from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ConversationMemory:
    def __init__(
        self,
        session_id: str,
        max_turns: int = 20,
        data_dir: Path = Path("data/conversations"),
    ) -> None:
        cleaned_session_id = "".join(
            character if character.isalnum() or character in {"-", "_"} else "-"
            for character in str(session_id or "global").strip()
        ).strip("-")
        self.session_id = cleaned_session_id or "global"
        self.max_turns = max(1, int(max_turns or 20))
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / f"{self.session_id}.jsonl"

    def add(self, role: str, text: str) -> None:
        entry = {
            "role": str(role or "").strip() or "assistant",
            "text": str(text or ""),
            "ts": _utc_iso(),
        }
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._trim()

    def recent(self, n: int = 10) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        items: list[dict] = []
        for line in lines:
            cleaned = line.strip()
            if not cleaned:
                continue
            try:
                payload = json.loads(cleaned)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                items.append(payload)
        return items[-max(1, int(n or 10)) :]

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def summary(self) -> str:
        turns = self.recent(6)
        lines: list[str] = []
        for turn in turns:
            role = "You" if str(turn.get("role", "")).lower() == "user" else "Copilot"
            text = str(turn.get("text", "")).strip()
            if text:
                lines.append(f"{role}: {text}")
        return "\n".join(lines)

    def _trim(self) -> None:
        turns = self.recent(self.max_turns)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            for turn in turns:
                handle.write(json.dumps(turn, ensure_ascii=False) + "\n")
