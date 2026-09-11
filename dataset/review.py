"""Prepare blank native-speaker forms and check submitted, version-bound evidence.

This tool never assigns reviewers or changes reviewed_by. Human identity and
independence must be established by the maintainer, not inferred from JSON.
"""

import argparse
from datetime import date
import json
from pathlib import Path

from dataset.validate import load_questions
from runner.io import digest, read_jsonl

CONTENT_FIELDS = ("id", "category", "question_bn", "question_en_gloss",
                  "expected_behavior", "ground_truth_answer", "source_note", "difficulty_tier")
CHECKS = ("natural_bengali", "source_verified", "premise_checked", "behavior_appropriate")


def question_hash(question):
    return digest({key: question[key] for key in CONTENT_FIELDS})


def prepare(dataset, output):
    questions = load_questions(dataset)
    output = Path(output)
    if output.exists():
        raise ValueError("review directory already exists; never overwrite human work")
    output.mkdir(parents=True)
    for slot in (1, 2):
        with (output / f"reviewer-{slot}.jsonl").open("w", encoding="utf-8") as stream:
            for question in questions:
                entry = {"status": "AWAITING HUMAN REVIEW", "question_id": question["id"],
                         "question_sha256": question_hash(question),
                         "reviewer_id": None, "native_bengali_speaker": None,
                         "reviewed_at": None, "decision": None,
                         "checks": {key: None for key in CHECKS}, "rationale": None}
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return len(questions)


def assess_reviews(questions, paths, allow_extra=False):
    items = {q["id"]: q for q in questions}
    accepted = {qid: set() for qid in items}
    seen = set()
    for path in paths:
        for entry in read_jsonl(path):
            qid = entry["question_id"]
            if qid not in items:
                if allow_extra:
                    continue
                raise ValueError("review references a question outside this dataset")
            if entry["question_sha256"] != question_hash(items[qid]):
                raise ValueError("question content changed; obtain a fresh independent review")
            if (all(entry.get(k) is None for k in ("reviewer_id", "native_bengali_speaker",
                                                  "reviewed_at", "decision", "rationale"))
                    and all(entry.get("checks", {}).get(k) is None for k in CHECKS)):
                continue
            reviewer = entry.get("reviewer_id")
            if not isinstance(reviewer, str) or not reviewer.strip() or reviewer != reviewer.strip():
                raise ValueError("actual reviewer ID required, without surrounding whitespace")
            key = (qid, reviewer)
            if key in seen:
                raise ValueError("duplicate reviewer for this question; two different people are required")
            seen.add(key)
            if entry.get("native_bengali_speaker") is not True:
                raise ValueError("review must be submitted by a native Bengali speaker")
            try:
                date.fromisoformat(entry["reviewed_at"])
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError("reviewed_at must be an actual YYYY-MM-DD review date") from exc
            if entry.get("decision") not in ("accept", "revise", "reject"):
                raise ValueError("decision must be accept, revise, or reject")
            if not isinstance(entry.get("rationale"), str) or not entry["rationale"].strip():
                raise ValueError("review rationale/source verification note required")
            if any(type(entry.get("checks", {}).get(k)) is not bool for k in CHECKS):
                raise ValueError("complete every review check with true or false")
            if entry["decision"] == "accept":
                if not all(entry["checks"][k] for k in CHECKS):
                    raise ValueError("acceptance requires every review check to pass")
                accepted[qid].add(reviewer)
    backed = [qid for qid, q in items.items() if len(set(q["reviewed_by"])) >= 2
              and set(q["reviewed_by"]).issubset(accepted[qid])]
    return {"n_questions": len(items),
            "n_two_acceptances": sum(len(ids) >= 2 for ids in accepted.values()),
            "n_reviewed_with_evidence": len(backed),
            "pending_ids": [qid for qid in items if qid not in backed],
            "evidence_sha256": digest([read_jsonl(path) for path in paths]),
            "identity_note": "Reviewer identities and independence require maintainer verification."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "status"))
    parser.add_argument("dataset")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    if args.action == "prepare":
        if len(args.paths) != 1:
            parser.error("prepare takes one new output directory")
        count = prepare(args.dataset, args.paths[0])
        print(f"AWAITING HUMAN REVIEW: {count} questions in two blank independent forms")
    else:
        print(json.dumps(assess_reviews(load_questions(args.dataset), args.paths), indent=2))


if __name__ == "__main__":
    main()
