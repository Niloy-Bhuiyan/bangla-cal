"""Interface integration tests use temporary data and synthetic reviewers only."""

import contextlib
from datetime import date
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dataset.review import CHECKS, assess_reviews, question_hash
from interface.server import ROOT, Workspace, make_server
from interface.worker import assessment, execute
from runner.io import read_jsonl
from runner.providers.base import ModelConfig
from runner.run import run
from scoring.human import create_queue
from scoring.judge import grade_run
from tests.test_confidence import FakeProvider
from tests.test_scoring import FakeJudge


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "dataset", self.root / "dataset")
        self.workspace = Workspace(self.root)

    def tearDown(self):
        self.workspace.stop()
        self.tmp.cleanup()

    def fixture(self):
        folder = self.root / "results/archive/fixture"
        with contextlib.redirect_stdout(io.StringIO()):
            run("dataset/draft-v0.1-batch01.jsonl", ModelConfig("ollama", "fixture", "local", interval_seconds=0),
                folder, samples=2, limit=6, allow_unreviewed=True, provider=FakeProvider())
            grade_run(folder, ModelConfig("ollama", "judge", "local", interval_seconds=0), provider=FakeJudge())
            create_queue(folder)
        return "results/archive/fixture", folder

    def test_submission_is_version_bound_independent_and_never_changes_dataset(self):
        key = "dataset/draft-v0.1-batch01.jsonl"
        source = (self.root / key).read_bytes()
        q = self.workspace.dataset(key)[0]
        data = {"dataset": key, "question_id": q["id"], "question_sha256": question_hash(q),
                "reviewer_id": "synthetic-interface-test", "native_bengali_speaker": True,
                "reviewed_at": date.today().isoformat(), "decision": "accept",
                "checks": dict.fromkeys(CHECKS, True), "rationale": "Synthetic test fixture; not a real review."}
        with self.assertRaisesRegex(ValueError, "Question changed"):
            self.workspace.mutate("review", {**data, "question_sha256": "stale"})
        with self.assertRaisesRegex(ValueError, "native Bengali"):
            self.workspace.mutate("review", {**data, "native_bengali_speaker": False})
        result = self.workspace.mutate("review", data)
        self.assertEqual(len(read_jsonl(self.root / result["file"])), 1)
        self.assertEqual((self.root / key).read_bytes(), source)
        with self.assertRaisesRegex(ValueError, "first decision"):
            self.workspace.mutate("review", data)
        public = self.workspace.dataset(key)
        self.assertTrue(all(not row["reviewed_by"] for row in public))
        public[0]["source_note"] += " Changed synthetic reference for a new test revision."
        (self.root / key).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in public), encoding="utf-8")
        fresh = self.workspace.mutate("review", {**data, "question_sha256": question_hash(public[0])})
        self.assertNotEqual(result["file"], fresh["file"])
        self.assertEqual(len(read_jsonl(self.root / result["file"])), 1)
        assess_reviews(public, [self.root / fresh["file"]])

    def test_archive_is_read_only_and_blinded_grades_reach_assessment(self):
        key, archive = self.fixture()
        with self.assertRaisesRegex(ValueError, "archived run"):
            self.workspace.mutate("assess", {"run": key})
        copied = self.workspace.mutate("clone", {"run": key})["run"]
        queue = self.workspace.queue(copied)
        row = queue["rows"][0]
        self.assertIsNone(row["grade"])
        self.assertNotIn("confidence", row)
        data = {"run": copied, "question_id": row["question_id"], "response_sha256": row["response_sha256"],
                "reviewer_id": "synthetic-human-test", "reviewed_at": date.today().isoformat(),
                "grade": "correct", "abstained": False, "behavior_met": True,
                "specific_unfounded": False, "confident_language": False,
                "rationale": "Synthetic test, not an actual human submission."}
        self.workspace.mutate("grade", data)
        with self.assertRaisesRegex(ValueError, "already graded"):
            self.workspace.mutate("grade", data)
        with contextlib.redirect_stdout(io.StringIO()):
            assessment(self.root / copied)
            assessment(self.root / copied)
        scored = json.loads((self.root / copied / "grading/scored.json").read_text(encoding="utf-8"))
        self.assertEqual(len(scored["human_reviews"]), 1)
        self.assertEqual(scored["human_reviews"][0]["reviewer_id"], "synthetic-human-test")
        self.assertFalse((archive / "grading/interface_human.jsonl").exists())

    def test_run_form_validates_and_dispatches_only_allowed_providers(self):
        data = {"dataset": "dataset/draft-v0.1-batch01.jsonl", "name": "fixture", "provider": "ollama",
                "model": "fixture", "samples": 3, "limit": 24, "allow_unreviewed": True}
        with patch.object(self.workspace, "start", return_value={}) as start:
            self.workspace.mutate("generate", data)
            payload = start.call_args.args[1]
            self.assertEqual(payload["output"], "results/local/fixture")
            self.assertEqual(payload["config"]["tier"], "local")
            with self.assertRaises(ValueError):
                self.workspace.mutate("generate", {**data, "provider": "openai"})
            with self.assertRaises(ValueError):
                self.workspace.mutate("generate", {**data, "name": "../../outside"})
            with self.assertRaisesRegex(ValueError, "two real independent"):
                self.workspace.mutate("generate", {**data, "allow_unreviewed": False})

    def test_worker_dispatch_and_background_local_assessment(self):
        with patch("interface.worker.run") as runner:
            execute({"action": "generate", "dataset": "dataset/examples.jsonl", "output": "results/local/test",
                     "config": {"provider": "ollama", "model": "fixture", "tier": "local"},
                     "samples": 3, "limit": 2, "allow_unreviewed": True})
            self.assertEqual(runner.call_args.kwargs["samples"], 3)
        key, _ = self.fixture()
        copied = self.workspace.mutate("clone", {"run": key})["run"]
        with patch.dict("os.environ", {"PYTHONPATH": str(ROOT)}):
            self.workspace.mutate("assess", {"run": copied})
            with self.assertRaisesRegex(ValueError, "task is running"):
                self.workspace.mutate("assess", {"run": copied})
            deadline = time.monotonic() + 20
            while self.workspace.job["status"] == "running" and time.monotonic() < deadline:
                time.sleep(0.05)
        self.assertEqual(self.workspace.job["status"], "complete", self.workspace.job_status())
        self.assertTrue((self.root / copied / "grading/scored.json").exists())

    def test_http_rejects_cross_origin_writes_and_arbitrary_files(self):
        server = make_server(self.workspace, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", server.server_port)
        try:
            connection.request("GET", "/api/state")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            state = json.loads(response.read())
            for path in ("/.env", "/../.env", "/artifact?report=../&file=.env"):
                connection.request("GET", path)
                response = connection.getresponse()
                self.assertIn(response.status, (400, 404))
                response.read()
            connection.request("GET", "/api/state", headers={"Host": "evil.example"})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            for extra in ({}, {"X-Workspace-Token": state["token"], "Origin": "https://evil.example"}):
                connection.request("POST", "/api/clone", "{}", {"Content-Type": "application/json", **extra})
                response = connection.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
            connection.request("GET", "/")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
            self.assertIn(b"app.js", response.read())
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join()
