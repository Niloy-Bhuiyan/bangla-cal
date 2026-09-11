"""Generate honest tables and charts from real run artifacts (or labeled test fixtures)."""

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dataset.validate import DRAFT_LABEL
from dataset.review import assess_reviews
from metrics.core import HEADLINES, summarize
from runner.io import digest, now, read_jsonl, write_json
from runner.audit import audit_run, unique_index
from scoring.judge import FIELDS, validate_grade


def format_metric(metric):
    if metric["estimate"] is None:
        return "unavailable"
    value = f"{metric['estimate']:.3f}"
    if metric["ci95"]:
        value += f" [{metric['ci95'][0]:.3f}, {metric['ci95'][1]:.3f}]"
    return value


def generate(run_dirs, output, resamples=2000, seed=42, release=False, dataset_reviews=None):
    output = Path(output)
    inputs, rows, draft = [], [], False
    for directory in run_dirs:
        folder = Path(directory)
        integrity = audit_run(folder)
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        scores = json.loads((folder / "grading/scored.json").read_text(encoding="utf-8"))
        agreement = json.loads((folder / "grading/agreement.json").read_text(encoding="utf-8"))
        judge = json.loads((folder / "grading/judge_manifest.json").read_text(encoding="utf-8"))
        questions = read_jsonl(folder / "questions.jsonl")
        responses = read_jsonl(folder / "responses.jsonl")
        source_hashes = {**integrity,
            "judge_scores_sha256": digest(read_jsonl(folder / "grading/judge_scores.jsonl")),
            "validation_plan_sha256": digest(json.loads((folder / "grading/validation_plan.json").read_text(encoding="utf-8")))}
        assessed = scores.get("assessment_inputs", {})
        if not assessed or any(assessed.get(k) != value for k, value in source_hashes.items()):
            raise ValueError("stale or unaudited scores; rerun scoring.human assess with the actual human file, if any")
        if agreement.get("assessment_inputs") != assessed or scores["status"] != agreement["status"]:
            raise ValueError("agreement and scores come from different assessments")
        score_index = unique_index(scores["rows"], "question_id")
        response_index = unique_index(responses, "question_id")
        question_index = unique_index(questions, "id")
        judges = unique_index(read_jsonl(folder / "grading/judge_scores.jsonl"), "question_id")
        human = unique_index(scores.get("human_reviews", []), "question_id")
        if digest(list(human.values())) != assessed.get("accepted_human_sha256"):
            raise ValueError("human grading evidence differs from its assessment")
        if not set(score_index).issubset(response_index) or scores["n_ungraded"] != len(responses) - len(score_index):
            raise ValueError("score coverage counts or IDs are inconsistent")
        for qid, row in score_index.items():
            validate_grade(row)
            question, response = question_index[qid], response_index[qid]
            if any(row[key] != question[key] for key in ("category", "expected_behavior", "ground_truth_answer")):
                raise ValueError("score references a different question or ground truth")
            confidence = response["primary"]["confidence"] if response["primary"] else None
            if row["confidence"] != confidence or row["self_consistency"] != response["self_consistency"]:
                raise ValueError("score confidence differs from its response")
            if row["grade_source"] == "judge" and (qid not in judges or any(row[f] != judges[qid][f] for f in FIELDS)):
                raise ValueError("derived judge grade differs from original judgment")
            if row["grade_source"] not in ("judge", "human"):
                raise ValueError("unknown grade source")
            if row["grade_source"] == "human":
                evidence = human.get(qid)
                if not evidence or any(row[f] != evidence[f] for f in FIELDS):
                    raise ValueError("human grade has no matching submitted evidence")
                if evidence["response_sha256"] != digest(response) or not evidence.get("reviewer_id") or not evidence.get("reviewed_at"):
                    raise ValueError("human evidence lacks response binding or reviewer attribution")
        this_draft = any(len(q["reviewed_by"]) < 2 for q in questions)
        draft |= this_draft
        review_evidence = assess_reviews(questions, dataset_reviews or [], allow_extra=True)
        if release and review_evidence["n_reviewed_with_evidence"] != len(questions):
            raise ValueError("release requires matching independent native-speaker review evidence via --dataset-reviews")
        if release and (this_draft or manifest["status"] != "complete" or not 400 <= len(questions) <= 600
                        or agreement["status"] not in ("VALIDATED", "HUMAN GRADED; JUDGE LOW AGREEMENT")
                        or scores["n_ungraded"]):
            raise ValueError("release requires 400–600 reviewed questions, a complete run, and validated/human grades")
        if scores["n_responses"] != len(responses):
            raise ValueError("stale scores: response count changed")
        rows.extend(scores["rows"])
        inputs.append({"path": folder.as_posix(), "manifest": manifest, "judge": judge,
            "dataset_review_evidence": review_evidence,
            "agreement": agreement, "scores_sha256": digest(scores),
            "n_responses": len(responses), "n_ungraded": scores["n_ungraded"],
            "n_parse_errors": sum(bool(r["parse_errors"]) for r in responses),
            "n_two_confidence_methods": sum(r["confidence_eligible"] for r in responses),
            "grading_errors": [{k: error[k] for k in ("at", "status", "detail")}
                               for error in read_jsonl(folder / "grading/errors.jsonl")],
            "model_versions": sorted({v for r in responses for v in r["model_versions"]}),
            "n_human_reviewed_questions": sum(len(q["reviewed_by"]) >= 2 for q in questions)})
    if not rows:
        raise ValueError("no scored responses; cannot manufacture a results report")
    label = DRAFT_LABEL if draft else ("REVIEWED DATA" if release else "PRELIMINARY ANALYSIS")
    incomplete = any(item["n_ungraded"] for item in inputs)
    summaries = summarize(rows, resamples, seed)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "metrics.json", {"label": label, "generated_at": now(), "seed": seed,
        "generator_sha256": digest(Path(__file__).read_text(encoding="utf-8")),
        "metrics_code_sha256": digest(Path("metrics/core.py").read_text(encoding="utf-8")),
        "resamples": resamples, "inputs": inputs, "summaries": summaries})
    with (output / "metrics.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["label", "provider", "model", "category", "metric", "estimate", "ci_low", "ci_high",
                  "n_scored", "n_calibration", "n_self_consistency", "n_hallucination_denominator",
                  "n_abstained", "n_abstention_target", "valid_resamples", "undefined_resamples"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for summary in summaries.values():
            for name, metric in summary["metrics"].items():
                interval = metric["ci95"] or [None, None]
                writer.writerow({"label": label, **{k: summary[k] for k in fields if k in summary},
                    "metric": name, "estimate": metric["estimate"], "ci_low": interval[0], "ci_high": interval[1],
                    "valid_resamples": metric["valid_resamples"], "undefined_resamples": metric["undefined_resamples"]})
    overall = [r for r in summaries.values() if r["category"] == "overall"]
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    for kind in ("calibration", "risk_coverage"):
        fig, ax = plt.subplots(figsize=(9, 6), layout="constrained")
        fig.suptitle(label + ("\nINCOMPLETE JUDGING — graded subset only" if incomplete else ""),
                     fontsize=11, color="#a33b20")
        for series_index, summary in enumerate(overall):
            name = summary["provider"] + ": " + summary["model"]
            if kind == "calibration":
                points = [b for b in summary["calibration_bins"] if b["n"]]
                ax.plot([b["confidence"] for b in points], [b["accuracy"] for b in points],
                        marker="o" if series_index % 2 == 0 else "x", linestyle="-",
                        markersize=9, markerfacecolor="none", label=name)
                for point in points:
                    ax.annotate(f"n={point['n']}", (point["confidence"], point["accuracy"]),
                                xytext=(-6, -14 - series_index * 13), ha="right",
                                textcoords="offset points", fontsize=8)
            else:
                points = [p for p in summary["risk_coverage"] if p["risk"] is not None]
                if points:
                    line, = ax.plot([p["coverage"] for p in points], [p["risk"] for p in points], "o-", label=name)
                    ax.fill_between([p["coverage"] for p in points],
                        [p["risk_ci"]["ci95"][0] if p["risk_ci"]["ci95"] else p["risk"] for p in points],
                        [p["risk_ci"]["ci95"][1] if p["risk_ci"]["ci95"] else p["risk"] for p in points],
                        color=line.get_color(), alpha=0.12)
        if kind == "calibration":
            ax.plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
            ax.set(xlabel="Mean verbalized confidence", ylabel="Strict correctness rate",
                   title="Calibration: factual items with concrete ground truth")
        else:
            ax.set(xlabel="Coverage of graded answerable questions", ylabel="Error rate among accepted answers",
                   title="Risk–coverage: pointwise 95% bootstrap intervals")
        ax.set(xlim=(-0.03, 1.03), ylim=(-0.05, 1.05))
        ax.grid(alpha=0.15)
        ax.legend(loc="best", fontsize=8)
        fig.savefig(output / (kind + ".png"), dpi=180)
        plt.close(fig)
    lines = ["# Bangla-Cal evaluation report", "", f"**{label}**", "",
        "This is a pipeline dry run, not a validated benchmark finding. Dataset review and",
        "judge/human validation status below control how these numbers may be interpreted.", "",
        "## Run provenance", ""]
    if incomplete:
        lines[4:4] = ["**INCOMPLETE JUDGING. Metrics below use only the graded subset.**",
            "Missing grades follow run order, not random sampling; do not rank models using these estimates.",
            f"{sum(item['n_ungraded'] for item in inputs)} of {sum(item['n_responses'] for item in inputs)} response grades remain pending.",
            "Recorded grading errors and their actual quota details are preserved in metrics.json and the raw run directories.", ""]
    for item in inputs:
        config = item["manifest"]["plan"]["config"]
        lines.extend([f"- **{config['provider']} / {config['model']}**: {item['n_responses']} responses; "
                      f"{item['n_two_confidence_methods']} with both confidence methods; "
                      f"{item['n_parse_errors']} responses with parse errors; {item['n_ungraded']} ungraded.",
                      f"  Exact returned version(s): {', '.join(item['model_versions'])}.",
                      f"  Started {item['manifest']['created_at']}; code {item['manifest']['code_revision']}.",
                      f"  Dataset hash: `{item['manifest']['plan']['dataset_sha256']}`.",
                      f"  Separate judge: {item['judge']['plan']['config']['model']}."])
    lines.extend(["", "## Overall estimates", "", "Values are estimates [95% bootstrap interval]. Lower ECE, Brier and",
                  "hallucination rate are better. Precision and recall have different denominators.", "",
                  "| Model | ECE | Brier | Hallucination rate | Abstention precision | Abstention recall (cat. 5) |",
                  "| --- | --- | --- | --- | --- | --- |"])
    for summary in overall:
        keys = ["ece_confidence", "brier_confidence", "hallucination_rate", "abstention_precision", "abstention_recall_category5"]
        lines.append("| " + summary["provider"] + "/" + summary["model"] + " | " +
                     " | ".join(format_metric(summary["metrics"][k]) for k in keys) + " |")
    lines.extend(["", "## Category estimates", "", "| Model | Category | Scored | Calibration n | ECE | Hallucination rate |",
                  "| --- | --- | --- | --- | --- | --- |"])
    for summary in summaries.values():
        if summary["category"] == "overall":
            continue
        lines.append(f"| {summary['provider']}/{summary['model']} | {summary['category']} | {summary['n_scored']} | "
                     f"{summary['n_calibration']} | {format_metric(summary['metrics']['ece_confidence'])} | "
                     f"{format_metric(summary['metrics']['hallucination_rate'])} |")
    lines.extend(["", "Full per-category Brier, sampling-confidence metrics, behavioral scores, sensitivities,",
                  "denominators and defined/undefined bootstrap counts are in [metrics.csv](metrics.csv)",
                  "and [metrics.json](metrics.json).", "", "## Confidence-method cross-check", "",
                  "| Model | Verbalized ECE | Sampling ECE | Sampling Brier |", "| --- | --- | --- | --- |"])
    for summary in overall:
        lines.append(f"| {summary['provider']}/{summary['model']} | " + " | ".join(format_metric(summary["metrics"][k])
                     for k in ("ece_confidence", "ece_self_consistency", "brier_self_consistency")) + " |")
    lines.extend(["", "![Calibration](calibration.png)", "", "![Risk–coverage](risk_coverage.png)", "",
                  "## Judge/human agreement", "",
                  "| Evaluated model | Validation status | Human graded / queued | Random pairs / selected | Exact grade agreement |",
                  "| --- | --- | --- | --- | --- |"])
    for item in inputs:
        a = item["agreement"]
        cfg = item["manifest"]["plan"]["config"]
        lines.append(f"| {cfg['provider']}/{cfg['model']} | {a['status']} | {a['human_completed']}/{a['queue_size']} | "
                     f"{a['random_pairs_complete']}/{a['random_sample_size']} | {format_metric(a['agreement']['grade'])} |")
    lines.extend(["", "Missing human grades mean agreement is **unavailable**, not zero and not perfect.",
        "Queues preserve blinded first-pass decisions. Any low agreement requires expanded human",
        "grading; human overrides do not alter the original judge agreement calculation.", "",
        "## Methodology and limitations", "",
        "- Question-level percentile bootstrap, 95% intervals, " + str(resamples) + " resamples, seed " + str(seed) + ".",
        "- Ten equal-width ECE bins; 5/15-bin sensitivity included. Strict correctness treats partial as zero.",
        "- ECE/Brier use categories 1–3 with concrete ground truth. Null temporal answers are excluded.",
        "- Risk–coverage includes all graded answerable questions (including answerable code switching),",
        "  excludes actual abstention from acceptance, and includes equal-confidence answers together.",
        "  Its shaded intervals are pointwise at fixed thresholds; they are not simultaneous bands.",
        "- Hallucination uses category 5, a specific unfounded assertion, no abstention, and >=0.8",
        "  verbalized confidence or explicit certainty in prose. Threshold sensitivity is provided.",
        "- Sampling agreement compares each sample to the primary answer after conservative text",
        "  normalization; paraphrases may be undercounted. It is a proxy, not semantic certainty.",
        "- Every run's sample count and temperatures are in metrics.json. Smoke uses three samples",
        "  at temperature 0.7; normal runs default to ten. Primary temperature is zero.",
        "- Raw token logprobs, where available, are retained separately. No whole-response token",
        "  likelihood is presented as probability of factual correctness.",
        "- Tiny category counts and unreviewed items limit inference. Degenerate bootstrap intervals",
        "  from all-correct/all-wrong small samples do not establish certainty. Undefined resamples",
        "  are counted, and intervals are conditional on estimable bootstrap samples.",
        "- Scores are provisional wherever the human-validation gate is pending. A Gemini judge",
        "  may favor related model outputs. Do not interpret differences as validated model rankings.",
        "- Standard/formal Bengali only, plus deliberate code switching; dialects are not covered.",
        "  The first batch is heritage-heavy and does not establish broad Bangladesh-domain coverage.",
        "- API models can change; retain exact returned versions, timestamps, raw logs and dataset hashes.",
        "  A returned model identifier may still be a mutable alias; no immutable snapshot is inferred.",
        "- No English comparison experiment was run. No cross-language gap or novelty claim is inferred.",
        "- All categories are reported, including unavailable and null/negative findings. This pilot",
        "  establishes pipeline behavior only; no robust category effect is claimed.", "",
        "Evaluated against freely accessible models only; proprietary frontier models (GPT, Claude)",
        "excluded from v1 due to cost, left as future work pending research credits or sponsorship.",
        "Ollama is implemented but not evaluated in this cloud smoke test. Encoder-only Bengali",
        "models are not treated as comparable generative QA systems.", "",
        "## Before a research release", "",
        "Expand the draft toward 400–600 questions, recruit a second native Bengali reviewer,",
        "obtain two independent item reviews, archive temporal sources, freeze the dataset, run",
        "full evaluations, complete and adjudicate human grades, then regenerate the report.", ""])
    (output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+")
    parser.add_argument("--output", default="report/generated")
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--dataset-reviews", nargs="+", help="actual native-speaker submissions; required for --release")
    args = parser.parse_args()
    generate(args.run_dirs, args.output, args.resamples, args.seed, args.release, args.dataset_reviews)
    print(f"Report written to {args.output}; inspect its dataset and grading status labels.")


if __name__ == "__main__":
    main()
