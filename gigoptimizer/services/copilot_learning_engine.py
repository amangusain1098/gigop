"""Copilot Learning Engine — predictive vocabulary model + auto-learning scheduler."""
from __future__ import annotations
import json, math, re, subprocess, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9']{2,}", text.lower())


_STOP_WORDS = {
    "the","and","for","are","but","not","you","all","can","her","was","one",
    "our","out","day","get","has","him","his","how","its","may","new","now",
    "old","see","two","way","who","any","did","let","put","say","she","too",
    "use","that","this","with","have","from","they","will","been","were",
    "your","more","also","into","some","than","then","them","these","those",
    "what","when","which","about","after","before","could","their","there",
    "would","should","other","each","just","over","such",
}


class CopilotLearningEngine:
    """Manages the vocabulary model, learning log, and cron schedule."""

    VERSION = "1.0.0"
    INTERVALS = {"1h": 3600, "6h": 21600, "12h": 43200, "24h": 86400, "48h": 172800}
    DEFAULT_INTERVAL = "6h"

    def __init__(self, data_dir: Path) -> None:
        self.root = (data_dir / "copilot_learning").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._corpus_dir = self.root / "corpus"
        self._corpus_dir.mkdir(exist_ok=True)
        self._model_file    = self.root / "vocab_model.json"
        self._log_file      = self.root / "learning_log.jsonl"
        self._schedule_file = self.root / "schedule.json"
        self._stats_file    = self.root / "stats.json"
        self._tests_file    = self.root / "last_test_results.json"
        self._vocab: dict[str, dict] = {}
        self._doc_count: int = 0
        self._bigrams: Counter = Counter()
        self._load_model()

    # --- Public API ---

    def ingest_text(self, text: str, source: str, source_type: str = "manual") -> dict:
        if not text or not text.strip():
            return {"ingested": False, "reason": "empty text"}
        tokens = _tokenize(text)
        meaningful = [t for t in tokens if t not in _STOP_WORDS]
        if len(meaningful) < 3:
            return {"ingested": False, "reason": "too short"}
        doc_id = f"{source_type}_{int(time.time() * 1000)}"
        doc_path = self._corpus_dir / f"{doc_id}.json"
        doc_path.write_text(json.dumps({
            "id": doc_id, "source": source, "source_type": source_type,
            "ingested_at": _utc_now(), "token_count": len(tokens),
            "text_preview": text[:300],
        }), encoding="utf-8")
        tf = Counter(meaningful)
        self._doc_count += 1
        for word, count in tf.items():
            if word not in self._vocab:
                self._vocab[word] = {"df": 0, "ttf": 0}
            self._vocab[word]["df"] += 1
            self._vocab[word]["ttf"] += count
        for i in range(len(meaningful) - 1):
            self._bigrams[f"{meaningful[i]} {meaningful[i+1]}"] += 1
        self._recompute_idf()
        self._save_model()
        new_words = sum(1 for w in tf if self._vocab.get(w, {}).get("df", 0) == 1)
        event = {
            "event_id": doc_id, "timestamp": _utc_now(), "source": source,
            "source_type": source_type, "tokens_learned": len(tf), "new_words": new_words,
        }
        self._append_log(event)
        self._update_stats(tokens_added=len(tf), docs_added=1, new_words=new_words)
        return {"ingested": True, "doc_id": doc_id, "tokens_learned": len(tf), "new_words": new_words}

    def ingest_conversations(self, conversations_dir: Path) -> dict:
        if not conversations_dir.exists():
            return {"ingested": 0, "skipped": 0, "reason": "dir not found"}
        jsonl_files = list(conversations_dir.glob("*.jsonl"))
        ingested = skipped = 0
        for jf in jsonl_files:
            try:
                texts = []
                for line in jf.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                        for key in ("message", "content", "text", "user", "assistant"):
                            if isinstance(obj.get(key), str):
                                texts.append(obj[key])
                    except json.JSONDecodeError:
                        continue
                if texts:
                    r = self.ingest_text(" ".join(texts), source=jf.name, source_type="conversation")
                    (ingested if r["ingested"] else skipped).__class__  # unused; count below
                    if r["ingested"]:
                        ingested += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1
        return {"ingested": ingested, "skipped": skipped, "files_scanned": len(jsonl_files)}

    def predict_completions(self, partial: str, top_n: int = 8) -> list[dict]:
        if not partial or not partial.strip():
            return []
        partial = partial.lower().strip()
        tokens = _tokenize(partial)
        if not tokens:
            return []
        last_word = tokens[-1]
        word_scores: list[tuple[float, str]] = []
        for word, stats in self._vocab.items():
            is_different = (word != last_word)
            if word.startswith(last_word) and is_different:
                score = stats.get("ttf", 1) * stats.get("idf", 1.0)
                word_scores.append((score, word))
        word_scores.sort(reverse=True)
        results: list[dict] = []
        seen: set[str] = set()
        prefix_without_last = partial[: -len(last_word)]
        for score, word in word_scores[:top_n]:
            if word not in seen:
                seen.add(word)
                results.append({
                    "type": "word", "completion": word, "score": round(score, 3),
                    "full_suggestion": prefix_without_last + word,
                })
        if len(tokens) >= 2:
            prefix_bg = f"{tokens[-2]} {last_word}"
            bigram_hits = [(cnt, bg) for bg, cnt in self._bigrams.items()
                           if bg.startswith(prefix_bg) and bg != prefix_bg]
            bigram_hits.sort(reverse=True)
            for cnt, bg in bigram_hits[:3]:
                next_word = bg[len(prefix_bg):].strip()
                if next_word:
                    results.append({
                        "type": "phrase", "completion": next_word,
                        "score": round(cnt * 2.0, 3),
                        "full_suggestion": partial + " " + next_word,
                    })
        seen_sugg: set[str] = set()
        final: list[dict] = []
        for r in sorted(results, key=lambda x: x["score"], reverse=True):
            k = r["full_suggestion"]
            if k not in seen_sugg:
                seen_sugg.add(k)
                final.append(r)
        return final[:top_n]

    def get_dashboard_stats(self) -> dict:
        stats = self._load_stats()
        schedule = self._load_schedule()
        recent_log = self._recent_log(limit=20)
        test_results = self._load_test_results()
        top_words = sorted(
            [(w, s["ttf"], s.get("idf", 1.0)) for w, s in self._vocab.items()],
            key=lambda x: x[1] * x[2], reverse=True,
        )[:30]
        return {
            "version": self.VERSION,
            "model": {
                "vocab_size": len(self._vocab),
                "doc_count": self._doc_count,
                "bigram_count": len(self._bigrams),
                "top_words": [{"word": w, "freq": tf, "idf": round(idf, 3)} for w, tf, idf in top_words],
            },
            "totals": stats,
            "schedule": schedule,
            "recent_learning": recent_log,
            "test_results": test_results,
            "corpus_docs": self._list_corpus_docs(limit=50),
        }

    def run_training_cycle(self, conversations_dir: Path | None = None) -> dict:
        started_at = _utc_now()
        results: dict[str, Any] = {"started_at": started_at, "steps": []}
        if conversations_dir and conversations_dir.exists():
            conv_result = self.ingest_conversations(conversations_dir)
            results["steps"].append({"step": "ingest_conversations", **conv_result})
        else:
            results["steps"].append({"step": "ingest_conversations", "skipped": True})
        schedule = self._load_schedule()
        interval_s = self.INTERVALS.get(schedule.get("interval", self.DEFAULT_INTERVAL), 21600)
        schedule["last_run"] = started_at
        schedule["next_run"] = datetime.fromtimestamp(
            time.time() + interval_s, tz=timezone.utc
        ).isoformat()
        schedule["run_count"] = schedule.get("run_count", 0) + 1
        self._save_schedule(schedule)
        results["finished_at"] = _utc_now()
        results["schedule"] = schedule
        self._append_log({
            "event_id": f"cycle_{int(time.time())}", "timestamp": started_at,
            "source": "auto_training_cycle", "source_type": "cron",
            "cycle_results": results["steps"],
        })
        return results

    def run_tests(self, repo_root: Path) -> dict:
        started = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "unittest",
                 "tests.test_copilot_round3", "tests.test_marketplace_reader",
                 "tests.test_conversation_memory", "tests.test_assistant", "-v"],
                capture_output=True, text=True, cwd=str(repo_root), timeout=120,
            )
            output = proc.stderr + proc.stdout
            elapsed = round(time.monotonic() - started, 2)
            m_ran = re.search(r"Ran (\d+) tests?", output)
            total = int(m_ran.group(1)) if m_ran else 0
            failed = len(re.findall(r"\nFAIL:", output, re.MULTILINE))
            errors = len(re.findall(r"\nERROR:", output, re.MULTILINE))
            passed = total - failed - errors
            status = "pass" if proc.returncode == 0 else "fail"
            result = {"run_at": _utc_now(), "status": status, "total": total,
                      "passed": passed, "failed": failed, "errors": errors,
                      "elapsed_s": elapsed, "output_tail": output[-2000:]}
        except Exception as exc:
            result = {"run_at": _utc_now(), "status": "error", "total": 0,
                      "passed": 0, "failed": 0, "errors": 0, "elapsed_s": 0, "output_tail": str(exc)}
        self._tests_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    def get_schedule(self) -> dict:
        return self._load_schedule()

    def set_schedule(self, interval: str, enabled: bool = True) -> dict:
        if interval not in self.INTERVALS:
            raise ValueError(f"interval must be one of {list(self.INTERVALS)}")
        schedule = self._load_schedule()
        schedule.update({"interval": interval, "enabled": enabled,
                         "interval_seconds": self.INTERVALS[interval], "updated_at": _utc_now()})
        if enabled and not schedule.get("next_run"):
            schedule["next_run"] = datetime.fromtimestamp(
                time.time() + self.INTERVALS[interval], tz=timezone.utc
            ).isoformat()
        self._save_schedule(schedule)
        return schedule

    # --- Private helpers ---

    def _recompute_idf(self) -> None:
        N = max(self._doc_count, 1)
        for stats in self._vocab.values():
            df = max(stats["df"], 1)
            stats["idf"] = math.log((N + 1) / (df + 1)) + 1.0

    def _save_model(self) -> None:
        self._model_file.write_text(json.dumps({
            "doc_count": self._doc_count, "vocab": self._vocab,
            "bigrams": dict(self._bigrams.most_common(5000)), "saved_at": _utc_now(),
        }), encoding="utf-8")

    def _load_model(self) -> None:
        if not self._model_file.exists():
            return
        try:
            data = json.loads(self._model_file.read_text(encoding="utf-8"))
            self._doc_count = data.get("doc_count", 0)
            self._vocab = data.get("vocab", {})
            self._bigrams = Counter(data.get("bigrams", {}))
        except Exception:
            pass

    def _append_log(self, event: dict) -> None:
        with self._log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")

    def _recent_log(self, limit: int = 20) -> list[dict]:
        if not self._log_file.exists():
            return []
        results = []
        for line in reversed(self._log_file.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(results) >= limit:
                break
        return results

    def _load_stats(self) -> dict:
        if not self._stats_file.exists():
            return {"total_docs": 0, "total_tokens": 0, "total_new_words": 0, "cycles_run": 0}
        try:
            return json.loads(self._stats_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _update_stats(self, *, tokens_added: int, docs_added: int, new_words: int) -> None:
        stats = self._load_stats()
        stats["total_docs"] = stats.get("total_docs", 0) + docs_added
        stats["total_tokens"] = stats.get("total_tokens", 0) + tokens_added
        stats["total_new_words"] = stats.get("total_new_words", 0) + new_words
        stats["last_updated"] = _utc_now()
        self._stats_file.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    def _load_schedule(self) -> dict:
        if not self._schedule_file.exists():
            default = {"enabled": True, "interval": self.DEFAULT_INTERVAL,
                       "interval_seconds": self.INTERVALS[self.DEFAULT_INTERVAL],
                       "last_run": None, "next_run": None, "run_count": 0, "created_at": _utc_now()}
            self._save_schedule(default)
            return default
        try:
            return json.loads(self._schedule_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_schedule(self, schedule: dict) -> None:
        self._schedule_file.write_text(json.dumps(schedule, indent=2), encoding="utf-8")

    def _load_test_results(self) -> dict:
        if not self._tests_file.exists():
            return {"status": "never_run", "total": 0, "passed": 0, "failed": 0, "errors": 0}
        try:
            return json.loads(self._tests_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _list_corpus_docs(self, limit: int = 50) -> list[dict]:
        docs = []
        for p in sorted(self._corpus_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
            try:
                docs.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return docs
