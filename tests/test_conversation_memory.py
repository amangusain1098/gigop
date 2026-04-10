from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from gigoptimizer.assistant.memory import ConversationMemory


class ConversationMemoryTests(unittest.TestCase):
    def test_add_recent_summary_and_clear(self) -> None:
        with TemporaryDirectory() as tmp:
            memory = ConversationMemory("demo-session", data_dir=Path(tmp), max_turns=4)
            memory.add("user", "Hello there")
            memory.add("assistant", "Hi, how can I help?")
            memory.add("user", "Rewrite my Fiverr title")

            recent = memory.recent(2)
            self.assertEqual(len(recent), 2)
            self.assertEqual(recent[0]["role"], "assistant")
            self.assertEqual(recent[1]["role"], "user")

            summary = memory.summary()
            self.assertIn("You: Hello there", summary)
            self.assertIn("Copilot: Hi, how can I help?", summary)

            memory.clear()
            self.assertEqual(memory.recent(), [])

    def test_max_turns_keeps_latest_entries_only(self) -> None:
        with TemporaryDirectory() as tmp:
            memory = ConversationMemory("trim-session", data_dir=Path(tmp), max_turns=3)
            memory.add("user", "one")
            memory.add("assistant", "two")
            memory.add("user", "three")
            memory.add("assistant", "four")

            recent = memory.recent(10)
            self.assertEqual(len(recent), 3)
            self.assertEqual([item["text"] for item in recent], ["two", "three", "four"])


if __name__ == "__main__":
    unittest.main()
