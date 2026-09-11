"""Real, explicitly preliminary cloud smoke test; no synthetic provider fallback."""

import argparse
import json
from pathlib import Path

from runner.providers.base import ModelConfig
from runner.run import run
from scoring.human import assess, create_queue
from scoring.judge import grade_run


def smoke(provider, root, resume=False, interval=6):
    models = {"gemini": "gemini-3.5-flash-lite", "groq": "qwen/qwen3.8-27b"}
    output = Path(root) / provider
    config = ModelConfig(provider, models[provider], max_tokens=1024, interval_seconds=interval)
    run("dataset/draft-v0.1-batch01.jsonl", config, output, samples=3,
        limit=24, seed=42, allow_unreviewed=True, resume=resume)
    judge = ModelConfig("gemini", "gemini-3.5-flash", max_tokens=1024, interval_seconds=interval)
    grade_run(output, judge, resume=resume)
    if not (output / "grading/validation_plan.json").exists():
        create_queue(output)
    # A convenience rerun must not replace previously ingested human grades
    # with an assessment of the original unfilled queue.
    if (output / "grading/scored.json").exists():
        agreement = json.loads((output / "grading/agreement.json").read_text(encoding="utf-8"))
        if agreement["human_completed"] == 0:
            agreement = assess(output)
        else:
            print("Existing human scores preserved; re-assess with the completed human file to include new judge scores.")
    else:
        agreement = assess(output)
    print(f"PRELIMINARY, UNREVIEWED DATA | {provider}: {agreement['status']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["gemini", "groq"], required=True)
    parser.add_argument("--root", default="results/local/smoke")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--interval", type=float, default=6)
    args = parser.parse_args()
    smoke(args.provider, args.root, args.resume, args.interval)


if __name__ == "__main__":
    main()
