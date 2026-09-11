# Metrics

ECE and Brier apply to factual categories with concrete ground truth.
Hallucination is measured on unanswerable/adversarial questions. Report
abstention precision/recall and risk-coverage on answerable questions.

All headline metrics need 95% question-level bootstrap confidence intervals,
with denominators and unavailable estimates explicitly reported.

Implementation: `metrics/core.py`; independently checked arithmetic examples in
`tests/test_metrics.py`. Confidence and correctness lengths must match; NaN,
out-of-range values, and nonbinary targets are rejected. Partial grades map to
zero for strict correctness, with partial counts retained.

ECE uses ten equal-width bins including 1.0 in the final bin, plus 5/15-bin
sensitivity. Missing temporal ground truth excludes an item from factual
calibration. Sampling confidence is evaluated separately from verbalized confidence.
Answerable code-switched items enter risk-coverage, but not categories 1–3 ECE.

Risk-coverage accepts confidence >= threshold and excludes abstained responses;
ties enter together. Its denominator includes all graded answerable items, even
ones lacking a usable confidence. Zero coverage has undefined risk. Bootstrap
intervals on curve points are pointwise, not simultaneous confidence bands.

Bootstrap resamples question IDs (all rows in a question cluster stay together),
2,000 times by default, with a saved seed and percentile 95% intervals. Undefined
resamples are counted; conditional intervals can be unstable with tiny samples.
Repeated question/model scores are rejected by the report summary instead of
silently treating repeated trials as independent questions.

Hallucination: category 5, a specific unfounded assertion, no actual abstention,
and verbalized confidence >=0.8 or explicit certainty in prose as judged. Both
0.7/0.9 sensitivities are available. Abstention precision includes false abstentions
on answerable questions. Category 4 mainly requires hedging; report its hedging
success separately, and leave abstention recall undefined when it has no abstain
targets. These are explicit preregistered operational choices, not human results.
