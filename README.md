# Bangla-Cal

[![Offline verification](https://github.com/Niloy-Bhuiyan/bangla-cal/actions/workflows/ci.yml/badge.svg)](https://github.com/Niloy-Bhuiyan/bangla-cal/actions/workflows/ci.yml)

A Bengali-language research benchmark for whether a language model's confidence
matches its correctness, and whether it admits uncertainty instead of inventing
answers. The deliverables are a carefully reviewed dataset and reproducible
statistical findings, supported by a small Python evaluation pipeline.

Repository name: `bangla-cal`. The original specification calls the benchmark
BAN-CAL; dataset identifiers retain its `ban-cal-` prefix for schema compatibility.

## Status: implementation and preliminary smoke evaluation

**AWAITING HUMAN REVIEW.** No dataset has been validated and no defensible
research finding is claimed. AI-drafted questions must retain
`reviewed_by: []` until two independent native Bengali speakers actually review
them. Niloy and a second native speaker must check facts, premises, behavior
targets, and natural phrasing before a trustworthy dataset release.

The first batch contains **60 unreviewed candidates: 10 per category**, plus six
separate schema examples. Five example IDs are held out as pilot items. The v0.1
target remains 400–600, roughly balanced. Drafts are not a frozen release.

The dataset validator, three provider adapters, two confidence methods, resumable
runner, metrics with bootstrap intervals, judge pipeline, human queues/agreement,
and report generator are implemented. Real cloud smoke artifacts are stored in
[`results/smoke-2026-09-11`](results/smoke-2026-09-11/); consult their manifests for
completion and model versions, and the
[preliminary report](report/smoke-2026-09-11/REPORT.md) for results and limitations.
All draft-run outputs say **PRELIMINARY, UNREVIEWED DATA**.

**Smoke status:** Gemini and Groq each completed 24 questions (192 raw generation
responses total), with no parse failures. Initial judging is **21/48 complete**:
9 Gemini responses and 12 Groq responses have machine grades. The separate Gemini
judge hit its confirmed **20 requests/project/model/day** quota, including after
a maintainer-requested retry. **27 grades remain pending.** The report uses only
the graded subset and must not be used to rank models. No human reviews or human
grades have been recorded. The offline suite currently contains 27 passing tests.

This repository is prepared as a **public research preview**. Read the
[release notes and remaining gates](docs/RELEASE.md) and
[dataset card](dataset/DATASET_CARD.md). Its interface is the Python command line
and generated Markdown/CSV/JSON reports with charts. A validated benchmark
release still needs the human review and evaluation work described below.

The full [research specification](bengali-ai-reliability-benchmark-spec.md) is
committed as the persistent source of truth. No OpenAI or Anthropic API is called.

## Setup

Use Python 3.10+ from the repository root:

```sh
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -v
python -m dataset.validate dataset/examples.jsonl dataset/draft-v0.1-batch01.jsonl
```

Copy `.env.example` to `.env` and fill in `GEMINI_API_KEY` and `GROQ_API_KEY`
locally. `.env` is gitignored; do not put keys in JSON configs or command-line
arguments. Existing environment variables take precedence. Use free-tier accounts
with billing disabled: the code cannot change or verify an account's billing tier.
The runner stops on HTTP/quota errors, records the actual error, and never switches
to a paid provider. Rate limits and model availability are account-specific.

For local evaluation, install Ollama, start its local server, and install a suitable
model using `ollama pull MODEL`. The adapter only calls `127.0.0.1`; cloud-tagged
Ollama models are rejected. Local hardware needs depend on the chosen model.

## Reproduce the real smoke test

To inspect the saved results without keys or API calls:

```sh
python -m report.generate results/smoke-2026-09-11/gemini results/smoke-2026-09-11/groq --output report/generated
```

Reports audit saved raw responses, derived confidence, and scoring provenance;
stale or inconsistent artifacts are rejected. CI independently reproduces the
archived metric estimates and bootstrap intervals on Windows and Linux.

The convenience command runs 24 questions, balanced across six categories, with
three nonzero-temperature samples per primary response, then a separate Gemini
judge and an unfilled human queue. It uses the actual keys in `.env`, never a fake
provider. Ordinary evaluation defaults to ten sampling responses per question.

```sh
python -m runner.smoke --provider gemini --root results/local/smoke
python -m runner.smoke --provider groq --root results/local/smoke
python -m report.generate results/local/smoke/gemini results/local/smoke/groq --output report/generated
```

These commands make 96 generation calls and 24 judge calls per evaluated model.
Check your actual free quota first. `--resume` on the smoke command reuses saved
responses; output paths are not overwritten by default. If a provider blocks a
request, retain the raw log and error, wait for the reported reset, and resume.
Do not change the dataset, model, prompt or sampling plan in an existing run.

The recorded Gemini judge quota cannot finish 48 judgments in one daily window.
For the saved runs, budget the remaining 27 requests over two quota windows
(20 then 7). The next window can finish the 15 missing Gemini-response grades
and five Groq-response grades; the following window finishes the last seven.
Do not interpret the error's short retryDelay as a reset of the daily quota.
No background schedule has been created and no paid upgrade is required.

Resume only the unfinished judging, without regenerating answers:

```sh
python -m scoring.judge results/smoke-2026-09-11/gemini --provider gemini --model gemini-3.5-flash --interval 6 --max-tokens 1024 --resume
python -m scoring.judge results/smoke-2026-09-11/groq --provider gemini --model gemini-3.5-flash --interval 6 --max-tokens 1024 --resume
python -m scoring.human assess results/smoke-2026-09-11/gemini
python -m scoring.human assess results/smoke-2026-09-11/groq
python -m report.generate results/smoke-2026-09-11/gemini results/smoke-2026-09-11/groq --output report/generated
```

If real humans have already completed grading, supply their completed files to
`assess --human-file` instead of reassessing an empty queue. The convenience smoke
command preserves previously ingested human grades. For a new quota-interrupted
run, `scoring.human queue` followed by `assess` can produce explicitly incomplete
report inputs from the machine grades available so far.

The [provider notes](runner/providers/README.md) link current official cost and
quota documentation. Example model IDs are explicit, and may need replacement
when the provider retires a model; always use a new run directory for that change.

## Run the stages individually

```sh
python -m runner.run --provider gemini --model gemini-3.5-flash-lite --output results/local/my-run --limit 24 --samples 3 --allow-unreviewed
python -m scoring.judge results/local/my-run --provider gemini --model gemini-3.5-flash
python -m scoring.human queue results/local/my-run
python -m scoring.human assess results/local/my-run
python -m report.generate results/local/my-run --output report/generated
```

Remove `--allow-unreviewed` for reviewed data, and pass its path with `--dataset`.
The runner intentionally rejects unreviewed records unless that flag is explicit.
For Ollama, use `--provider ollama --model YOUR_LOCAL_MODEL --interval 0`.
Provider configuration and temperatures are recorded alongside the selected IDs,
dataset/prompt hashes, timestamps, exact returned versions, and raw responses.

`raw.jsonl` preserves every primary/sampling response before parsing;
`responses.jsonl` stores derived confidence estimates and any parse errors.
`grading/judge_raw.jsonl` preserves judge replies; human queues and original judge
grades stay separate. Report JSON/CSV contains per-model/category estimates,
denominators, bootstrap settings, and counts of undefined resamples.

## What still requires humans

- **Dataset:** Niloy must recruit a second native Bengali speaker. Independently
  review every candidate, resolve disagreement, expand coverage toward 400–600,
  archive time-sensitive sources, and freeze a version only after two sign-offs.
  Give each reviewer a separate [blank form](dataset/review-forms/batch01/) and
  follow the [version-bound review instructions](dataset/CONSTRUCTION.md).
- **Grading:** complete the blinded queue with real reviewer IDs, dates and
  rationales. Human grade fields currently remain null; judge/human agreement
  is unavailable. Dataset review and response grading are different tasks.
- **Validation:** submit completed human grades with
  `python -m scoring.human assess RUN_DIR --human-file COMPLETED.jsonl`.
  If agreement is low, use `python -m scoring.human queue RUN_DIR --expand` and
  obtain more human grading; do not hide disagreement by changing the judge prompt.
- **Research release:** perform full reviewed-dataset evaluations and write the
  final findings, including null results. No frozen dataset, validated leaderboard,
  full evaluation, or paper is claimed complete. `report.generate --release`
  enforces size, review, completion, and grading gates, including actual
  matching submissions supplied with `--dataset-reviews`.

See [construction guidelines](dataset/CONSTRUCTION.md),
[grading instructions](scoring/README.md), [metric definitions](metrics/README.md),
and [contribution guide](CONTRIBUTING.md).

## Scope

- Standard/formal Bengali: factual high certainty, Bangladesh-specific factual
  knowledge, temporal uncertainty, ambiguity/disagreement, unanswerable or
  adversarial premises, and Bengali-English code switching.
- $0 API budget: Gemini free tier, Groq free tier, and local Ollama only.
- Verbalized confidence and sampling agreement; token log-probabilities where
  supported.
- Calibration, hallucination, abstention, and risk-coverage, with question-level
  bootstrap 95% confidence intervals and an explicit judge/human agreement check.

This is not a general fluency/translation benchmark, harmful-content benchmark,
new model, or dialect-complete evaluation. Novelty is a research question to
verify through literature review, not an established result.

## Layout

```text
dataset/             Versioned JSONL, schema, validator, review guidelines
runner/providers/    Thin Gemini, Groq, and Ollama adapters
scoring/             Judge scoring, human-review queue, agreement
metrics/             Calibration, abstention, bootstrap uncertainty
results/             Raw run logs and computed metrics
report/              Methodology, generated tables/charts, limitations
```

## Phased plan and release gates

0. Establish taxonomy, schema, construction guidelines, and recruit reviewer two.
1. Draft and independently review 400–600 questions; freeze v0.1 only after sign-off.
2. Implement runner and confidence methods; run a 20–30 question smoke test.
3. Evaluate the reviewed dataset and preserve timestamped raw model output.
4. Judge responses, obtain human validation, resolve disagreements.
5. Compute bootstrap intervals, generate charts, and write honest findings.
6. Release reviewed data, code, and report.

Engineering dry runs may use drafts, but every resulting artifact must say
**PRELIMINARY, UNREVIEWED DATA**. Completing software does not complete the human
review or empirical phases.

## License and contributions

Code, original dataset drafts, and documentation are MIT licensed; source
references retain their own terms. Contribute original questions with concise
source notes rather than copying third-party question banks. Do not insert
reviewer identities without their actual review. Never commit credentials.

Maintainer: [Niloy Bhuiyan](https://github.com/Niloy-Bhuiyan).
