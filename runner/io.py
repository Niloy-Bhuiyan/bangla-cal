"""Durable, UTF-8 artifact I/O and provenance helpers."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from runner.providers.base import redact


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_jsonl(path):
    if not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(redact(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)) + "\n",
                          encoding="utf-8")


def append_jsonl(path, row):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(redact(json.dumps(row, ensure_ascii=False, allow_nan=False)) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
