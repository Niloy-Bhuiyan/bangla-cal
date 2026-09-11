"""Verify logged run consistency without making API calls or judging correctness."""

import json
from pathlib import Path

from dataset.validate import load_questions
from runner.confidence import parse_response, sampling_agreement
from runner.io import digest, read_jsonl


def unique_index(rows, field):
    index = {}
    for row in rows:
        key = row[field]
        if key in index:
            raise ValueError(f"duplicate {field}: {key}")
        index[key] = row
    return index


def audit_run(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    questions = load_questions(folder / "questions.jsonl")
    responses = read_jsonl(folder / "responses.jsonl")
    raw_rows = read_jsonl(folder / "raw.jsonl")
    plan = manifest["plan"]
    if manifest["status"] != "complete":
        raise ValueError("generation is incomplete; resume before scoring or reporting")
    if [q["id"] for q in questions] != plan["selected_ids"]:
        raise ValueError("question snapshot differs from the selected run IDs")
    response_index = unique_index(responses, "question_id")
    if set(response_index) != set(plan["selected_ids"]):
        raise ValueError("response IDs do not cover the selected questions")
    raw = {}
    for row in raw_rows:
        key = (row["question_id"], row["sample_index"])
        if key in raw:
            raise ValueError("duplicate raw sample")
        raw[key] = row
    expected = {(q["id"], i) for q in questions for i in range(plan["samples"] + 1)}
    if set(raw) != expected:
        raise ValueError("raw samples are missing or have unexpected IDs/indices")
    prompts = [raw[(q["id"], 0)]["prompt"] for q in questions]
    if digest(prompts) != plan["prompt_sha256"]:
        raise ValueError("raw prompts differ from the manifest hash")
    for question, prompt in zip(questions, prompts):
        qid = question["id"]
        response = response_index[qid]
        parsed, versions = [], set()
        if not prompt.endswith(question["question_bn"]):
            raise ValueError("raw prompt does not match the question snapshot")
        for i in range(plan["samples"] + 1):
            sample = raw[(qid, i)]
            temperature = plan["primary_temperature"] if i == 0 else plan["sample_temperature"]
            if sample["prompt"] != prompt or sample["temperature"] != temperature:
                raise ValueError("sample prompt/temperature differs from run plan")
            versions.add(sample["model_version"])
            try:
                parsed.append(parse_response(sample["text"], sample["finish_reason"]))
            except (ValueError, TypeError):
                parsed.append(None)
        agreement = sampling_agreement(parsed[0], parsed[1:])
        if (response["primary"] != parsed[0] or response["samples"] != parsed[1:]
                or response["sample_count"] != plan["samples"]
                or response["model_versions"] != sorted(versions)
                or any(response[key] != agreement[key] for key in ("self_consistency", "modal_agreement"))):
            raise ValueError("derived responses/confidences differ from raw samples")
        if any(response[key] != plan["config"][key] for key in ("provider", "model")):
            raise ValueError("response model differs from run plan")
    return {"questions_sha256": digest(questions), "responses_sha256": digest(responses),
            "raw_sha256": digest(raw_rows), "n_questions": len(questions)}
