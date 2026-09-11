# Real cloud smoke evaluation

**PRELIMINARY, UNREVIEWED DATA — AWAITING HUMAN REVIEW**

This folder contains actual API output, not synthetic fixtures. The maintainer's
Gemini and Groq keys were read from a local gitignored `.env`. No key, request
authorization header, or paid-provider integration is included in these artifacts.

Design: 24 identical draft questions per model, selected with seed 42, four from
each category. The five example pilot IDs are excluded. Each question has one
primary response at temperature 0 and three independent samples at temperature
0.7. Sampling agreement is normalized exact matching to the primary answer;
semantic paraphrases may be undercounted. Normal evaluation defaults to ten
samples; this dry run deliberately uses three, so sampling estimates are coarse.

Subjects: Gemini `gemini-3.5-flash-lite` and Groq `qwen/qwen3.8-27b`.
Separate initial judge: Gemini `gemini-3.5-flash`. The judge is not human-validated.
Exact returned model IDs, timestamps, sampling settings, and dataset/prompt hashes
are in each manifest/raw log. A returned model ID may be a mutable alias.

## Artifact layout

- `environment.json`: runtime dependency versions and cost/design context.
- `gemini/`, `groq/`: separate run directories.
- `manifest.json`: requested model/configuration, selected IDs and completion state.
- `questions.jsonl`: the exact unreviewed question snapshot supplied to the runner.
- `raw.jsonl`: raw API payloads, raw response text, prompts, finish reasons and quota headers.
- `responses.jsonl`: parsed answer/action/confidence and sampling agreement, including parse errors.
- `grading/judge_raw.jsonl`: original judge payloads and rubric/prompt.
- `grading/judge_scores.jsonl`: provisional machine grades, kept unchanged by human overrides.
- `grading/human_queue.jsonl`: unfilled blinded review forms; no human grades have been fabricated.
- `grading/validation_plan.json`: uniformly sampled three responses (12.5%), plus behavioral items.
- `grading/agreement.json`: human agreement is unavailable until real grades are supplied.
- `grading/scored.json`: provisional joined inputs for report generation.

## Budget and future batching

Both response runs completed: 24 questions and 96 raw generation replies each,
with zero parse failures. Initial judging is **incomplete**: 9/24 Gemini responses
and 12/24 Groq responses were graded. Gemini `gemini-3.5-flash` returned HTTP 429
with `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, quota value **20**.
The error payloads are preserved under each grading directory. One earlier HTTP
503 service-demand error was also retained and recovered through resume.

There are 27 outstanding judge requests. A maintainer-requested retry saved one
additional grade before the same daily-quota error returned. Proposed continuation:
use the next two daily quota windows for 20 then 7 requests on the same judge; preserve all model,
prompt, and input settings. A short retryDelay in an error does not remove its
explicit per-day quota. No extra keys/accounts, paid service or substitute judge
were used to bypass this limit. No further API calls are scheduled automatically.

The partial graded subset follows run order, not random missingness. Any metrics
computed now apply only to those graded responses, and must not be used to rank
models or make population-level claims. All 48 response records remain available.

Groq's observed response headers advertised 1,000 requests/day and 8,000 tokens/
minute for this account/model. These are actual observed headers, not promised
future quotas. The 24-question run requires 96 generation requests per subject,
plus 24 separate judge requests per run. No paid fallback is configured.

For a future 400–600-question run with ten samples, each model needs 4,400–6,600
generation requests. At the observed Groq daily quota, plan at least 5–7 days,
with capacity reserved for other account usage and retries; a tentative batch of
80 questions/day uses 880 requests. Inspect Gemini's actual account quota before
planning its batches. No full-dataset run or recurring schedule has been started.
If a limit is hit, retain the error and Retry-After/reset headers, then resume the
same plan in its original directory after quota returns.

Dataset release and trustworthy findings remain blocked on actual native-speaker
review, dataset expansion, human grading, and judge validation. The generated
[preliminary report](../../report/smoke-2026-09-11/REPORT.md) includes these limits.
