import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from report.generate import generate
from runner.providers.base import ModelConfig
from runner.run import run
from scoring.human import assess, create_queue
from scoring.judge import grade_run
from tests.test_confidence import FakeProvider
from tests.test_scoring import FakeJudge


class ReportTests(unittest.TestCase):
    def test_report_uses_scores_preserves_pending_and_rejects_release(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            source, out = Path(folder) / "fixture-run", Path(folder) / "report"
            run("dataset/draft-v0.1-batch01.jsonl", ModelConfig("ollama", "fixture", "local", interval_seconds=0),
                source, samples=2, limit=6, allow_unreviewed=True, provider=FakeProvider())
            grade_run(source, ModelConfig("ollama", "judge", "local", interval_seconds=0), provider=FakeJudge())
            create_queue(source)
            assess(source, resamples=20)
            with self.assertRaises(ValueError):
                generate([source], out, resamples=20, release=True)
            result = generate([source], out, resamples=20)
            self.assertEqual(result["ollama/fixture/overall"]["n_scored"], 6)
            report = (out / "REPORT.md").read_text(encoding="utf-8")
            self.assertIn("PRELIMINARY, UNREVIEWED DATA", report)
            self.assertIn("PENDING HUMAN VALIDATION", report)
            self.assertIn("unavailable", report)
            self.assertTrue((out / "calibration.png").stat().st_size > 1000)
            metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["resamples"], 20)
