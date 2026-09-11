"""Serve the research workspace on loopback; no keys or arbitrary files are served."""

import argparse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlsplit

from dataset.review import assess_reviews, question_hash
from dataset.validate import load_questions
from runner.io import append_jsonl, digest, now, read_jsonl, write_json
from runner.providers.base import ModelConfig, load_secrets, redact
from scoring.judge import FIELDS, validate_grade

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).with_name("static")


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def required(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ValueError(f"Enter {name}.")
    return value.strip()


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return value


class Workspace:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.local = self.root / "results/local/interface"
        self.lock = threading.RLock()
        self.process = None
        self.job = read_json(self.local / "job.json", {"status": "idle"})
        if self.job["status"] == "running":
            self.job["status"] = "interrupted"

    def catalog(self, base, pattern):
        return {p.parent.relative_to(self.root).as_posix(): p.parent
                for p in (self.root / base).rglob(pattern)
                if p.resolve().is_relative_to(self.root / base)}

    def datasets(self):
        return {p.relative_to(self.root).as_posix(): p for p in (self.root / "dataset").glob("*.jsonl")}

    def dataset(self, key):
        if key not in self.datasets():
            raise ValueError("Choose an available dataset.")
        return load_questions(self.datasets()[key])

    def run_folder(self, key, writable=False):
        runs = self.catalog("results", "manifest.json")
        if key not in runs:
            raise ValueError("Choose an available run.")
        folder = runs[key]
        if writable and not folder.is_relative_to(self.root / "results/local"):
            raise ValueError("This is an archived run. Create a local working copy first.")
        return folder

    def available(self):
        runs = []
        for key, folder in self.catalog("results", "manifest.json").items():
            manifest = read_json(folder / "manifest.json")
            agreement = read_json(folder / "grading/agreement.json", {})
            runs.append({"id": key, "label": manifest["label"], "status": manifest["status"],
                         "config": manifest["plan"]["config"], "planned": len(manifest["plan"]["selected_ids"]),
                         "completed": len(read_jsonl(folder / "responses.jsonl")),
                         "judged": len(read_jsonl(folder / "grading/judge_scores.jsonl")),
                         "human": agreement.get("human_completed", 0),
                         "agreement_status": agreement.get("status", "Not assessed"),
                         "local": folder.is_relative_to(self.root / "results/local"),
                         "has_queue": (folder / "grading/validation_plan.json").exists()})
        return {"datasets": [{"id": key, "count": len(load_questions(path))} for key, path in self.datasets().items()],
                "runs": runs, "reports": list(self.catalog("report", "metrics.json")),
                "credentials": {name: bool(os.environ.get(name.upper() + "_API_KEY")) for name in ("gemini", "groq")},
                "job": self.job_status()}

    def idle(self):
        if self.job["status"] == "running":
            raise ValueError("A task is running. Wait for it to finish or stop it first.")

    def job_status(self):
        log = self.local / "task.log"
        # Keep browser responses bounded even after a long evaluation.
        tail = ""
        if log.exists():
            with log.open("rb") as stream:
                stream.seek(max(0, log.stat().st_size - 16000))
                tail = redact(stream.read().decode("utf-8", errors="replace"))
        return {**self.job, "log": tail}

    def start(self, action, payload):
        self.idle()
        self.local.mkdir(parents=True, exist_ok=True)
        write_json(self.local / "request.json", {"action": action, **payload})
        self.job = {"status": "running", "action": action, "started_at": now()}
        write_json(self.local / "job.json", self.job)
        command = [sys.executable, "-u", "-m", "interface.worker", str(self.local / "request.json")]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            with (self.local / "task.log").open("w", encoding="utf-8") as log:
                self.process = subprocess.Popen(command, cwd=self.root, stdout=log, stderr=subprocess.STDOUT,
                                                creationflags=flags, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        except OSError:
            self.job["status"] = "failed"
            write_json(self.local / "job.json", self.job)
            raise
        process = self.process

        def finish():
            code = process.wait()
            with self.lock:
                if self.process is process and self.job["status"] == "running":
                    self.job.update(status="complete" if code == 0 else "failed", exit_code=code, finished_at=now())
                    write_json(self.local / "job.json", self.job)

        threading.Thread(target=finish, daemon=True).start()
        return self.job

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=10)
            self.job.update(status="stopped", finished_at=now())
            write_json(self.local / "job.json", self.job)
        return self.job

    def queue(self, run_id):
        folder = self.run_folder(run_id)
        plan = read_json(folder / "grading/validation_plan.json")
        if not plan:
            raise ValueError("Prepare the human queue from Evaluations first.")
        completed = read_json(folder / "grading/scored.json", {}).get("human_reviews", [])
        completed += read_jsonl(folder / "grading/interface_human.jsonl")
        done = {row["question_id"] for row in completed}
        rows = read_jsonl(folder / "grading" / plan["queue_file"])
        # No original judge grades or confidence fields enter the blinded queue.
        return {"rows": [row for row in rows if row["question_id"] not in done],
                "completed": len(done), "total": len(rows)}

    def mutate(self, action, data):
        with self.lock:
            if action == "stop":
                return self.stop()
            self.idle()
            if action == "review":
                questions = self.dataset(data.get("dataset"))
                question = next((q for q in questions if q["id"] == data.get("question_id")), None)
                if question is None or question_hash(question) != data.get("question_sha256"):
                    raise ValueError("Question changed. Refresh before reviewing.")
                reviewer = required(data.get("reviewer_id"), "your reviewer ID")
                entry = {key: data.get(key) for key in ("question_id", "question_sha256", "decision",
                         "native_bengali_speaker", "reviewed_at", "checks", "rationale")}
                entry.update(reviewer_id=reviewer, status="HUMAN SUBMISSION; MAINTAINER VERIFICATION PENDING")
                # Reuse the native review validator before persisting a submission.
                import tempfile
                with tempfile.TemporaryDirectory() as tmp:
                    check = Path(tmp) / "review.jsonl"
                    append_jsonl(check, entry)
                    assess_reviews(questions, [check])
                target = self.local / "dataset-reviews" / (digest(reviewer)[:24] + ".jsonl")
                if any(r["question_id"] == entry["question_id"] and r["question_sha256"] == entry["question_sha256"]
                       for r in read_jsonl(target)):
                    raise ValueError("Your first decision for this revision is already saved. It will not be overwritten.")
                append_jsonl(target, entry)
                return {"message": "Your review was saved locally. Dataset review IDs were not changed.",
                        "file": target.relative_to(self.root).as_posix()}
            if action == "clone":
                source = self.run_folder(data.get("run"))
                target = self.root / "results/local" / (source.name + "-" + secrets.token_hex(3))
                shutil.copytree(source, target)
                return {"message": "Local working copy created.", "run": target.relative_to(self.root).as_posix()}
            if action == "grade":
                folder = self.run_folder(data.get("run"), writable=True)
                queue = self.queue(data["run"])["rows"]
                original = next((r for r in queue if r["question_id"] == data.get("question_id")), None)
                if original is None or original["response_sha256"] != data.get("response_sha256"):
                    raise ValueError("Response changed or already graded. Refresh the queue.")
                entry = {**original, **{f: data.get(f) for f in (*FIELDS, "rationale")},
                         "reviewer_id": required(data.get("reviewer_id"), "your reviewer ID"),
                         "reviewed_at": data.get("reviewed_at")}
                date.fromisoformat(required(entry["reviewed_at"], "the review date"))
                validate_grade(entry)
                append_jsonl(folder / "grading/interface_human.jsonl", entry)
                return {"message": "Human grade saved. Refresh assessment to calculate agreement."}
            if action == "generate":
                self.dataset(data.get("dataset"))
                if data.get("allow_unreviewed") is not True:
                    load_questions(self.datasets()[data["dataset"]], require_reviewed=True)
                name = required(data.get("name"), "a run name")
                if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}", name):
                    raise ValueError("Run name: use 1–60 letters, numbers, hyphens or underscores.")
                output = self.root / "results/local" / name
                if output.exists():
                    raise ValueError("That run name already exists. Choose another or resume it.")
                config = self.configuration(data)
                pilots = set(read_json(self.root / "dataset/pilot_ids.json", []))
                eligible = sum(q["id"] not in pilots for q in self.dataset(data["dataset"]))
                count = integer(data.get("limit"), "Question count (excluding held-out pilot items)", 1, eligible)
                samples = integer(data.get("samples"), "Samples per question", 2, 10)
                return self.start(action, {"dataset": data["dataset"], "output": output.relative_to(self.root).as_posix(),
                                          "config": config, "limit": count, "samples": samples,
                                          "allow_unreviewed": data.get("allow_unreviewed") is True})
            if action in ("resume", "judge", "assess", "expand", "report"):
                self.run_folder(data.get("run"), writable=True)
                payload = {"run": data["run"]}
                if action == "judge":
                    payload["config"] = self.configuration(data)
                return self.start(action, payload)
            raise ValueError("Unknown action.")

    @staticmethod
    def configuration(data):
        from dataclasses import asdict
        provider = data.get("provider")
        config = ModelConfig(provider, required(data.get("model"), "a model ID"),
                             "local" if provider == "ollama" else "free",
                             integer(data.get("max_tokens", 1024), "Token limit", 128, 8192),
                             integer(data.get("interval", 6), "Request interval", 0, 3600))
        if provider in ("gemini", "groq") and not os.environ.get(provider.upper() + "_API_KEY"):
            raise ValueError(f"Set {provider.upper()}_API_KEY in the local .env file and restart the interface.")
        return asdict(config)


def make_server(workspace, port=8765):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, body, content_type="application/json; charset=utf-8", status=200):
            if isinstance(body, (dict, list)):
                body = redact(json.dumps(body, ensure_ascii=False)).encode("utf-8")
            self.send_response(status)
            for key, value in {"Content-Type": content_type, "Content-Length": str(len(body)),
                               "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                               "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'"}.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

        def do_GET(self):
            if not self.valid_host():
                return self.send({"error": "Local access only."}, status=403)
            url = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/api/state":
                    return self.send({**workspace.available(), "token": token})
                if url.path == "/api/questions":
                    return self.send([{**q, "question_sha256": question_hash(q)} for q in workspace.dataset(query.get("dataset"))])
                if url.path == "/api/queue":
                    return self.send(workspace.queue(query.get("run")))
                if url.path == "/api/job":
                    return self.send(workspace.job_status())
                if url.path == "/api/report":
                    reports = workspace.catalog("report", "metrics.json")
                    if query.get("report") not in reports:
                        raise ValueError("Choose an available report.")
                    return self.send(read_json(reports[query["report"]] / "metrics.json"))
                if url.path == "/artifact":
                    reports = workspace.catalog("report", "metrics.json")
                    name = query.get("file")
                    types = {"calibration.png": "image/png", "risk_coverage.png": "image/png",
                             "metrics.csv": "text/csv; charset=utf-8", "metrics.json": "application/json; charset=utf-8",
                             "REPORT.md": "text/plain; charset=utf-8"}
                    if query.get("report") not in reports or name not in types:
                        raise ValueError("Unknown report artifact.")
                    return self.send((reports[query["report"]] / name).read_bytes(), types[name])
                assets = {"/": ("index.html", "text/html; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8")}
                if url.path in assets:
                    name, content_type = assets[url.path]
                    return self.send((STATIC / name).read_bytes(), content_type)
                self.send({"error": "Not found."}, status=404)
            except (ValueError, KeyError, OSError) as exc:
                self.send({"error": str(exc)}, status=400)

        def do_POST(self):
            origin = self.headers.get("Origin")
            expected = f"http://{self.headers.get('Host')}"
            if not self.valid_host() or self.headers.get("X-Workspace-Token") != token or (origin and origin != expected):
                return self.send({"error": "Refresh the local interface before submitting."}, status=403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 32000 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Expected a bounded JSON request.")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict) or not self.path.startswith("/api/"):
                    raise ValueError("Invalid action request.")
                self.send(workspace.mutate(self.path[5:], data))
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self.send({"error": str(exc)}, status=400)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    load_secrets()
    workspace = Workspace()
    server = make_server(workspace, args.port)
    print(f"Bangla-Cal workspace: http://127.0.0.1:{server.server_port} — Ctrl+C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with workspace.lock:
            workspace.stop()
        server.server_close()


if __name__ == "__main__":
    main()
