# Research preview release notes

**PRELIMINARY, UNREVIEWED DATA. This package is a software/research preview,
not the completed v0.1 benchmark or a publication-ready empirical paper.**

## What can be published now

The MIT-licensed source, documented methodology, original unreviewed draft,
offline tests, and labeled real-model smoke artifacts are available for public
inspection and contribution. Cite the repository and exact Git revision using
`CITATION.cff`; no DOI, paper acceptance, or novelty claim is asserted.

The interface is a Python command line and generated Markdown report with CSV,
JSON, and PNG figures. No hosted interactive dashboard is required by the spec.

The software includes free-tier Gemini/Groq and local Ollama adapters, resumable
raw logs, verbalized and sampling confidence, known-answer metric tests,
question-level bootstrap intervals, a separate judge, blinded human grading,
agreement checks, and report generation with provenance/review gates. OpenAI and
Anthropic remain unimplemented future interfaces. No paid API fallback exists.

## Evidence included

| Item | Actual status |
| --- | --- |
| Draft candidate batch | 60, ten per category; all unreviewed |
| First-release dataset target | 400–600, roughly balanced; unchanged |
| Native-speaker reviews | Zero; two blank independent forms supplied |
| Real generation smoke | 24 identical questions per model, Gemini and Groq |
| Raw generation replies | 192; primary plus three samples per question/model |
| Initial judge grades | 21 of 48; 27 pending |
| Human response grades | Zero; agreement unavailable |
| Ollama | Adapter implemented; not empirically evaluated in this smoke |
| Empirical finding / model ranking | Not established |

The separate Gemini judge exhausted the returned daily free quota of 20
requests per project/model. Finish the remaining 27 grades in two new quota
windows (20 then 7), retaining the raw evidence. Commands are in the root README.
Short retry-delay hints do not override a daily quota. No scheduled job has been
created and no paid upgrade is needed. New quota availability has not been
assumed in preparing this preview.

## Reproduce the preview without API access

From the repository root, with Python 3.10+:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -v
python -m dataset.validate dataset/examples.jsonl dataset/draft-v0.1-batch01.jsonl
python -m report.generate results/smoke-2026-09-11/gemini results/smoke-2026-09-11/groq --output report/generated
```

These commands use saved actual responses and machine judgments. Tests use
clearly synthetic temporary fixtures; they never supply the published model
results or human reviews. No `.env` is needed to reproduce the archived analysis.
The smoke environment is recorded in `results/smoke-2026-09-11/environment.json`.
Dependency ranges support new installations; recorded versions identify the
original environment. CI checks Windows/Linux and Python 3.10/3.13, including
exact equality of the saved metric summaries and bootstrap intervals.

Report generation verifies raw samples, derived confidences, reference fields,
and bound scoring inputs before it computes metrics. Native-speaker review
evidence is additionally required for `--release`. Hashes detect inconsistent
artifacts; they do not authenticate a reviewer or establish factual correctness.

## Gates before a completed research release

1. Niloy recruits a second native Bengali speaker. Both independently review
   the initial batch, verify sources and naturalness, and resolve disagreements.
2. Expand domain coverage toward 400–600 questions using that feedback. Archive
   dated temporal answers, repeat review after substantive changes, and freeze
   a version with two evidenced sign-offs per item and a SHA-256 manifest.
3. Run the full frozen dataset, preserving model versions and all raw outputs.
   Smoke uses three samples; the normal sampling protocol defaults to ten.
4. Complete separate-model judging and real human validation. Preserve blinded
   first decisions. Expand human grading when agreement is low; adjudicate
   disagreements rather than tuning the judge to hide them.
5. Produce final per-model/category results and bootstrap intervals, disclose
   missing/excluded cases and null effects, and verify related work before any
   novelty claim. The initial graded subset cannot support a leaderboard.

These are research requirements, not optional packaging work. An AI assistant
cannot fill in native-speaker approvals or human grades on the reviewers' behalf.

## Packaging

Build a source preview from a committed revision with `git archive`, which
includes tracked files only. Exclude local credentials, caches, and instruction
files. Keep a SHA-256 checksum and the exact source commit next to the archive.
Label any eventual GitHub release as a **prerelease / research preview** until
the gates above are met. A source archive is not a reviewed dataset freeze.
