from __future__ import annotations

import json
import re
import shutil
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import GigOptimizerConfig
from ..persistence import BlueprintRepository
from ..utils import build_gig_key


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CopilotTrainingService:
    STATUS_FILE = "status.json"
    GLOBAL_GIG_ID = "copilot-training-global"
    TOPIC_MAP = {
        "python": {"python", "fastapi", "django", "flask", "asyncio"},
        "javascript": {"javascript", "node", "react", "typescript", "nextjs"},
        "devops": {"docker", "redis", "postgres", "kubernetes", "nginx", "deploy"},
        "security": {"firewall", "security", "auth", "jwt", "csrf", "rate limit"},
        "ai": {"ai", "agent", "agentic", "llm", "prompt", "rag", "embedding", "fine-tune"},
        "fiverr": {"fiverr", "gig", "keyword", "title", "tags", "ctr", "conversion"},
    }
    EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)")
    URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
    SECRETISH_RE = re.compile(r"\b(?:sk|ghp|gho|ghu|Bearer|token|secret)[-_A-Za-z0-9]{10,}\b", re.IGNORECASE)

    def __init__(self, config: GigOptimizerConfig, repository: BlueprintRepository) -> None:
        self.config = config
        self.repository = repository
        self.training_dir = (self.config.data_dir / "copilot_training").resolve()
        self.exports_dir = self.training_dir / "exports"
        self.local_mirror_dir = self._resolve_local_mirror_dir()
        self.training_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        if self.local_mirror_dir is not None:
            self.local_mirror_dir.mkdir(parents=True, exist_ok=True)

    def status(self, *, gig_id: str | None = None) -> dict[str, Any]:
        target_gig = build_gig_key(gig_id or self.GLOBAL_GIG_ID)
        latest = self.repository.latest_copilot_training_run(gig_id=target_gig)
        feedback = self.repository.feedback_summary(gig_id=target_gig)
        if latest:
            summary = latest.get("summary") or {}
            return {
                "enabled": True,
                "gig_id": target_gig,
                "last_run_id": latest.get("run_id", ""),
                "last_exported_at": latest.get("finished_at") or latest.get("started_at") or "",
                "status": latest.get("status", "completed"),
                "train_examples": summary.get("train_examples", 0),
                "holdout_examples": summary.get("holdout_examples", 0),
                "preference_examples": summary.get("preference_examples", 0),
                "recent_topics": summary.get("top_topics", []),
                "feedback": feedback,
                "latest_files": {
                    "train_path": latest.get("train_path", ""),
                    "holdout_path": latest.get("holdout_path", ""),
                    "preferences_path": latest.get("preferences_path", ""),
                },
                "local_mirror": self._build_local_mirror_status(latest),
            }
        return {
            "enabled": True,
            "gig_id": target_gig,
            "last_run_id": "",
            "last_exported_at": "",
            "status": "idle",
            "train_examples": 0,
            "holdout_examples": 0,
            "preference_examples": 0,
            "recent_topics": [],
            "feedback": feedback,
            "latest_files": {
                "train_path": "",
                "holdout_path": "",
                "preferences_path": "",
            },
            "local_mirror": self._build_local_mirror_status(None),
        }

    def classify_topics(self, text: str) -> list[str]:
        lowered = str(text or "").lower()
        tags: list[str] = []
        for topic, keywords in self.TOPIC_MAP.items():
            if any(keyword in lowered for keyword in keywords):
                tags.append(topic)
        return tags or ["general"]

    def estimate_tokens(self, text: str) -> int:
        cleaned = str(text or "").strip()
        if not cleaned:
            return 0
        return max(1, int(len(cleaned.split()) * 1.35))

    def sanitize_text(self, text: str) -> tuple[str, int]:
        cleaned = str(text or "")
        redactions = 0
        for pattern, replacement in (
            (self.EMAIL_RE, "[redacted-email]"),
            (self.PHONE_RE, "[redacted-phone]"),
            (self.URL_RE, "[redacted-url]"),
            (self.SECRETISH_RE, "[redacted-secret]"),
        ):
            cleaned, count = pattern.subn(replacement, cleaned)
            redactions += count
        return cleaned.strip(), redactions

    def record_feedback(
        self,
        *,
        message_id: int,
        rating: int,
        note: str = "",
    ) -> dict[str, Any]:
        message = self.repository.get_assistant_message(int(message_id))
        if message is None:
            raise KeyError(message_id)
        if str(message.get("role", "")).lower() != "assistant":
            raise ValueError("Feedback can only be recorded for assistant messages.")
        topic_tags = self.classify_topics(f"{message.get('content', '')} {note}".strip())
        quality_score = self._feedback_quality_score(
            rating=int(rating),
            content=str(message.get("content", "")),
            note=str(note or ""),
        )
        return self.repository.record_assistant_feedback(
            message_id=int(message_id),
            rating=max(-1, min(1, int(rating))),
            note=str(note).strip(),
            topic_tags=topic_tags,
            quality_score=quality_score,
            metadata={
                "source": message.get("source", "assistant"),
                "estimated_tokens": self.estimate_tokens(str(message.get("content", ""))),
            },
        )

    def export_training_bundle(
        self,
        *,
        gig_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        del force
        started_at = utc_now()
        target_gig = build_gig_key(gig_id or self.GLOBAL_GIG_ID)
        messages = list(reversed(self.repository.list_assistant_messages(gig_id=target_gig, limit=600)))
        feedback_map = {
            int(item.get("message_id", 0)): item
            for item in self.repository.list_assistant_feedback(gig_id=target_gig, limit=400)
            if int(item.get("message_id", 0))
        }
        pairs = self._build_pairs(messages, feedback_map)
        run_id = uuid.uuid4().hex
        stamp = started_at.strftime("%Y%m%d-%H%M%S")
        export_dir = self.exports_dir / target_gig.replace(":", "_")
        export_dir.mkdir(parents=True, exist_ok=True)
        train_path = export_dir / f"{stamp}-{run_id}-train.jsonl"
        holdout_path = export_dir / f"{stamp}-{run_id}-holdout.jsonl"
        preferences_path = export_dir / f"{stamp}-{run_id}-preferences.jsonl"

        holdout_count = max(1, round(len(pairs) * 0.15)) if pairs else 0
        holdout = pairs[:holdout_count]
        train = pairs[holdout_count:]
        preferences = self._build_preferences(pairs)

        self._write_jsonl(train_path, train)
        self._write_jsonl(holdout_path, holdout)
        self._write_jsonl(preferences_path, preferences)

        topic_counter: Counter[str] = Counter()
        for item in pairs:
            topic_counter.update(item.get("metadata", {}).get("topic_tags", []))
        summary = {
            "gig_id": target_gig,
            "total_pairs": len(pairs),
            "train_examples": len(train),
            "holdout_examples": len(holdout),
            "preference_examples": len(preferences),
            "top_topics": [topic for topic, _ in topic_counter.most_common(8)],
            "generated_at": started_at.isoformat(),
        }
        mirror_details = self._mirror_export_bundle(
            gig_id=target_gig,
            train_path=train_path,
            holdout_path=holdout_path,
            preferences_path=preferences_path,
        )
        if mirror_details:
            summary["local_mirror"] = mirror_details
        finished_at = utc_now()
        self.repository.record_copilot_training_run(
            run_id=run_id,
            gig_id=target_gig,
            status="completed",
            train_path=str(train_path),
            holdout_path=str(holdout_path),
            preferences_path=str(preferences_path),
            summary=summary,
            started_at=started_at,
            finished_at=finished_at,
        )
        self._write_status(
            {
                **summary,
                "run_id": run_id,
                "status": "completed",
                "finished_at": finished_at.isoformat(),
                "train_path": str(train_path),
                "holdout_path": str(holdout_path),
                "preferences_path": str(preferences_path),
            },
            gig_id=target_gig,
        )
        return self.status(gig_id=target_gig)

    def _resolve_local_mirror_dir(self) -> Path | None:
        if not self.config.copilot_training_local_mirror_enabled:
            return None
        if self.config.copilot_training_local_mirror_dir is None:
            return None
        return Path(self.config.copilot_training_local_mirror_dir).expanduser().resolve()

    def _build_local_mirror_status(self, latest: dict[str, Any] | None) -> dict[str, Any]:
        summary = dict((latest or {}).get("summary") or {})
        local_mirror = dict(summary.get("local_mirror") or {})
        return {
            "enabled": self.local_mirror_dir is not None,
            "path": str(self.local_mirror_dir) if self.local_mirror_dir is not None else "",
            "last_synced_at": str(local_mirror.get("synced_at", "")),
            "latest_files": {
                "train_path": str(local_mirror.get("train_path", "")),
                "holdout_path": str(local_mirror.get("holdout_path", "")),
                "preferences_path": str(local_mirror.get("preferences_path", "")),
                "status_path": str(local_mirror.get("status_path", "")),
            },
        }

    def _mirror_export_bundle(
        self,
        *,
        gig_id: str,
        train_path: Path,
        holdout_path: Path,
        preferences_path: Path,
    ) -> dict[str, Any]:
        if self.local_mirror_dir is None:
            return {}
        target_dir = self.local_mirror_dir / gig_id.replace(":", "_")
        target_dir.mkdir(parents=True, exist_ok=True)
        mirrored_train = target_dir / train_path.name
        mirrored_holdout = target_dir / holdout_path.name
        mirrored_preferences = target_dir / preferences_path.name
        shutil.copy2(train_path, mirrored_train)
        shutil.copy2(holdout_path, mirrored_holdout)
        shutil.copy2(preferences_path, mirrored_preferences)
        return {
            "synced_at": utc_now().isoformat(),
            "train_path": str(mirrored_train),
            "holdout_path": str(mirrored_holdout),
            "preferences_path": str(mirrored_preferences),
            "status_path": str(target_dir / self.STATUS_FILE),
        }

    def _build_pairs(
        self,
        messages: list[dict[str, Any]],
        feedback_map: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        pairs: list[dict[str, Any]] = []
        pending_user: dict[str, Any] | None = None
        for message in messages:
            role = str(message.get("role", "")).strip().lower()
            if role == "user":
                pending_user = message
                continue
            if role != "assistant" or pending_user is None:
                continue
            user_text, user_redactions = self.sanitize_text(str(pending_user.get("content", "")))
            assistant_text, assistant_redactions = self.sanitize_text(str(message.get("content", "")))
            if len(user_text) < 4 or len(assistant_text) < 12:
                pending_user = None
                continue
            feedback = feedback_map.get(int(message.get("id", 0)), {})
            topic_tags = sorted(
                set(
                    self.classify_topics(f"{user_text} {assistant_text}")
                    + [str(tag).strip() for tag in (feedback.get("topic_tags") or []) if str(tag).strip()]
                    + [str(tag).strip() for tag in (message.get("metadata", {}).get("topic_tags") or []) if str(tag).strip()]
                )
            )
            quality_score = self._pair_quality_score(
                user_text=user_text,
                assistant_text=assistant_text,
                feedback=feedback,
                redactions=user_redactions + assistant_redactions,
            )
            pairs.append(
                {
                    "messages": [
                        {"role": "user", "content": user_text},
                        {"role": "assistant", "content": assistant_text},
                    ],
                    "metadata": {
                        "gig_id": message.get("gig_id"),
                        "user_message_id": pending_user.get("id"),
                        "assistant_message_id": message.get("id"),
                        "source": message.get("source", "assistant"),
                        "topic_tags": topic_tags,
                        "quality_score": quality_score,
                        "feedback_rating": int(feedback.get("rating", 0) or 0),
                        "estimated_tokens": {
                            "user": self.estimate_tokens(user_text),
                            "assistant": self.estimate_tokens(assistant_text),
                        },
                        "redaction_count": user_redactions + assistant_redactions,
                        "created_at": message.get("created_at"),
                    },
                }
            )
            pending_user = None
        return pairs

    def _build_preferences(self, pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for pair in pairs:
            prompt = str(pair.get("messages", [{}])[0].get("content", "")).strip()
            rating = int((pair.get("metadata", {}) or {}).get("feedback_rating", 0) or 0)
            if not prompt or rating == 0:
                continue
            bucket = grouped.setdefault(prompt, {"positive": [], "negative": []})
            bucket["positive" if rating > 0 else "negative"].append(pair)

        preferences: list[dict[str, Any]] = []
        for prompt, bucket in grouped.items():
            positives = bucket["positive"]
            negatives = bucket["negative"]
            for chosen, rejected in zip(positives, negatives):
                preferences.append(
                    {
                        "prompt": prompt,
                        "chosen": chosen["messages"][1]["content"],
                        "rejected": rejected["messages"][1]["content"],
                        "metadata": {
                            "topic_tags": chosen.get("metadata", {}).get("topic_tags", []),
                            "source": "feedback_pair",
                        },
                    }
                )
        return preferences

    def _feedback_quality_score(self, *, rating: int, content: str, note: str) -> float:
        score = 0.55
        score += 0.25 if rating > 0 else -0.15 if rating < 0 else 0.0
        score += 0.1 if len(str(content).strip()) > 80 else 0.0
        score += 0.05 if note.strip() else 0.0
        return round(max(0.0, min(1.0, score)), 3)

    def _pair_quality_score(
        self,
        *,
        user_text: str,
        assistant_text: str,
        feedback: dict[str, Any],
        redactions: int,
    ) -> float:
        score = 0.45
        score += min(len(user_text) / 400.0, 0.15)
        score += min(len(assistant_text) / 700.0, 0.2)
        feedback_rating = int(feedback.get("rating", 0) or 0)
        score += 0.2 if feedback_rating > 0 else -0.15 if feedback_rating < 0 else 0.0
        score -= min(redactions * 0.05, 0.2)
        return round(max(0.0, min(1.0, score)), 3)

    def _write_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_status(self, payload: dict[str, Any], *, gig_id: str) -> None:
        target = self.training_dir / gig_id.replace(":", "_")
        target.mkdir(parents=True, exist_ok=True)
        status_path = target / self.STATUS_FILE
        status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.local_mirror_dir is not None:
            mirror_target = self.local_mirror_dir / gig_id.replace(":", "_")
            mirror_target.mkdir(parents=True, exist_ok=True)
            mirror_status_path = mirror_target / self.STATUS_FILE
            mirror_status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
