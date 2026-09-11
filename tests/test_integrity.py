import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from report.generate import generate
from runner.audit import audit_run
from runner.io import read_jsonl, write_json
from runner.providers.base import ModelConfig
from runner.run import run
from scoring.human import assess, create_queue
from scoring.judge import grade_run
from tests.test_confidence import FakeProvider
from tests.test_scoring import FakeJudge


class IntegrityTests(unittest.TestCase):
    def fixture(self, folder):
        run("dataset/draft-v0.1-batch01.jsonl", ModelConfig("ollama", "fixture", "local", interval_seconds=0),
            folder, samples=2, limit=6, allow_unreviewed=True, provider=FakeProvider())
        grade_run(folder, ModelConfig("ollama", "judge", "local", interval_seconds=0), provider=FakeJudge())
        create_queue(folder)
        assess(folder, resamples=20)

    def test_rejects_modified_confidence_and_duplicate_raw_samples(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(tmp) / "run"
            self.fixture(folder)
            self.assertEqual(audit_run(folder)["n_questions"], 6)
            path = folder / "responses.jsonl"
            original = path.read_bytes()
            rows = read_jsonl(path)
            rows[0]["primary"]["confidence"] = 0.01
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "derived responses"):
                audit_run(folder)
            path.write_bytes(original)
            raw = folder / "raw.jsonl"
            with raw.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(read_jsonl(raw)[0]) + "\n")
            with self.assertRaisesRegex(ValueError, "duplicate raw"):
                audit_run(folder)

    def test_rejects_stale_or_altered_scores_even_when_counts_match(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(tmp) / "run"
            self.fixture(folder)
            path = folder / "grading/scored.json"
            scores = json.loads(path.read_text(encoding="utf-8"))
            scores["rows"][0]["grade"] = "incorrect"
            write_json(path, scores)
            with self.assertRaisesRegex(ValueError, "original judgment"):
                generate([folder], Path(tmp) / "out", resamples=20)
            assess(folder, resamples=20)
            judge_path = folder / "grading/judge_scores.jsonl"
            rows = read_jsonl(judge_path)
            rows[0]["grade"] = "incorrect"
            judge_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale or unaudited"):
                generate([folder], Path(tmp) / "out", resamples=20)
