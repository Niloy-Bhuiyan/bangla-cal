import json
import tempfile
import unittest

from runner.confidence import make_prompt, normalize_answer, parse_response, sampling_agreement
from runner.io import read_jsonl
from runner.providers.base import ModelConfig, Response
from runner.run import run


class FakeProvider:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt, temperature):
        self.calls += 1
        text = json.dumps({"answer_bn": "৪২", "confidence": 80, "action": "answer"})
        return Response(text, {"fixture": True}, "synthetic-only", "stop", {})


class ConfidenceTests(unittest.TestCase):
    def test_parser_and_invalid_values(self):
        row = {"answer_bn": "৪২", "confidence": "৮০", "action": "answer"}
        self.assertEqual(parse_response(json.dumps(row))["confidence"], 0.8)
        for value in [True, -1, 101, "NaN", None]:
            with self.assertRaises((ValueError, TypeError)):
                parse_response(json.dumps({**row, "confidence": value}))
        with self.assertRaises(ValueError):
            parse_response(json.dumps(row), "length")

    def test_agreement_is_primary_matching_not_modal_confidence(self):
        primary = {"answer_bn": "৪২", "action": "answer"}
        different = {"answer_bn": "43", "action": "answer"}
        result = sampling_agreement(primary, [primary, different, different])
        self.assertAlmostEqual(result["self_consistency"], 1 / 3)
        self.assertAlmostEqual(result["modal_agreement"], 2 / 3)
        self.assertIsNone(sampling_agreement(primary, [None])["self_consistency"])
        self.assertNotEqual(normalize_answer("-1"), normalize_answer("1"))
        self.assertNotEqual(normalize_answer("1.2"), normalize_answer("12"))

    def test_no_ground_truth_leakage(self):
        prompt = make_prompt({"question_bn": "প্রশ্ন?", "ground_truth_answer": "SECRET_TRUTH",
                              "question_en_gloss": "SECRET_GLOSS"})
        self.assertNotIn("SECRET", prompt)

    def test_raw_logging_and_resume_without_duplicate_calls(self):
        fake = FakeProvider()
        config = ModelConfig("ollama", "test", "local", interval_seconds=0)
        with tempfile.TemporaryDirectory() as folder:
            run("dataset/draft-v0.1-batch01.jsonl", config, folder, samples=2,
                limit=2, allow_unreviewed=True, provider=fake)
            self.assertEqual(fake.calls, 6)
            self.assertEqual(len(read_jsonl(folder + "/raw.jsonl")), 6)
            run("dataset/draft-v0.1-batch01.jsonl", config, folder, samples=2,
                limit=2, allow_unreviewed=True, resume=True, provider=fake)
            self.assertEqual(fake.calls, 6)
            with self.assertRaises(ValueError):
                run("dataset/draft-v0.1-batch01.jsonl", config, folder, samples=3,
                    limit=2, allow_unreviewed=True, resume=True, provider=fake)
