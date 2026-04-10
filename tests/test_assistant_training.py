from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gigoptimizer.assistant.training import (
    AssistantTrainer,
    TrainingExample,
    TrainingReport,
)


class FakeRepository:
    """Repository double exposing the methods the trainer probes for."""

    def __init__(
        self,
        *,
        messages=None,
        feedback=None,
        knowledge=None,
        gigs=None,
        reports=None,
    ) -> None:
        self._messages = messages or []
        self._feedback = feedback or []
        self._knowledge = knowledge or []
        self._gigs = gigs or []
        self._reports = reports or []

    def list_assistant_messages(self, *, gig_id=None, limit=500):
        return list(self._messages)

    def list_assistant_feedback(self, *, gig_id=None, limit=500):
        return list(self._feedback)

    def list_knowledge_documents(self, *, limit=500):
        return list(self._knowledge)

    def list_gig_snapshots(self, *, limit=100):
        return list(self._gigs)

    def list_optimization_reports(self, *, limit=100):
        return list(self._reports)


class ExplodingRepository:
    def list_assistant_messages(self, *, gig_id=None, limit=500):
        raise RuntimeError("db is down")

    def list_knowledge_documents(self, *, limit=500):
        raise RuntimeError("db is down")


class TrainingExampleTests(unittest.TestCase):
    def test_to_chat_messages_includes_system_prompt(self) -> None:
        ex = TrainingExample(
            instruction="Optimize my gig",
            input="Title: slow site",
            output="Analysis:\n- do better",
        )
        messages = ex.to_chat_messages()
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("GigOptimizer AI", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("Optimize my gig", messages[1]["content"])
        self.assertIn("Title: slow site", messages[1]["content"])
        self.assertEqual(messages[2]["role"], "assistant")


class AssistantTrainerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = Path(self.tmp.name)

    # ------------------------------------------------------------------
    # Dataset export
    # ------------------------------------------------------------------
    def test_seed_only_dataset_is_never_empty(self) -> None:
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=None)
        examples = trainer.export_dataset()
        self.assertGreaterEqual(len(examples), 3)
        self.assertTrue(all(ex.output for ex in examples))

    def test_extra_examples_are_included(self) -> None:
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=None)
        extra = [
            TrainingExample(
                instruction="Write a CTA",
                input="",
                output="Action Steps:\n1. Book today.",
                source="manual",
            )
        ]
        examples = trainer.export_dataset(extra_examples=extra)
        self.assertTrue(any(ex.source == "manual" for ex in examples))

    def test_examples_dedup_on_instruction_and_input(self) -> None:
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=None)
        dup = TrainingExample(
            instruction="Optimize this Fiverr gig title for a WordPress speed audit service.",
            input="Title: I will make your WordPress fast\nTags: wordpress, speed, seo",
            output="different",
        )
        examples = trainer.export_dataset(extra_examples=[dup])
        keys = [(ex.instruction.strip(), ex.input.strip()) for ex in examples]
        self.assertEqual(len(keys), len(set(keys)))

    def test_assistant_message_pairs_are_harvested(self) -> None:
        # Messages come back from the repo in reverse-chronological order.
        messages = [
            {"id": 2, "role": "assistant", "content": "Analysis:\n- do this", "topic": "seo"},
            {"id": 1, "role": "user", "content": "How do I rank higher?", "topic": "seo"},
        ]
        repo = FakeRepository(messages=messages)
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=repo)
        examples = trainer.export_dataset()
        harvested = [ex for ex in examples if ex.source == "assistant_history"]
        self.assertEqual(len(harvested), 1)
        self.assertEqual(harvested[0].instruction, "How do I rank higher?")

    def test_negative_feedback_filters_assistant_turn(self) -> None:
        messages = [
            {"id": 2, "role": "assistant", "content": "bad answer", "topic": "seo"},
            {"id": 1, "role": "user", "content": "q", "topic": "seo"},
        ]
        feedback = [{"message_id": 2, "verdict": "down"}]
        repo = FakeRepository(messages=messages, feedback=feedback)
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=repo)
        examples = trainer.export_dataset()
        self.assertFalse(any(ex.source == "assistant_history" for ex in examples))

    def test_pii_is_redacted_from_harvested_examples(self) -> None:
        messages = [
            {
                "id": 2,
                "role": "assistant",
                "content": "email me at hi@example.com or call +1 555 123 4567",
                "topic": "general",
            },
            {
                "id": 1,
                "role": "user",
                "content": "contact: https://secret.example.com/page",
                "topic": "general",
            },
        ]
        repo = FakeRepository(messages=messages)
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=repo)
        examples = trainer.export_dataset()
        harvested = [ex for ex in examples if ex.source == "assistant_history"][0]
        self.assertNotIn("hi@example.com", harvested.output)
        self.assertNotIn("secret.example.com", harvested.instruction)
        self.assertIn("[email]", harvested.output)
        self.assertIn("[url]", harvested.instruction)

    def test_exploding_repo_does_not_break_dataset(self) -> None:
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=ExplodingRepository())
        examples = trainer.export_dataset()
        # Seed examples still come through.
        self.assertGreaterEqual(len(examples), 3)

    # ------------------------------------------------------------------
    # Full train() pipeline
    # ------------------------------------------------------------------
    def test_train_writes_all_artifacts(self) -> None:
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=None)
        report = trainer.train()
        self.assertIsInstance(report, TrainingReport)
        for path_str in report.created_files:
            path = Path(path_str)
            self.assertTrue(path.exists(), f"expected {path} to exist")
        self.assertTrue(Path(report.modelfile_path).exists())
        self.assertTrue(Path(report.dataset_path).exists())
        self.assertTrue(Path(report.rag_index_path).exists())

    def test_train_modelfile_contains_system_prompt_and_base(self) -> None:
        trainer = AssistantTrainer(
            data_dir=self.data_dir,
            repository=None,
            base_model="llama3.1:8b",
            custom_model_name="gigoptimizer-test",
        )
        report = trainer.train()
        modelfile = Path(report.modelfile_path).read_text(encoding="utf-8")
        self.assertIn("FROM llama3.1:8b", modelfile)
        self.assertIn("GigOptimizer AI", modelfile)
        self.assertIn("gigoptimizer-test", modelfile)
        self.assertIn("MESSAGE user", modelfile)
        self.assertIn("MESSAGE assistant", modelfile)

    def test_train_dataset_jsonl_is_valid(self) -> None:
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=None)
        report = trainer.train()
        lines = Path(report.dataset_path).read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len(lines), 3)
        for line in lines:
            row = json.loads(line)
            self.assertIn("instruction", row)
            self.assertIn("output", row)

    def test_train_chat_format_is_valid(self) -> None:
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=None)
        trainer.train()
        chat_path = self.data_dir / "assistant" / "dataset.chat.jsonl"
        lines = chat_path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines)
        for line in lines:
            row = json.loads(line)
            msgs = row["messages"]
            self.assertEqual([m["role"] for m in msgs], ["system", "user", "assistant"])

    def test_train_rag_index_is_built_from_knowledge_docs(self) -> None:
        knowledge = [
            {
                "title": "PageSpeed basics",
                "content": (
                    "Core Web Vitals are LCP, CLS, and INP. "
                    "Optimize the LCP element first by preloading it. "
                    "Inline critical CSS to avoid render blocking."
                ),
            },
            {
                "title": "Fiverr SEO",
                "body": "Lead with the outcome in your title. Use 5 intent-matched tags.",
            },
        ]
        repo = FakeRepository(knowledge=knowledge)
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=repo)
        report = trainer.train()
        self.assertGreaterEqual(report.total_rag_chunks, 2)
        index = json.loads(Path(report.rag_index_path).read_text(encoding="utf-8"))
        self.assertEqual(index["schema_version"], 1)
        self.assertIn("vocabulary", index)
        self.assertIn("doc_weights", index)
        self.assertIn("postings", index)
        self.assertGreater(len(index["vocabulary"]), 5)
        # Vocabulary should include product-relevant words.
        vocab = set(index["vocabulary"])
        self.assertTrue({"core", "web", "vitals"}.issubset(vocab) or "pagespeed" in vocab)

    def test_train_empty_knowledge_warns(self) -> None:
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=None)
        report = trainer.train()
        self.assertTrue(any("RAG" in w for w in report.warnings))
        self.assertEqual(report.total_rag_chunks, 0)

    def test_rag_chunks_respect_max_chunk_chars(self) -> None:
        big_text = "Core Web Vitals. " * 500
        repo = FakeRepository(knowledge=[{"title": "big", "content": big_text}])
        trainer = AssistantTrainer(data_dir=self.data_dir, repository=repo)
        report = trainer.train()
        chunks_path = Path(report.rag_chunks_path)
        lines = chunks_path.read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(lines), 1)
        for line in lines:
            row = json.loads(line)
            self.assertLessEqual(len(row["text"]), trainer.MAX_CHUNK_CHARS + 50)


if __name__ == "__main__":
    unittest.main()
