"""Run questions with raw-first logging and resumable sample-level checkpoints."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import random
import subprocess
import time

from dataset.validate import CATEGORIES, DRAFT_LABEL, load_questions
from runner.confidence import PROMPT_VERSION, make_prompt, parse_response, sampling_agreement
from runner.io import append_jsonl, digest, now, read_jsonl, write_json
from runner.providers.base import ModelConfig, ProviderError, get_provider


def select_questions(questions, limit, seed):
    if limit is None:
        return questions
    if not 1 <= limit <= len(questions):
        raise ValueError("limit must be between 1 and dataset size")
    rng = random.Random(seed)
    buckets = [[q for q in questions if q["category"] == cat] for cat in CATEGORIES]
    for bucket in buckets:
        rng.shuffle(bucket)
    chosen = []
    while len(chosen) < limit:
        for bucket in buckets:
            if bucket and len(chosen) < limit:
                chosen.append(bucket.pop())
    return chosen


def run(dataset, config, output, samples=10, temperature=0.7, limit=None,
        seed=42, allow_unreviewed=False, resume=False, provider=None):
    if samples < 2 or not 0 < temperature <= 2:
        raise ValueError("need at least two samples and a temperature in (0, 2]")
    questions = load_questions(dataset, require_reviewed=not allow_unreviewed)
    # Pilot items are reserved regardless of which file the caller supplies.
    pilot_ids = set(json.loads(Path("dataset/pilot_ids.json").read_text(encoding="utf-8")))
    questions = [q for q in questions if q["id"] not in pilot_ids]
    questions = select_questions(questions, limit, seed)
    output = Path(output)
    label = DRAFT_LABEL if any(len(q["reviewed_by"]) < 2 for q in questions) else "REVIEWED DATA; GRADING PENDING"
    plan = {"config": asdict(config), "dataset_sha256": digest(load_questions(dataset)),
            "selected_ids": [q["id"] for q in questions], "samples": samples,
            "sample_temperature": temperature, "primary_temperature": 0.0,
            "seed": seed, "prompt_version": PROMPT_VERSION,
            "prompt_sha256": digest([make_prompt(q) for q in questions])}
    manifest_path = output / "manifest.json"
    if output.exists() and any(output.iterdir()) and not resume:
        raise ValueError("output exists; use --resume or a new directory")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["plan"] != plan:
            raise ValueError("resume refused: dataset/config/prompt/sampling plan changed")
    else:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        manifest = {"label": label, "run_id": output.name, "created_at": now(),
                    "code_revision": revision.stdout.strip(), "plan": plan, "status": "running"}
        write_json(manifest_path, manifest)
        for question in questions:
            append_jsonl(output / "questions.jsonl", question)
    provider = provider or get_provider(config)
    raw_index = {(r["question_id"], r["sample_index"]): r for r in read_jsonl(output / "raw.jsonl")}
    completed = {r["question_id"] for r in read_jsonl(output / "responses.jsonl")}
    for question in questions:
        qid = question["id"]
        if qid in completed:
            continue
        parsed, errors, versions = [], [], set()
        for index in range(samples + 1):
            key = (qid, index)
            if key not in raw_index:
                if raw_index and config.interval_seconds:
                    time.sleep(config.interval_seconds)
                started = now()
                try:
                    response = provider.generate(make_prompt(question), 0.0 if index == 0 else temperature)
                except ProviderError as exc:
                    append_jsonl(output / "errors.jsonl", {"label": label, "at": now(),
                        "question_id": qid, "sample_index": index, "status": exc.status,
                        "detail": exc.detail, "headers": exc.headers})
                    manifest.update(status="interrupted", stopped_at=now(), http_status=exc.status)
                    write_json(manifest_path, manifest)
                    raise
                raw_index[key] = {"label": label, "question_id": qid, "sample_index": index,
                    "started_at": started, "finished_at": now(), "prompt": make_prompt(question),
                    "temperature": 0.0 if index == 0 else temperature, **asdict(response)}
                append_jsonl(output / "raw.jsonl", raw_index[key])
            raw = raw_index[key]
            versions.add(raw["model_version"])
            try:
                parsed.append(parse_response(raw["text"], raw["finish_reason"]))
            except (ValueError, TypeError) as exc:
                parsed.append(None)
                errors.append({"sample_index": index, "error": str(exc)})
        estimates = sampling_agreement(parsed[0], parsed[1:])
        append_jsonl(output / "responses.jsonl", {"label": label, "question_id": qid,
            "provider": config.provider, "model": config.model, "model_versions": sorted(versions),
            "primary": parsed[0], "sample_count": samples, "samples": parsed[1:],
            **estimates, "parse_errors": errors,
            "confidence_eligible": parsed[0] is not None and estimates["self_consistency"] is not None})
        print(f"{label} | {qid} saved ({len(completed) + 1}/{len(questions)})", flush=True)
        completed.add(qid)
    manifest.update(status="complete", completed_at=now(), completed_questions=len(completed))
    write_json(manifest_path, manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="dataset/draft-v0.1-batch01.jsonl")
    parser.add_argument("--provider", choices=["gemini", "groq", "ollama"], required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--interval", type=float, default=6)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--logprobs", action="store_true")
    parser.add_argument("--allow-unreviewed", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    config = ModelConfig(args.provider, args.model, "local" if args.provider == "ollama" else "free",
                         args.max_tokens, args.interval, logprobs=args.logprobs)
    run(args.dataset, config, args.output, args.samples, args.temperature, args.limit,
        args.seed, args.allow_unreviewed, args.resume)


if __name__ == "__main__":
    main()
