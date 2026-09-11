# Research report

No validated research findings yet. The final report must include methodology, dataset provenance,
per-model/category estimates with 95% bootstrap intervals, calibration and
risk-coverage charts, judge/human agreement, and null findings.

Required limitations: small sample size; judge bias and human-validation status;
standard/formal Bengali only; API model drift and exact run versions; any model
excluded because confidence could not be measured.

Cost scope: evaluated against freely accessible models only; proprietary frontier
models (GPT, Claude) excluded from v1 due to cost, left as future work pending
research credits or sponsorship.

## Generate a report

```sh
python -m report.generate results/smoke-2026-09-11/gemini results/smoke-2026-09-11/groq --output report/generated
```

The generator reads actual run manifests and scored output. It emits Markdown,
CSV, JSON, a calibration plot and a risk-coverage plot, with 2,000 bootstrap
resamples by default. Missing metrics/agreement are explicitly unavailable.

The [committed smoke report](smoke-2026-09-11/REPORT.md) is labeled
PRELIMINARY, UNREVIEWED DATA. `--release` refuses draft/small datasets, incomplete
runs, missing grades or unvalidated grading. Synthetic tests use temporary
directories and are never substituted for the published cloud runs.
