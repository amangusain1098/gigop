from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gigoptimizer.assistant import AIAssistant, RAGHit, RAGIndex
from gigoptimizer.assistant.client import LLMResponse
from gigoptimizer.assistant.training import AssistantTrainer


class _FakeRepo:
    def __init__(self, knowledge):
        self._k = knowledge

    def list_knowledge_documents(self, *, limit=500):
        return list(self._k)


class RAGIndexLoadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = Path(self.tmp.name)
        knowledge = [
            {
                "title": "PageSpeed basics",
                "content": (
                    "Core Web Vitals are LCP, CLS, and INP. Optimize LCP by "
                    "preloading the hero image and inlining critical CSS."
                ),
            },
            {
                "title": "Fiverr SEO",
                "content": (
                    "Lead with the outcome. Fiverr titles convert best when the "
                    "first 40 characters include the proof metric and long-tail "
                    "keyword."
                ),
            },
            {
                "title": "Twitter hooks",
                "content": (
                    "Great Twitter hooks lead with a pain or a stat. Founders "
                    "engage with content that mentions lost conversions or revenue."
                ),
            },
        ]
        trainer = AssistantTrainer(
            data_dir=self.data_dir,
            repository=_FakeRepo(knowledge),
        )
        self.report = trainer.train()
        self.index = RAGIndex.load(
            index_path=self.report.rag_index_path,
            chunks_path=self.report.rag_chunks_path,
        )

    def test_loaded_index_has_chunks(self):
        self.assertGreaterEqual(self.index.n_chunks, 3)
        self.assertFalse(self.index.is_empty())

    def test_pagespeed_query_retrieves_lcp_chunk(self):
        hits = self.index.search("how do I fix my LCP and core web vitals", k=3)
        self.assertTrue(hits)
        top = hits[0]
        self.assertIsInstance(top, RAGHit)
        self.assertIn("PageSpeed", top.title)
        self.assertGreater(top.score, 0)
        self.assertEqual(top.rank, 1)

    def test_fiverr_query_retrieves_seo_chunk(self):
        hits = self.index.search("how should I write my Fiverr title", k=2)
        self.assertTrue(hits)
        self.assertIn("Fiverr", hits[0].title)

    def test_twitter_query_retrieves_twitter_chunk(self):
        hits = self.index.search("what makes a great twitter hook for founders", k=2)
        self.assertTrue(hits)
        self.assertIn("Twitter", hits[0].title)

    def test_unknown_query_returns_empty(self):
        hits = self.index.search("zzzzunknownwordz", k=3)
        self.assertEqual(hits, [])

    def test_empty_query_returns_empty(self):
        self.assertEqual(self.index.search("", k=3), [])

    def test_render_context_formats_hits(self):
        block = self.index.render_context("LCP fix for WordPress", k=2)
        self.assertIn("Knowledge base excerpts", block)
        self.assertIn("[1]", block)

    def test_empty_index_is_safe(self):
        empty = RAGIndex.empty()
        self.assertTrue(empty.is_empty())
        self.assertEqual(empty.search("anything", k=3), [])
        self.assertEqual(empty.render_context("anything"), "")


class _CannedClient:
    name = "canned"
    model = "canned-1"

    def __init__(self):
        self.last_messages = None

    def complete(self, messages, *, temperature=0.4, max_tokens=1024):
        self.last_messages = messages
        return LLMResponse(
            text=(
                "Analysis:\n- ok\n"
                "Problems:\n- ok\n"
                "Optimized Version:\n- do it\n"
                "Action Steps:\n1. ship\n"
            ),
            model=self.model,
            provider=self.name,
        )


class AssistantRAGIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = Path(self.tmp.name)
        knowledge = [
            {
                "title": "PageSpeed recipe",
                "content": (
                    "Fix LCP by preloading the hero image. Fix CLS by reserving "
                    "space for images. Fix INP by deferring long JS tasks."
                ),
            }
        ]
        trainer = AssistantTrainer(
            data_dir=self.data_dir,
            repository=_FakeRepo(knowledge),
        )
        self.report = trainer.train()
        self.index = RAGIndex.load(
            index_path=self.report.rag_index_path,
            chunks_path=self.report.rag_chunks_path,
        )

    def test_ask_with_rag_injects_context_into_prompt(self):
        client = _CannedClient()
        assistant = AIAssistant(client=client, rag_index=self.index)
        envelope = assistant.ask("How do I fix my LCP?")
        self.assertEqual(envelope.feature, "ask")
        # The canned client stored the exact messages it saw.
        user_msg = client.last_messages[-1].content
        self.assertIn("Knowledge base excerpts", user_msg)
        self.assertIn("LCP", user_msg)
        self.assertIn("preloading", user_msg)

    def test_ask_skips_rag_when_explicit_context_given(self):
        client = _CannedClient()
        assistant = AIAssistant(client=client, rag_index=self.index)
        assistant.ask("How do I fix my LCP?", context="custom context block")
        user_msg = client.last_messages[-1].content
        self.assertIn("custom context block", user_msg)
        self.assertNotIn("Knowledge base excerpts", user_msg)

    def test_ask_skips_rag_when_use_rag_false(self):
        client = _CannedClient()
        assistant = AIAssistant(client=client, rag_index=self.index)
        assistant.ask("How do I fix my LCP?", use_rag=False)
        user_msg = client.last_messages[-1].content
        self.assertNotIn("Knowledge base excerpts", user_msg)

    def test_ask_without_index_works(self):
        client = _CannedClient()
        assistant = AIAssistant(client=client)
        envelope = assistant.ask("What is a gig?")
        self.assertEqual(envelope.feature, "ask")


if __name__ == "__main__":
    unittest.main()
