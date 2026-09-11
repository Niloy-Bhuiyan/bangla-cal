"""Create a blinded human queue; ingest real grades and measure judge agreement."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import random

from metrics.core import bootstrap, ratio
from runner.io import append_jsonl, digest, now, read_jsonl, write_json
from scoring.judge import FIELDS, validate_grade

BEHAVIORAL = {"ambiguous_contested", "unanswerable_adversarial", "code_switched"}


def create_queue(run_dir, fraction=0.15, seed=42, expand=False):
    if not 0.10 <= fraction <= 0.15:
        raise ValueError("random validation fraction must be 10–15%")
    folder = Path(run_dir)
    responses = read_jsonl(folder / "responses.jsonl")
    if not responses:
        raise ValueError("no responses to review")
    questions = {r["id"]: r for r in read_jsonl(folder / "questions.jsonl")}
    raw = {r["question_id"]: r["text"] for r in read_jsonl(folder / "raw.jsonl") if r["sample_index"] == 0}
    judges = {r["question_id"] for r in read_jsonl(folder / "grading/judge_scores.jsonl")}
    ids = sorted(r["question_id"] for r in responses)
    # ceil avoids zero-person validation in small pilot runs; report actual fraction.
    random_ids = set(random.Random(seed).sample(ids, math.ceil(len(ids) * fraction)))
    if expand:
        previous = json.loads((folder / "grading/validation_plan.json").read_text(encoding="utf-8"))
        random_ids = set(previous["random_ids"])
        seed, fraction = previous["seed"], previous["requested_fraction"]
    queue = []
    for response in responses:
        qid = response["question_id"]
        question = questions[qid]
        if not expand and qid not in random_ids and question["category"] not in BEHAVIORAL and qid in judges:
            continue
        answer = response["primary"]["answer_bn"] if response["primary"] else raw[qid]
        queue.append({"label": response["label"], "question_id": qid,
            "response_sha256": digest(response), "question_bn": question["question_bn"],
            "expected_behavior": question["expected_behavior"], "ground_truth_answer": question["ground_truth_answer"],
            "source_note": question["source_note"], "response_text": answer,
            **{field: None for field in FIELDS}, "rationale": None,
            "reviewer_id": None, "reviewed_at": None, "resolution_note": None})
    queue_name = "human_queue_expanded.jsonl" if expand else "human_queue.jsonl"
    queue_path = folder / "grading" / queue_name
    if queue_path.exists():
        raise ValueError("queue already exists; never overwrite human work")
    for entry in queue:
        append_jsonl(queue_path, entry)
    write_json(folder / "grading/validation_plan.json", {"label": responses[0]["label"],
        "seed": seed, "requested_fraction": fraction, "actual_fraction": len(random_ids) / len(ids),
        "random_ids": sorted(random_ids), "population_ids": ids, "queue_ids": [r["question_id"] for r in queue],
        "response_sha256": digest(responses), "created_at": now(), "queue_file": queue_name,
        "note": "random sample plus all behavioral categories and failed judge parses"})
    return queue


def kappa(pairs):
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    a, b = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    chance = sum(a[label] * b[label] for label in a.keys() | b.keys()) / n ** 2
    return (observed - chance) / (1 - chance) if chance < 1 else None


def assess(run_dir, human_path=None, resamples=2000, seed=42):
    folder = Path(run_dir)
    plan = json.loads((folder / "grading/validation_plan.json").read_text(encoding="utf-8"))
    responses = read_jsonl(folder / "responses.jsonl")
    if digest(responses) != plan["response_sha256"]:
        raise ValueError("responses changed after validation sampling")
    response_map = {r["question_id"]: r for r in responses}
    questions = {r["id"]: r for r in read_jsonl(folder / "questions.jsonl")}
    judges = {r["question_id"]: r for r in read_jsonl(folder / "grading/judge_scores.jsonl")}
    human_rows = read_jsonl(human_path or folder / "grading" / plan.get("queue_file", "human_queue.jsonl"))
    human, seen = {}, set()
    raw = {r["question_id"]: r["text"] for r in read_jsonl(folder / "raw.jsonl") if r["sample_index"] == 0}
    for entry in human_rows:
        qid = entry["question_id"]
        if qid in seen or qid not in plan["queue_ids"]:
            raise ValueError("duplicate or unexpected human question ID")
        seen.add(qid)
        if entry["response_sha256"] != digest(response_map[qid]):
            raise ValueError("human grade refers to a different model response")
        original = questions[qid]
        if any(entry.get(field) != original[field] for field in
               ("question_bn", "expected_behavior", "ground_truth_answer", "source_note")):
            raise ValueError("human review question or reference was modified")
        response = response_map[qid]
        original_answer = response["primary"]["answer_bn"] if response["primary"] else raw[qid]
        if entry.get("response_text") != original_answer:
            raise ValueError("human review response text was modified")
        if all(entry.get(field) is None for field in (*FIELDS, "reviewer_id", "reviewed_at", "rationale")):
            continue
        validate_grade(entry)
        if not isinstance(entry.get("reviewer_id"), str) or not entry["reviewer_id"].strip() or not entry.get("reviewed_at"):
            raise ValueError("actual human reviewer ID and review date required")
        human[qid] = entry
    paired = []
    for qid in plan["random_ids"]:
        if qid in human and qid in judges:
            paired.append({"question_id": qid, "judge": judges[qid], "human": human[qid]})
    agreement = {field: bootstrap(paired, lambda sample, f=field:
        ratio(sum(r["judge"][f] == r["human"][f] for r in sample), len(sample)), resamples, seed)
        for field in FIELDS}
    agreement["kappa_grade"] = bootstrap(paired, lambda sample:
        kappa([(r["judge"]["grade"], r["human"]["grade"]) for r in sample]), resamples, seed)
    disagreements = [qid for qid in human if qid in judges and
                     any(human[qid][f] != judges[qid][f] for f in FIELDS)]
    unresolved = [qid for qid in disagreements if not human[qid].get("resolution_note")]
    complete_sample = len(paired) == len(plan["random_ids"])
    low = any(agreement[f]["estimate"] is not None and agreement[f]["estimate"] < 0.8 for f in FIELDS)
    status = "VALIDATED" if complete_sample and not low and not unresolved and len(human) == len(plan["queue_ids"]) else "PENDING HUMAN VALIDATION"
    if low:
        status = "EXPAND HUMAN GRADING: LOW AGREEMENT"
        if len(human) == len(responses) and not unresolved:
            status = "HUMAN GRADED; JUDGE LOW AGREEMENT"
    result = {"label": plan["label"], "status": status, "human_completed": len(human),
        "queue_size": len(plan["queue_ids"]), "random_sample_size": len(plan["random_ids"]),
        "random_pairs_complete": len(paired), "agreement": agreement,
        "disagreement_ids": disagreements, "unresolved_ids": unresolved,
        "note": "Agreement measured on random sample only; human overrides do not rewrite original judge labels."}
    write_json(folder / "grading/agreement.json", result)
    merged = []
    for response in responses:
        qid = response["question_id"]
        grade = human.get(qid, judges.get(qid))
        if grade is None:
            continue
        question = questions[qid]
        merged.append({"label": response["label"], "question_id": qid, "provider": response["provider"],
            "model": response["model"], "category": question["category"],
            "expected_behavior": question["expected_behavior"], "ground_truth_answer": question["ground_truth_answer"],
            "confidence": response["primary"]["confidence"] if response["primary"] else None,
            "self_consistency": response["self_consistency"],
            **{field: grade[field] for field in FIELDS}, "rationale": grade["rationale"],
            "grade_source": "human" if qid in human else "judge", "validation_status": status})
    # Derived artifact, never overwrite the human queue or original judge scores.
    write_json(folder / "grading/scored.json", {"label": plan["label"], "status": status,
        "n_responses": len(responses), "n_ungraded": len(responses) - len(merged), "rows": merged})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["queue", "assess"])
    parser.add_argument("run_dir")
    parser.add_argument("--human-file")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--expand", action="store_true", help="queue every response after low agreement")
    args = parser.parse_args()
    if args.action == "queue":
        queue = create_queue(args.run_dir, seed=args.seed, expand=args.expand)
        print(f"AWAITING HUMAN REVIEW: {len(queue)} responses queued")
    else:
        result = assess(args.run_dir, args.human_file, seed=args.seed)
        print(f"{result['label']} | {result['status']} | humans completed: {result['human_completed']}")


if __name__ == "__main__":
    main()
