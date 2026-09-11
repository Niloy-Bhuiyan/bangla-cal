import json
from pathlib import Path
import tempfile
import unittest

from runner.io import read_jsonl
from runner.providers.base import ModelConfig, Response
from runner.run import run
from scoring.human import assess, create_queue, kappa
from scoring.judge import grade_run, validate_grade
from tests.test_confidence import FakeProvider


class FakeJudge:
    def generate(self, prompt, temperature):
        text = json.dumps({"grade": "correct", "abstained": False, "behavior_met": True,
                           "specific_unfounded": False, "confident_language": False, "rationale": "Synthetic test only"})
        return Response(text, {"fixture": True}, "synthetic-judge", "stop", {})


class ScoringTests(unittest.TestCase):
    def test_kappa_and_grade_validation(self):
        self.assertEqual(kappa([("a", "a"), ("b", "b")]), 1)
        self.assertEqual(kappa([("a", "b"), ("b", "a")]), -1)
        self.assertIsNone(kappa([]))
        with self.assertRaises(ValueError):
            validate_grade({"grade": "correct", "abstained": "false"})

    def test_blind_queue_pending_agreement_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            subject = ModelConfig("ollama", "fixture", "local", interval_seconds=0)
            judge = ModelConfig("ollama", "judge", "local", interval_seconds=0)
            run("dataset/draft-v0.1-batch01.jsonl", subject, folder, samples=2,
                limit=12, allow_unreviewed=True, provider=FakeProvider())
            with self.assertRaises(ValueError):
                grade_run(folder, subject, provider=FakeJudge())
            grade_run(folder, judge, provider=FakeJudge())
            queue = create_queue(folder)
            self.assertGreaterEqual(len(queue), 6)
            for entry in queue:
                self.assertNotIn("judge_model", entry)
                self.assertIsNone(entry["grade"])
                self.assertIsNone(entry["reviewer_id"])
            with self.assertRaises(ValueError):
                create_queue(folder)
            result = assess(folder, resamples=20)
            self.assertEqual(result["human_completed"], 0)
            self.assertEqual(result["status"], "PENDING HUMAN VALIDATION")
            self.assertIsNone(result["agreement"]["grade"]["estimate"])
            scored = json.loads((Path(folder) / "grading/scored.json").read_text(encoding="utf-8"))
            self.assertEqual(len(scored["rows"]), 12)
            self.assertTrue(all(r["grade_source"] == "judge" for r in scored["rows"]))
