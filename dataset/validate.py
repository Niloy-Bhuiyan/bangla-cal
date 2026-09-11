"""Validate JSONL structure and review gates; never confer human review."""

import argparse
from collections import Counter
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = json.loads(Path(__file__).with_name("schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
CATEGORIES = tuple(SCHEMA["properties"]["category"]["enum"])
DRAFT_LABEL = "PRELIMINARY, UNREVIEWED DATA"


def load_questions(path, require_reviewed=False):
    records, ids, texts = [], set(), set()
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        try:
            record = json.loads(line)
            VALIDATOR.validate(record)
            if record["id"] in ids or record["question_bn"].strip() in texts:
                raise ValueError("duplicate ID or question text")
            reviewers = [r.strip() for r in record["reviewed_by"]]
            if len(set(reviewers)) != len(reviewers):
                raise ValueError("reviewers must be distinct after trimming")
            if len(reviewers) < 2:
                if require_reviewed:
                    raise ValueError("two real independent human reviews required")
                if "AWAITING HUMAN REVIEW" not in record["notes"]:
                    raise ValueError("unreviewed record must say AWAITING HUMAN REVIEW in notes")
            ids.add(record["id"])
            texts.add(record["question_bn"].strip())
            records.append(record)
        except Exception as exc:
            raise ValueError(f"{path}:{line_no}: {exc}") from exc
    if not records:
        raise ValueError("dataset is empty")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--require-reviewed", action="store_true")
    args = parser.parse_args()
    for path in args.paths:
        records = load_questions(path, args.require_reviewed)
        print(json.dumps({"path": path, "count": len(records),
                          "categories": dict(Counter(r["category"] for r in records)),
                          "review_status": "AWAITING HUMAN REVIEW" if any(
                              len(r["reviewed_by"]) < 2 for r in records) else
                              "review IDs present; verify signed review evidence"}))


if __name__ == "__main__":
    main()
