import os
import unittest
from unittest.mock import patch

from runner.providers.base import ModelConfig, ProviderError, get_provider
from runner.providers.future import FuturePaidProvider


class ProviderTests(unittest.TestCase):
    def test_paid_and_cloud_rejected(self):
        for args in [("openai", "gpt", "free"), ("groq", "qwen", "paid"),
                     ("ollama", "anything:cloud", "local")]:
            with self.assertRaises(ValueError):
                ModelConfig(*args)
        with self.assertRaises(NotImplementedError):
            FuturePaidProvider()

    def test_secret_redaction(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "private-test-value"}):
            self.assertNotIn("private-test-value", str(ProviderError(401, "key=private-test-value")))

    def test_gemini_raw_and_empty_block(self):
        raw = {"modelVersion": "snapshot", "candidates": [{"content": {"parts": [
            {"text": "hidden", "thought": True}, {"text": '{"answer":"x"}'}]},
            "finishReason": "STOP"}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test"}), patch(
            "runner.providers.gemini.request_json", return_value=(raw, {})) as request:
            result = get_provider(ModelConfig("gemini", "example")).generate("question")
            self.assertEqual(result.text, '{"answer":"x"}')
            self.assertEqual(result.model_version, "snapshot")
            self.assertEqual(result.raw, raw)
            self.assertNotIn("test", request.call_args.args[0])

    def test_groq_and_ollama_mapping(self):
        raw = {"model": "snapshot", "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
        with patch.dict(os.environ, {"GROQ_API_KEY": "test"}), patch(
            "runner.providers.groq.request_json", return_value=(raw, {})):
            self.assertEqual(get_provider(ModelConfig("groq", "example")).generate("q").text, "{}")
        with patch("runner.providers.ollama.request_json", return_value=(
            {"message": {"content": "{}"}, "done_reason": "stop"}, {})) as request:
            get_provider(ModelConfig("ollama", "qwen3:0.6b", "local")).generate("q")
            self.assertTrue(request.call_args.args[0].startswith("http://127.0.0.1:"))
