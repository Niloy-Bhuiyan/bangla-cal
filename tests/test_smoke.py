"""Integration fixtures exercise failures; they are never published as real runs."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from runner.io import read_jsonl
from runner.providers.base import ModelConfig, ProviderError
from runner.run import run
from scoring.human import assess, create_queue
from scoring.judge import grade_run
from tests.test_confidence import FakeProvider
from tests.test_scoring import FakeJudge


class InterruptedProvider(FakeProvider):
    def generate(self, prompt, temperature):
        if self.calls == 1:
            raise ProviderError(429, "synthetic quota error", {"Retry-After": "60"})
        return super().generate(prompt, temperature)


class SmokeTests(unittest.TestCase):
    def test_resume_reuses_raw_sample_after_quota_interruption(self):
        config = ModelConfig("ollama", "fixture", "local", interval_seconds=0)
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ProviderError):
                run("dataset/draft-v0.1-batch01.jsonl", config, folder, samples=2,
                    limit=1, allow_unreviewed=True, provider=InterruptedProvider())
            self.assertEqual(len(read_jsonl(Path(folder) / "raw.jsonl")), 1)
            self.assertEqual(read_jsonl(Path(folder) / "errors.jsonl")[0]["status"], 429)
            fake = FakeProvider()
            run("dataset/draft-v0.1-batch01.jsonl", config, folder, samples=2,
                limit=1, allow_unreviewed=True, resume=True, provider=fake)
            self.assertEqual(fake.calls, 2)
            self.assertEqual(len(read_jsonl(Path(folder) / "raw.jsonl")), 3)

    def test_actual_human_input_path_agreement_and_expansion_with_synthetic_grades(self):
        # These temporary unit-test identities are explicitly synthetic, not reviews.
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            run("dataset/draft-v0.1-batch01.jsonl", ModelConfig("ollama", "fixture", "local", interval_seconds=0),
                folder, samples=2, limit=20, allow_unreviewed=True, provider=FakeProvider())
            grade_run(folder, ModelConfig("ollama", "judge", "local", interval_seconds=0), provider=FakeJudge())
            queue = create_queue(folder)
            plan = json.loads((Path(folder) / "grading/validation_plan.json").read_text(encoding="utf-8"))
            disagree_id = plan["random_ids"][0]
            def fill(entries):
                for entry in entries:
                    entry.update(grade="incorrect" if entry["question_id"] == disagree_id else "correct",
                                 abstained=False, behavior_met=True, specific_unfounded=False,
                                 confident_language=False, rationale="Synthetic fixture, not a real human grade",
                                 reviewer_id="SYNTHETIC_TEST_ONLY", reviewed_at="2026-09-11",
                                 resolution_note="Synthetic adjudication fixture")
                path = Path(folder) / "synthetic-completed.jsonl"
                path.write_text("\n".join(json.dumps(r) for r in entries) + "\n", encoding="utf-8")
                return path
            result = assess(folder, fill(queue), resamples=100)
            self.assertAlmostEqual(result["agreement"]["grade"]["estimate"], 2 / 3)
            self.assertEqual(result["status"], "EXPAND HUMAN GRADING: LOW AGREEMENT")
            expanded = create_queue(folder, expand=True)
            result = assess(folder, fill(expanded), resamples=100)
            self.assertEqual(result["status"], "HUMAN GRADED; JUDGE LOW AGREEMENT")
            self.assertEqual(result["random_sample_size"], 3)
            self.assertEqual(result["human_completed"], 20)
            expanded[0]["response_text"] = "tampered"
            with self.assertRaises(ValueError):
                assess(folder, fill(expanded), resamples=20)
