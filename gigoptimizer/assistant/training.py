"""Local training pipeline for the GigOptimizer AI assistant.

This module implements the "Ollama Modelfile + RAG" training strategy:

1. **Dataset export** - walks the product's own historical data (gigs,
   optimization reports, knowledge base entries, assistant feedback) and
   builds a supervised-fine-tuning JSONL file plus a few-shot seed file.
2. **Modelfile generation** - emits an Ollama ``Modelfile`` that bakes the
   ``GIG_OPTIMIZER_SYSTEM_PROMPT`` and the strongest few-shot examples into a
   custom local model (e.g. ``gigoptimizer-llama3``). The user can then run
   ``ollama create gigoptimizer-llama3 -f Modelfile`` to materialize it.
3. **RAG index** - builds a lightweight retrieval index (JSON + inverted
   token list, zero new dependencies) over the knowledge base so the
   assistant can ground its answers in the user's own documents.

Everything lives under ``<data_dir>/assistant/`` and is safe to regenerate
from scratch. No network calls are made - this is pure local prep.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .prompts import GIG_OPTIMIZER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TrainingExample:
    """One supervised example (prompt -> completion)."""

    instruction: str
    input: str
    output: str
    source: str = "dataset"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_chat_messages(self) -> list[dict[str, str]]:
        user = self.instruction
        if self.input:
            user = f"{self.instruction}\n\n{self.input}"
        return [
            {"role": "system", "content": GIG_OPTIMIZER_SYSTEM_PROMPT},
            {"role": "user", "content": user},
            {"role": "assistant", "content": self.output},
        ]


@dataclass(slots=True)
class TrainingReport:
    dataset_path: str
    fewshot_path: str
    modelfile_path: str
    rag_index_path: str
    rag_chunks_path: str
    total_examples: int
    total_fewshot: int
    total_rag_chunks: int
    vocabulary_size: int
    base_model: str
    custom_model_name: str
    created_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Repository-facing adapters
# ---------------------------------------------------------------------------
class _RepoAdapter:
    """Tiny shim so the trainer is not coupled to a concrete repository.

    The product already has ``BlueprintRepository`` with methods like
    ``list_assistant_messages``, ``list_knowledge_documents``, etc., but
    different environments expose slightly different surfaces. Instead of
    hard-coding all of them we probe for methods by name and gracefully
    degrade if one is missing.
    """

    def __init__(self, repository: Any | None) -> None:
        self.repository = repository

    def _safe_call(self, name: str, *args: Any, **kwargs: Any) -> list[Any]:
        if self.repository is None:
            return []
        method = getattr(self.repository, name, None)
        if method is None:
            return []
        try:
            result = method(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - repo errors must not kill training
            logger.warning("training: repository.%s failed: %s", name, exc)
            return []
        if result is None:
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, Iterable):
            return list(result)
        return [result]

    def assistant_messages(self, *, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._safe_call("list_assistant_messages", gig_id="global", limit=limit)
        return [r for r in rows if isinstance(r, Mapping)]

    def assistant_feedback(self, *, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._safe_call("list_assistant_feedback", gig_id="global", limit=limit)
        return [r for r in rows if isinstance(r, Mapping)]

    def knowledge_documents(self, *, limit: int = 500) -> list[dict[str, Any]]:
        for name in ("list_knowledge_documents", "list_knowledge_entries", "list_knowledge"):
            rows = self._safe_call(name, limit=limit)
            if rows:
                return [r for r in rows if isinstance(r, Mapping)]
        return []

    def gig_snapshots(self, *, limit: int = 100) -> list[dict[str, Any]]:
        for name in ("list_gig_snapshots", "list_gigs", "list_fiverr_gigs"):
            rows = self._safe_call(name, limit=limit)
            if rows:
                return [r for r in rows if isinstance(r, Mapping)]
        return []

    def optimization_reports(self, *, limit: int = 100) -> list[dict[str, Any]]:
        for name in ("list_optimization_reports", "list_reports", "list_weekly_reports"):
            rows = self._safe_call(name, limit=limit)
            if rows:
                return [r for r in rows if isinstance(r, Mapping)]
        return []


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------
_PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"https?://\S+"), "[url]"),
    (re.compile(r"\+?\d[\d \-()]{7,}\d"), "[phone]"),
]


def _redact(text: str) -> str:
    cleaned = text or ""
    for pattern, replacement in _PII_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned.strip()


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


# ---------------------------------------------------------------------------
# Main trainer
# ---------------------------------------------------------------------------
class AssistantTrainer:
    """Exports training data, builds a Modelfile, and writes a RAG index."""

    DEFAULT_BASE_MODEL = "llama3.1:8b"
    DEFAULT_CUSTOM_MODEL = "gigoptimizer-llama3"
    MAX_CHUNK_CHARS = 1200
    MAX_RAG_CHUNKS = 400
    MAX_FEWSHOT = 6

    def __init__(
        self,
        *,
        data_dir: str | os.PathLike[str],
        repository: Any | None = None,
        base_model: str | None = None,
        custom_model_name: str | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.assistant_dir = self.data_dir / "assistant"
        self.assistant_dir.mkdir(parents=True, exist_ok=True)
        self.repo = _RepoAdapter(repository)
        self.base_model = base_model or self.DEFAULT_BASE_MODEL
        self.custom_model_name = custom_model_name or self.DEFAULT_CUSTOM_MODEL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def train(
        self,
        *,
        extra_examples: Sequence[TrainingExample] | None = None,
    ) -> TrainingReport:
        """Run the full pipeline and return a ``TrainingReport``."""

        warnings: list[str] = []
        created: list[str] = []

        examples = self.export_dataset(extra_examples=extra_examples)
        dataset_path = self.assistant_dir / "dataset.jsonl"
        self._write_jsonl(dataset_path, [ex.to_dict() for ex in examples])
        created.append(str(dataset_path))

        chat_path = self.assistant_dir / "dataset.chat.jsonl"
        self._write_jsonl(
            chat_path,
            [{"messages": ex.to_chat_messages()} for ex in examples],
        )
        created.append(str(chat_path))

        fewshot = self._select_fewshot(examples)
        fewshot_path = self.assistant_dir / "fewshot.jsonl"
        self._write_jsonl(fewshot_path, [ex.to_dict() for ex in fewshot])
        created.append(str(fewshot_path))

        if not examples:
            warnings.append(
                "Dataset is empty - falling back to seed examples baked from prompt templates."
            )

        modelfile_path = self.assistant_dir / "Modelfile"
        modelfile_path.write_text(self._render_modelfile(fewshot), encoding="utf-8")
        created.append(str(modelfile_path))

        rag_chunks = self._build_rag_chunks()
        rag_chunks_path = self.assistant_dir / "rag_chunks.jsonl"
        self._write_jsonl(rag_chunks_path, rag_chunks)
        created.append(str(rag_chunks_path))

        rag_index = self._build_rag_index(rag_chunks)
        rag_index_path = self.assistant_dir / "rag_index.json"
        rag_index_path.write_text(
            json.dumps(rag_index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        created.append(str(rag_index_path))

        if not rag_chunks:
            warnings.append("No knowledge documents found - RAG index is empty.")

        return TrainingReport(
            dataset_path=str(dataset_path),
            fewshot_path=str(fewshot_path),
            modelfile_path=str(modelfile_path),
            rag_index_path=str(rag_index_path),
            rag_chunks_path=str(rag_chunks_path),
            total_examples=len(examples),
            total_fewshot=len(fewshot),
            total_rag_chunks=len(rag_chunks),
            vocabulary_size=len(rag_index.get("vocabulary", [])),
            base_model=self.base_model,
            custom_model_name=self.custom_model_name,
            created_files=created,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Dataset export
    # ------------------------------------------------------------------
    def export_dataset(
        self,
        *,
        extra_examples: Sequence[TrainingExample] | None = None,
    ) -> list[TrainingExample]:
        examples: list[TrainingExample] = []
        examples.extend(self._seed_examples())
        examples.extend(self._examples_from_assistant_messages())
        examples.extend(self._examples_from_gigs())
        examples.extend(self._examples_from_reports())
        if extra_examples:
            examples.extend(extra_examples)

        # Deduplicate on (instruction, input)
        seen: set[tuple[str, str]] = set()
        unique: list[TrainingExample] = []
        for ex in examples:
            key = (ex.instruction.strip(), ex.input.strip())
            if key in seen:
                continue
            seen.add(key)
            unique.append(ex)
        return unique

    def _seed_examples(self) -> list[TrainingExample]:
        """A handful of gold-standard examples baked from the system prompt.

        These guarantee the dataset is never empty and give the model a
        reliable anchor for the required 4-part output format.
        """

        return [
            TrainingExample(
                instruction="Optimize this Fiverr gig title for a WordPress speed audit service.",
                input="Title: I will make your WordPress fast\nTags: wordpress, speed, seo",
                output=(
                    "Analysis:\n"
                    "- Title is generic and drops the proof metric.\n"
                    "- No platform-specific power word in the first 40 chars.\n"
                    "Problems:\n"
                    "- No PageSpeed / Core Web Vitals anchor.\n"
                    "- No outcome number buyers search for.\n"
                    "- Tags are too broad.\n"
                    "Optimized Version:\n"
                    "Title: I will optimize WordPress speed and Core Web Vitals for a 90+ PageSpeed score\n"
                    "Tags: wordpress speed, core web vitals, pagespeed insights, gtmetrix, lcp fix\n"
                    "Action Steps:\n"
                    "1. Rewrite the title with the outcome metric.\n"
                    "2. Add a before/after PageSpeed screenshot.\n"
                    "3. Replace broad tags with 5 intent-matched terms.\n"
                ),
                source="seed",
                tags=["fiverr", "seo", "wordpress"],
            ),
            TrainingExample(
                instruction="Audit this landing page for Core Web Vitals wins.",
                input="URL: [url]\nStack: WordPress + Elementor + WooCommerce",
                output=(
                    "Analysis:\n"
                    "- Render-blocking CSS is the most common LCP killer on this stack.\n"
                    "- Elementor ships wide fonts that inflate CLS.\n"
                    "Problems:\n"
                    "- LCP > 2.5s on mobile.\n"
                    "- CLS > 0.1 from late-loading hero image.\n"
                    "- JS main thread blocked by analytics tag.\n"
                    "Optimized Version:\n"
                    "- Preload the hero image + font file.\n"
                    "- Defer analytics + chat widgets.\n"
                    "- Move critical CSS inline, async the rest.\n"
                    "Action Steps:\n"
                    "1. Preload LCP image with fetchpriority=high.\n"
                    "2. Inline critical CSS for above-the-fold.\n"
                    "3. Reserve space for hero to kill CLS.\n"
                    "4. Defer Elementor background videos.\n"
                ),
                source="seed",
                tags=["audit", "core web vitals", "wordpress"],
            ),
            TrainingExample(
                instruction="Generate 3 Twitter hooks for a WordPress speed offer.",
                input="Audience: SaaS founders with slow marketing sites.",
                output=(
                    "Analysis:\n"
                    "- Founders care about conversion loss, not tech jargon.\n"
                    "Problems:\n"
                    "- Most hooks lead with tools instead of outcomes.\n"
                    "Optimized Version:\n"
                    "Post 1: Your slow homepage is costing you 7% of signups. I fixed it for 40+ SaaS teams. Today's audit slot is open.\n"
                    "\n"
                    "Post 2: Google now ranks Core Web Vitals like a page speed exam. Here is the 5-minute fix I ship for every client.\n"
                    "\n"
                    "Post 3: Every 100ms of load time = 1% drop in conversions. DM me and I will audit your pricing page for free this week.\n"
                    "Hashtags: wordpress, seo, coreWebVitals\n"
                    "Action Steps:\n"
                    "1. Post once per morning at 9am local.\n"
                    "2. Pin the best performer for 24h.\n"
                    "3. Reply to every comment with a mini-tip.\n"
                ),
                source="seed",
                tags=["content", "twitter", "saas"],
            ),
        ]

    def _examples_from_assistant_messages(self) -> list[TrainingExample]:
        messages = self.repo.assistant_messages(limit=500)
        if not messages:
            return []
        feedback = {
            int(item.get("message_id", 0) or 0): item
            for item in self.repo.assistant_feedback(limit=500)
            if isinstance(item, Mapping)
        }
        # Walk in chronological order and pair user -> assistant turns.
        ordered = list(reversed(messages))
        pairs: list[TrainingExample] = []
        pending_user: dict[str, Any] | None = None
        for msg in ordered:
            role = str(msg.get("role") or "").lower()
            content = _redact(_coerce_str(msg.get("content")))
            if not content:
                continue
            if role == "user":
                pending_user = {"content": content, "topic": msg.get("topic", "")}
                continue
            if role == "assistant" and pending_user is not None:
                mid = int(msg.get("id") or msg.get("message_id") or 0)
                verdict = feedback.get(mid, {}).get("verdict")
                if verdict and str(verdict).lower() in {"down", "bad", "reject"}:
                    pending_user = None
                    continue
                pairs.append(
                    TrainingExample(
                        instruction=pending_user["content"],
                        input="",
                        output=content,
                        source="assistant_history",
                        tags=[str(pending_user.get("topic") or "general")],
                    )
                )
                pending_user = None
        return pairs

    def _examples_from_gigs(self) -> list[TrainingExample]:
        gigs = self.repo.gig_snapshots(limit=80)
        examples: list[TrainingExample] = []
        for gig in gigs:
            title = _redact(_coerce_str(gig.get("title")))
            description = _redact(_coerce_str(gig.get("description")))
            if not title and not description:
                continue
            tags = gig.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            input_blob = (
                f"Title: {title}\n"
                f"Description: {description[:600]}\n"
                f"Tags: {', '.join(tags[:5])}"
            )
            examples.append(
                TrainingExample(
                    instruction="Optimize this Fiverr gig for discoverability and conversion.",
                    input=input_blob,
                    output=self._stub_output_for_gig(title, tags),
                    source="gig_snapshot",
                    tags=list(tags)[:5],
                )
            )
        return examples

    def _examples_from_reports(self) -> list[TrainingExample]:
        reports = self.repo.optimization_reports(limit=60)
        examples: list[TrainingExample] = []
        for report in reports:
            summary = _redact(_coerce_str(report.get("summary") or report.get("body")))
            if not summary:
                continue
            topic = _coerce_str(report.get("topic") or report.get("title") or "weekly report")
            examples.append(
                TrainingExample(
                    instruction=f"Explain the wins and gaps from this optimization report: {topic}",
                    input=summary[:1200],
                    output=self._stub_output_for_report(topic, summary),
                    source="report",
                    tags=[topic[:32]],
                )
            )
        return examples

    def _stub_output_for_gig(self, title: str, tags: Sequence[str]) -> str:
        anchor = (tags[0] if tags else "your service").strip() or "your service"
        return (
            "Analysis:\n"
            f"- The title '{title[:80]}' can lead harder with the outcome.\n"
            f"- Tags lean on {anchor}; need 2 long-tail intent terms.\n"
            "Problems:\n"
            "- Missing proof block (before/after, PageSpeed, metrics).\n"
            "- No CTA inside the first package description.\n"
            "Optimized Version:\n"
            f"Title: I will deliver {anchor} results with a proven audit.\n"
            "Description: Hook -> pain -> deliverables -> proof -> CTA.\n"
            "Tags: Mix 3 head terms and 2 long-tail intent terms.\n"
            "Action Steps:\n"
            "1. Rewrite the title around the outcome.\n"
            "2. Add a before/after proof block.\n"
            "3. Ship Basic / Standard / Premium packages with a CTA.\n"
        )

    def _stub_output_for_report(self, topic: str, summary: str) -> str:
        return (
            "Analysis:\n"
            f"- Report '{topic}' shows room for a bigger conversion story.\n"
            "Problems:\n"
            "- Wins are buried under raw numbers.\n"
            "- No clear next bet for the coming week.\n"
            "Optimized Version:\n"
            f"- Lead with the top 3 wins from: {summary[:200]}\n"
            "- Turn each gap into an action item with an owner.\n"
            "Action Steps:\n"
            "1. Ship the top 3 wins as client-ready one-liners.\n"
            "2. Turn every gap into a ticket for next week.\n"
            "3. Send a 3-bullet summary to stakeholders today.\n"
        )

    # ------------------------------------------------------------------
    # Few-shot selection
    # ------------------------------------------------------------------
    def _select_fewshot(self, examples: Sequence[TrainingExample]) -> list[TrainingExample]:
        """Pick the strongest N examples for the Modelfile."""
        scored: list[tuple[int, TrainingExample]] = []
        for ex in examples:
            score = 0
            text = ex.output.lower()
            for header in ("analysis", "problems", "optimized version", "action steps"):
                if header in text:
                    score += 5
            if len(text) > 400:
                score += 5
            if ex.source == "seed":
                score += 8
            if ex.source == "assistant_history":
                score += 3
            scored.append((score, ex))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [ex for _, ex in scored[: self.MAX_FEWSHOT]]

    # ------------------------------------------------------------------
    # Modelfile
    # ------------------------------------------------------------------
    def _render_modelfile(self, fewshot: Sequence[TrainingExample]) -> str:
        system_block = GIG_OPTIMIZER_SYSTEM_PROMPT.strip().replace('"""', '\\"\\"\\"')
        lines: list[str] = [
            f"# GigOptimizer AI - custom Ollama model",
            f"# Generated at {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"FROM {self.base_model}",
            "",
            "PARAMETER temperature 0.4",
            "PARAMETER top_p 0.9",
            "PARAMETER num_ctx 4096",
            "PARAMETER repeat_penalty 1.05",
            "",
            'SYSTEM """',
            system_block,
            '"""',
            "",
        ]
        for ex in fewshot:
            user = ex.instruction
            if ex.input:
                user = f"{ex.instruction}\n\n{ex.input}"
            user = user.replace('"""', '\\"\\"\\"')
            assistant = ex.output.replace('"""', '\\"\\"\\"')
            lines.extend(
                [
                    'MESSAGE user """',
                    user,
                    '"""',
                    'MESSAGE assistant """',
                    assistant,
                    '"""',
                    "",
                ]
            )
        lines.append(
            "# To build: ollama create "
            f"{self.custom_model_name} -f Modelfile"
        )
        lines.append(
            "# To run:   ollama run "
            f"{self.custom_model_name}"
        )
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # RAG
    # ------------------------------------------------------------------
    def _build_rag_chunks(self) -> list[dict[str, Any]]:
        docs = self.repo.knowledge_documents(limit=500)
        chunks: list[dict[str, Any]] = []
        for doc in docs:
            title = _coerce_str(doc.get("title") or doc.get("name") or "knowledge")
            body = _coerce_str(doc.get("content") or doc.get("body") or doc.get("text"))
            if not body.strip():
                continue
            body = _redact(body)
            for idx, chunk in enumerate(self._chunk_text(body)):
                if len(chunks) >= self.MAX_RAG_CHUNKS:
                    return chunks
                chunks.append(
                    {
                        "id": f"{title[:40]}::{idx}",
                        "title": title,
                        "chunk_index": idx,
                        "text": chunk,
                    }
                )
        return chunks

    def _chunk_text(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        if len(text) <= self.MAX_CHUNK_CHARS:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + self.MAX_CHUNK_CHARS, len(text))
            # Try to break on a sentence or paragraph boundary.
            window = text[start:end]
            pivot = max(window.rfind("\n\n"), window.rfind(". "))
            if pivot > self.MAX_CHUNK_CHARS // 2:
                end = start + pivot + 1
            chunks.append(text[start:end].strip())
            start = end
        return [c for c in chunks if c]

    def _build_rag_index(self, chunks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Build a minimal TF-IDF style inverted index.

        We emit an index file the assistant can load at runtime without any
        extra dependencies. It stores the vocabulary, document frequencies,
        and per-chunk term weights.
        """

        doc_term_counts: list[Counter[str]] = []
        df: Counter[str] = Counter()
        for chunk in chunks:
            # Title tokens count too so queries like 'Fiverr title' hit a
            # chunk whose body does not mention 'Fiverr'.
            title_tokens = _tokenize(chunk.get("title", ""))
            body_tokens = _tokenize(chunk.get("text", ""))
            tokens = title_tokens + title_tokens + body_tokens
            counts = Counter(tokens)
            doc_term_counts.append(counts)
            for term in counts:
                df[term] += 1

        n_docs = max(1, len(chunks))
        vocabulary = sorted(df.keys())
        term_to_id = {term: i for i, term in enumerate(vocabulary)}
        idf = {term: math.log((1 + n_docs) / (1 + df[term])) + 1 for term in vocabulary}

        doc_weights: list[dict[str, float]] = []
        for counts in doc_term_counts:
            max_tf = max(counts.values()) if counts else 1
            weights = {
                str(term_to_id[term]): round((count / max_tf) * idf[term], 5)
                for term, count in counts.items()
            }
            doc_weights.append(weights)

        postings: dict[str, list[int]] = defaultdict(list)
        for doc_id, counts in enumerate(doc_term_counts):
            for term in counts:
                postings[str(term_to_id[term])].append(doc_id)

        return {
            "schema_version": 1,
            "n_docs": n_docs,
            "vocabulary": vocabulary,
            "idf": {str(term_to_id[t]): round(v, 5) for t, v in idf.items()},
            "doc_weights": doc_weights,
            "postings": postings,
            "chunks": [
                {"id": c.get("id"), "title": c.get("title")}
                for c in chunks
            ],
        }

    # ------------------------------------------------------------------
    # IO helpers
    # ------------------------------------------------------------------
    def _write_jsonl(self, path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


__all__ = [
    "AssistantTrainer",
    "TrainingExample",
    "TrainingReport",
]
