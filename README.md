# Bangla-Cal

A Bengali-language research benchmark for whether a language model's confidence
matches its correctness, and whether it admits uncertainty instead of inventing
answers. The deliverables are a carefully reviewed dataset and reproducible
statistical findings, supported by a small Python evaluation pipeline.

Repository name: `bangla-cal`. The original specification calls the benchmark
BAN-CAL; dataset identifiers retain its `ban-cal-` prefix for schema compatibility.

## Status: Phase 0 — methodology

**AWAITING HUMAN REVIEW.** No dataset has been validated, no model has been
evaluated, and no empirical finding is claimed. AI-drafted questions must retain
`reviewed_by: []` until two independent native Bengali speakers actually review
them. Niloy and a second native speaker must check facts, premises, behavior
targets, and natural phrasing before a trustworthy dataset release.

The v0.1 target is 400–600 questions, roughly evenly distributed across six
categories, with 4–5 questions reserved for a pilot. The exact release size will
depend on human verification. Drafts are not a frozen release.

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
