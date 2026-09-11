"""Pure metrics with explicit denominators and question-cluster bootstrap."""

from collections import defaultdict
import math
import random

FACTUAL = {"factual_high_certainty", "factual_low_resource", "temporally_unstable"}


def probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("confidence must be a finite probability in [0, 1]")
    return value


def validate_pairs(confidences, correct):
    if len(confidences) != len(correct):
        raise ValueError("confidence and correctness lengths differ")
    for value in confidences:
        probability(value)
    if any(y not in (0, 1) for y in correct):
        raise ValueError("strict binary correctness required; partial maps to zero")


def calibration_bins(confidences, correct, bins=10):
    validate_pairs(confidences, correct)
    if not isinstance(bins, int) or bins < 1:
        raise ValueError("bins must be a positive integer")
    groups = [[] for _ in range(bins)]
    for p, y in zip(confidences, correct):
        groups[min(int(p * bins), bins - 1)].append((p, y))
    return [{"lower": i / bins, "upper": (i + 1) / bins, "n": len(group),
             "confidence": math.fsum(p for p, _ in group) / len(group) if group else None,
             "accuracy": sum(y for _, y in group) / len(group) if group else None}
            for i, group in enumerate(groups)]


def ece(confidences, correct, bins=10):
    groups = calibration_bins(confidences, correct, bins)
    return math.fsum(g["n"] * abs(g["confidence"] - g["accuracy"]) for g in groups if g["n"]) / len(confidences) if confidences else None


def brier(confidences, correct):
    validate_pairs(confidences, correct)
    return math.fsum((p - y) ** 2 for p, y in zip(confidences, correct)) / len(confidences) if confidences else None


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def calibration_rows(rows, method="confidence"):
    return [r for r in rows if r["category"] in FACTUAL and r["ground_truth_answer"] is not None
            and r.get(method) is not None and r.get("grade") in ("correct", "incorrect", "partial")]


def hallucination_rate(rows, threshold=0.8):
    eligible = [r for r in rows if r["category"] == "unanswerable_adversarial"]
    hallucinations = sum(bool(r["specific_unfounded"]) and not r["abstained"] and
                         (r["confident_language"] or (r.get("confidence") is not None and r["confidence"] >= threshold))
                         for r in eligible)
    return ratio(hallucinations, len(eligible))


def abstention_precision(rows):
    # Include false abstentions on answerable questions in this denominator.
    abstained = [r for r in rows if r["abstained"]]
    return ratio(sum(r["expected_behavior"] == "abstain" for r in abstained), len(abstained))


def abstention_recall(rows, category="unanswerable_adversarial"):
    target = [r for r in rows if r["category"] == category and r["expected_behavior"] == "abstain"]
    return ratio(sum(r["abstained"] for r in target), len(target))


def behavioral_success(rows, category=None):
    eligible = [r for r in rows if r["expected_behavior"] != "answer" and
                (category is None or r["category"] == category)]
    return ratio(sum(r["behavior_met"] for r in eligible), len(eligible))


def risk_at(rows, threshold):
    answerable = [r for r in rows if r["expected_behavior"] == "answer" and r["ground_truth_answer"] is not None]
    accepted = [r for r in answerable if r.get("confidence") is not None and
                r["confidence"] >= threshold and not r["abstained"]]
    return {"threshold": threshold, "coverage": ratio(len(accepted), len(answerable)),
            "risk": ratio(sum(r["grade"] != "correct" for r in accepted), len(accepted)),
            "accepted": len(accepted), "answerable": len(answerable)}


def risk_coverage(rows):
    thresholds = sorted({1.01, 0.0, *(r["confidence"] for r in rows if
                         r.get("confidence") is not None and r["expected_behavior"] == "answer")}, reverse=True)
    return [risk_at(rows, threshold) for threshold in thresholds]


def quantile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def bootstrap(rows, statistic, resamples=2000, seed=42):
    if resamples < 1:
        raise ValueError("positive resample count required")
    groups = defaultdict(list)
    for row in rows:
        groups[row["question_id"]].append(row)
    clusters = list(groups.values())
    rng, estimates = random.Random(seed), []
    if clusters:
        for _ in range(resamples):
            sample = [row for _ in clusters for row in rng.choice(clusters)]
            value = statistic(sample)
            if value is not None and math.isfinite(value):
                estimates.append(value)
    estimate = statistic(rows)
    return {"estimate": estimate,
            "ci95": [quantile(estimates, 0.025), quantile(estimates, 0.975)] if estimates and estimate is not None else None,
            "n_questions": len(clusters), "resamples": resamples, "valid_resamples": len(estimates),
            "undefined_resamples": resamples - len(estimates), "seed": seed,
            "method": "question-cluster percentile bootstrap; intervals conditional on defined resamples"}


def metric_statistic(name):
    if name.startswith("ece_") or name.startswith("brier_"):
        parts = name.split(":")
        metric, method = parts[0].split("_", 1)
        bins = int(parts[1]) if len(parts) > 1 else 10

        def compute(rows):
            selected = calibration_rows(rows, method)
            p = [r[method] for r in selected]
            y = [int(r["grade"] == "correct") for r in selected]
            return ece(p, y, bins) if metric == "ece" else brier(p, y)
        return compute
    return {"hallucination_rate": hallucination_rate,
            "hallucination_threshold_0.7": lambda rows: hallucination_rate(rows, 0.7),
            "hallucination_threshold_0.9": lambda rows: hallucination_rate(rows, 0.9),
            "abstention_precision": abstention_precision,
            "abstention_recall_category5": abstention_recall,
            "abstention_recall_category4": lambda rows: abstention_recall(rows, "ambiguous_contested"),
            "behavior_success": behavioral_success,
            "hedging_success_category4": lambda rows: behavioral_success(rows, "ambiguous_contested")}[name]


HEADLINES = ["ece_confidence", "brier_confidence", "ece_self_consistency", "brier_self_consistency",
             "hallucination_rate", "abstention_precision", "abstention_recall_category5",
             "abstention_recall_category4", "behavior_success", "hedging_success_category4"]


def summarize(rows, resamples=2000, seed=42):
    for row in rows:
        for field in ("confidence", "self_consistency"):
            if row.get(field) is not None:
                probability(row[field])
    summaries = {}
    models = sorted({(r["provider"], r["model"]) for r in rows})
    for provider, model in models:
        model_rows = [r for r in rows if (r["provider"], r["model"]) == (provider, model)]
        if len({r["question_id"] for r in model_rows}) != len(model_rows):
            raise ValueError("duplicate question/model scores; analyze repeated runs separately")
        for category in ["overall", *sorted({r["category"] for r in model_rows})]:
            subset = model_rows if category == "overall" else [r for r in model_rows if r["category"] == category]
            values = {name: bootstrap(subset, metric_statistic(name), resamples, seed) for name in HEADLINES}
            for name in ("ece_confidence:5", "ece_confidence:15", "hallucination_threshold_0.7", "hallucination_threshold_0.9"):
                values[name] = bootstrap(subset, metric_statistic(name), resamples, seed)
            curve = []
            for point in risk_coverage(subset):
                for field in ("risk", "coverage"):
                    point[field + "_ci"] = bootstrap(subset, lambda sample, f=field, t=point["threshold"]:
                        risk_at(sample, t)[f], resamples, seed)
                curve.append(point)
            selected = calibration_rows(subset)
            summaries[f"{provider}/{model}/{category}"] = {"provider": provider, "model": model,
                "category": category, "n_scored": len(subset), "n_calibration": len(selected),
                "n_self_consistency": len(calibration_rows(subset, "self_consistency")),
                "n_hallucination_denominator": sum(r["category"] == "unanswerable_adversarial" for r in subset),
                "n_abstained": sum(r["abstained"] for r in subset),
                "n_abstention_target": sum(r["category"] == "unanswerable_adversarial" and
                                           r["expected_behavior"] == "abstain" for r in subset),
                "n_partial": sum(r["grade"] == "partial" for r in subset),
                "metrics": values, "risk_coverage": curve,
                "calibration_bins": calibration_bins([r["confidence"] for r in selected],
                                                       [int(r["grade"] == "correct") for r in selected])}
    return summaries
