"""Run one explicit interface action in an isolated, stoppable process."""

import json
from pathlib import Path
import sys

from dataset.validate import load_questions
from runner.io import digest, read_jsonl
from runner.providers.base import ModelConfig, redact, load_secrets
from runner.run import run
from scoring.human import assess, create_queue
from scoring.judge import grade_run


def assessment(folder):
    if not (folder / "grading/validation_plan.json").exists():
        create_queue(folder)
    scored = folder / "grading/scored.json"
    humans = json.loads(scored.read_text(encoding="utf-8")).get("human_reviews", []) if scored.exists() else []
    by_id = {r["question_id"]: r for r in humans}
    for entry in read_jsonl(folder / "grading/interface_human.jsonl"):
        qid = entry["question_id"]
        if qid in by_id and any(by_id[qid].get(k) != entry.get(k) for k in ("grade", "reviewer_id", "rationale", "response_sha256")):
            raise ValueError("Conflicting human submissions; resolve first decisions explicitly with the maintainer.")
        # Preserve an adjudication note already ingested through the CLI.
        by_id.setdefault(qid, entry)
    path = folder / "grading/interface_assessment.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in by_id.values()), encoding="utf-8")
    result = assess(folder, path)
    print(f"{result['label']} | {result['status']} | {result['human_completed']} human grades", flush=True)


def execute(request):
    action = request["action"]
    if action == "generate":
        return run(request["dataset"], ModelConfig(**request["config"]), request["output"],
                   samples=request["samples"], limit=request["limit"], allow_unreviewed=request["allow_unreviewed"])
    folder = Path(request["run"])
    if action == "resume":
        plan = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["plan"]
        dataset = next((p for p in Path("dataset").glob("*.jsonl") if digest(load_questions(p)) == plan["dataset_sha256"]), None)
        if dataset is None:
            raise ValueError("The original dataset revision is unavailable; restore it before resuming.")
        pilots = set(json.loads(Path("dataset/pilot_ids.json").read_text(encoding="utf-8")))
        questions = [q for q in load_questions(dataset) if q["id"] not in pilots]
        limit = None if [q["id"] for q in questions] == plan["selected_ids"] else len(plan["selected_ids"])
        return run(dataset, ModelConfig(**plan["config"]), folder, plan["samples"], plan["sample_temperature"],
                   limit, plan["seed"], allow_unreviewed=True, resume=True)
    if action == "judge":
        config = ModelConfig(**request["config"])
        # grade_run itself rejects a changed judge plan on resume.
        return grade_run(folder, config, resume=(folder / "grading/judge_manifest.json").exists())
    if action == "expand":
        create_queue(folder, expand=True)
        return assessment(folder)
    if action in ("assess", "report"):
        assessment(folder)
        if action == "report":
            from report.generate import generate
            output = Path("report/generated") / folder.name
            generate([folder], output)
            print(f"Report saved to {output}", flush=True)
        return
    raise ValueError("Unknown worker action")


if __name__ == "__main__":
    load_secrets()
    try:
        execute(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except Exception as exc:
        print(redact(str(exc)), flush=True)
        sys.exit(1)
