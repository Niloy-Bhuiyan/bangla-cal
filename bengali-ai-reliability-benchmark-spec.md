# BAN-CAL: A Calibration and Hallucination Benchmark for Bengali LLMs

**Provenance:** The requested source file was absent from the initial workspace.
This file preserves the complete build specification supplied in the initial
project request, with Markdown formatting normalized. Claims about novelty and
current providers/quotas below are proposals requiring verification, not findings.

**One-line pitch:** The first rigorous benchmark measuring whether large language models actually
know what they don't know when answering in Bengali — because every existing calibration/hallucination
benchmark (TruthfulQA, HaluEval, and the calibration studies from OpenAI/Anthropic/Google) is built
and validated in English, and nobody has measured whether a model's stated confidence means anything
in Bengali, a language spoken by ~230 million people with live commercial LLM deployment already
happening (banking chatbots, government service bots, edtech) with zero rigorous safety measurement
behind it.

This document is a complete build spec: problem, method, dataset design, evaluation protocol,
system architecture, and a phased build plan. It is written to be handed to a coding agent /
AI assistant as the primary implementation brief.

## 1. Problem statement

A model can be accurate on average and still be dangerous, because the failure mode that matters
is **confident wrongness**: the model states an answer with high apparent confidence when it should
have hedged or refused. This is measured by *calibration* (does stated/implied confidence match
actual correctness rate?) and by *hallucination rate on unanswerable questions* (does the model
invent an answer when the honest answer is "insufficient information" or "this is disputed/unknown"?).

English-language models are increasingly well-studied on this axis. Bengali is not, despite:

- ~230M speakers, one of the world's most-spoken languages
- Active commercial deployment in Bangladesh (customer service bots, government digital-service
  chatbots, edtech tutoring products) using general-purpose multilingual models with no
  Bengali-specific reliability testing
- A known general pattern in multilingual LLM research that models trained predominantly on
  English data are *less well-calibrated* in lower-resource languages — but this is rarely
  measured per-language, and never (as far as available literature shows) rigorously for Bengali
  specifically with a public dataset and reproducible protocol

**The gap this project fills:** produce a public, reproducible, methodologically sound answer to
"how much should you trust model X's confidence when it answers in Bengali, and how often does it
hallucinate instead of admitting it doesn't know?"

## 2. Goals and non-goals

**Goals**

- Build a benchmark dataset of Bengali-language questions purpose-built to expose calibration
  failures and hallucination, not just factual accuracy
- Evaluate a representative set of models people in Bangladesh actually use or could plausibly
  deploy (large multilingual frontier models + any Bengali-specific fine-tuned models that exist)
- Report calibration error, hallucination rate, and abstention behavior with statistical rigor
  (confidence intervals, not single point estimates)
- Release the dataset and results publicly so others can benchmark their own models against it
- Produce a written report/paper with the methodology and findings stated honestly, including
  what did *not* show a clear effect

**Non-goals (state these explicitly, don't drift into them)**

- This is not a general Bengali NLP benchmark (translation quality, fluency, grammar) — those exist
  in some form already (e.g. IndicNLP-adjacent work). This is specifically about calibration and
  hallucination.
- This is not a jailbreak/safety-content benchmark (harmful content generation). That's a different,
  already-crowded problem. Stay focused on epistemic reliability: does the model know what it knows.
- Not building a new base model or doing any pretraining. This evaluates existing models
  off-the-shelf (API calls and, optionally, locally-run open models).
- Not aiming for exhaustive coverage of every Bengali dialect/register on day one — start with
  standard/formal Bengali (Shuddho Bangla) as used in news, education, and government services,
  and state that scope limitation explicitly.

## 3. Core concepts the builder needs to understand

- **Calibration**: a model is well-calibrated if, among all the times it expresses (or implies)
  X% confidence, it is actually correct about X% of the time. Measured via **Expected Calibration
  Error (ECE)**: bucket predictions by stated confidence, compare average confidence per bucket to
  actual accuracy per bucket, take the weighted average absolute gap.
- **Brier score**: mean squared error between stated confidence (as a probability) and the
  correctness indicator (1 or 0). Lower is better. Use alongside ECE since ECE can hide binning
  artifacts.
- **Hallucination (for this project's purposes)**: a confident, specific, wrong or unfounded answer
  to a question that should have been answered with abstention, uncertainty, or "this is disputed" —
  specifically on the **unanswerable/adversarial** question category (see Section 4). This is a
  narrower, more measurable definition than "any factual error," and it's the one that maps directly
  to real-world risk (a chatbot inventing a fake bank policy is a hallucination in this sense even if
  it "sounds right").
- **Abstention precision/recall**: on questions designed to require abstention, does the model
  correctly abstain (recall), and when it abstains, is it usually right to (precision, i.e. it isn't
  abstaining on easy answerable questions too)?
- **Risk-coverage curve**: if you only accept the model's answer when its stated confidence exceeds
  threshold T, what fraction of questions can you "cover" (answer) at what accuracy, as T varies?
  This is the single most informative chart in the whole project — it directly answers "how much of
  this workload could you safely automate."
- **Eliciting confidence from a model that doesn't give you a probability by default**: three
  standard methods, use at least two for cross-validation:
  1. **Verbalized confidence** — ask the model to state a 0–100% confidence alongside its answer,
     in the same turn, in Bengali
  2. **Log-probability of the answer token(s)** — where the API exposes logprobs (works for some
     providers/open models, not all)
  3. **Self-consistency / sampling agreement** — sample the same question N times (e.g. N=10) at
     nonzero temperature, use the fraction of samples that agree as a proxy confidence

## 4. Dataset design

### 4.1 Question categories (this taxonomy is the intellectual core of the project — build it carefully)

1. **Factual — high certainty** (should be answerable, unambiguous, verifiable ground truth exists)
   Example domain: geography, basic science, well-documented history, arithmetic in Bengali numerals.
2. **Factual — low-resource / Bangladesh-specific** (answerable but requires knowledge a
   predominantly-English-trained model is less likely to have): local history, regional geography,
   Bangladeshi government service procedures, local cultural/literary facts. This category is
   expected to show the clearest calibration gap and is the most novel contribution — almost no
   existing benchmark tests this.
3. **Temporally unstable** (correct answer changes over time — current officeholders, recent prices,
   ongoing events): tests whether the model hedges appropriately given its training cutoff, rather
   than confidently stating stale facts as current.
4. **Ambiguous / contested** (reasonable sources disagree, or the question is underspecified):
   correct behavior is to present the disagreement, not pick one answer confidently.
5. **Unanswerable / adversarial (the hallucination-detection category)**: questions with false
   premises, fictional entities presented as real, or genuinely no-information questions
   ("What is the population of [invented place name]?"). Correct behavior is refusal or explicit
   "I don't have reliable information about this," never a specific invented answer. This category
   is where you compute the primary hallucination-rate metric.
6. **Code-switched / mixed Bengali-English** (common in actual Bangladeshi usage — tests robustness
   to how people really type, not textbook-standard Bengali).

### 4.2 Construction methodology

- Target **400–600 questions total** for a first release (quality over quantity — a smaller,
  carefully verified dataset is more credible than a large noisy one), roughly evenly split across
  the six categories, with 4–5 held out for a small pilot/calibration-of-the-benchmark-itself round.
- Every question needs: the question text (Bengali), the category label, a ground-truth answer or
  ground-truth *behavior* (for categories 4–6, the "ground truth" is often "should abstain/hedge,"
  not a specific answer), and a short justification/source note.
- **Native-speaker verification is mandatory** for every question — this is the part an AI coding
  agent cannot do alone; budget explicit human review time in the plan. Two independent native
  Bengali speakers should review each question for: is it actually unambiguous (for categories 1–3),
  is the "false premise" in category 5 actually false and not just obscure, is the phrasing natural
  Bengali and not a translation artifact.
- Store as versioned JSONL, one question per line, schema:

```json
{
  "id": "ban-cal-0001",
  "category": "factual_low_resource",
  "question_bn": "...",
  "question_en_gloss": "... (for the builder's/reviewer's reference only, not shown to models)",
  "expected_behavior": "answer | abstain | hedge_disagreement | hedge_temporal",
  "ground_truth_answer": "... or null",
  "source_note": "...",
  "difficulty_tier": "easy | medium | hard",
  "reviewed_by": ["reviewer_1_id", "reviewer_2_id"],
  "notes": "..."
}
```

## 5. Models to evaluate (first release — free-tier and local only)

**Budget constraint: v1 has $0 API budget.** This is a hard constraint on the build, not a nice-to-have —
do not design the runner around paid frontier APIs and treat free access as an afterthought. Every
model in v1 must be reachable at zero cost:

- **Google Gemini API free tier** — usable rate-limited free access, no card charge at the free
  quota level. Use the current Gemini free-tier model at build time.
- **Groq API free tier** — free, fast inference for current open-weight models (Llama 3.x family,
  Mixtral, etc.) at generous rate limits.
- **Locally-run open models via Ollama** — Llama, Mistral, Qwen, Gemma, or whatever current
  generation is available; fully free, no API key, runs on the developer's own machine. Slower
  per-query but zero cost and zero rate limit beyond hardware.
- **Kaggle's free GPU quota (30 hrs/week)** as a fallback for running a local open model if the
  developer's own machine can't handle it — this mirrors an existing personal workflow already used
  for other research work, so treat it as a known, reliable option, not a new thing to figure out.
- **Any Bengali-specific fine-tuned model that is freely hostable** (e.g. BanglaBERT-family, if
  applicable to the task type — note that some of these are encoder-only and may not be a fair
  comparison for generative QA; document this limitation rather than forcing a bad comparison).

**Explicitly out of scope for v1:** OpenAI GPT and Anthropic Claude API access (paid, no meaningful
free tier at this volume). Do not build a provider adapter for them yet — leave a placeholder
interface so one can be added later, but do not spend build time or any money integrating them now.

State the v1 model list's cost basis explicitly in the report: "evaluated against freely accessible
models only; proprietary frontier models (GPT, Claude) excluded from v1 due to cost, left as future
work pending research credits or sponsorship." This is a legitimate, honest scope — say it plainly,
don't apologize for it.

Explicitly exclude/flag any model with no usable confidence-elicitation method (Section 3, point 5)
rather than silently reporting a broken number for them.

### 5.1 If frontier models are added later (future work, not v1)

For roughly 500 short Bengali Q&A queries, one pass, current GPT/Claude-class pricing is realistically
in the range of a few dollars total per model — cheap enough to self-fund later, or to justify a small
ask for research/student API credits once v1's free-tier results already show a real finding. Do not
block v1 on this.

## 6. Evaluation protocol

1. For every question × every model: run the query, apply all applicable confidence-elicitation
   methods, log the raw response text, extracted answer, and each confidence estimate.
2. **Grading**: for categories 1–3, correctness needs to be judged against ground truth.
   - Use an LLM-as-judge pass for initial scoring (a separate, strong model given the question,
     ground truth, and the response, asked to score correct/incorrect/partial) **but** validate the
     judge itself: have humans grade a random 10–15% sample and report judge/human agreement rate.
     If agreement is low, this needs more human grading, not a better prompt.
   - For categories 4–6, grading is about *behavior* (did it abstain/hedge appropriately), which is
     more subjective — lean more heavily on human grading here, since this is exactly the part
     that matters most and is least safe to automate.
3. **Compute per model, per category, and overall:**
   - ECE and Brier score (categories 1–3, where a real ground truth exists)
   - Hallucination rate (category 5 specifically: % of responses that give a confident specific
     wrong answer instead of abstaining)
   - Abstention precision/recall (category 5, and secondarily category 4)
   - Risk-coverage curve (using verbalized confidence as the threshold variable) across the whole
     answerable-question set
4. **Report uncertainty on your own numbers**: bootstrap confidence intervals on all headline
   metrics (resample questions with replacement, recompute, report 95% CI). A single ECE number
   with no interval is not a credible result at this dataset size.
5. **Report negative/null findings honestly**: if a model turns out to be well-calibrated in
   Bengali, or if a category shows no measurable gap, say so. The credibility of the whole project
   depends on not cherry-picking the categories that show the expected effect.

## 7. System architecture

Keep this simple and modular — the dataset and the findings are the product, not the software.

```text
/dataset/          -- versioned JSONL question sets + a schema validator script
/runner/           -- unified client that takes (question, model_config) -> raw response + logprobs if available
    /providers/    -- one thin adapter per free-tier/local backend (Gemini, Groq, Ollama);
                      leave a stub interface for OpenAI/Anthropic to be added later, unimplemented in v1
/scoring/          -- grading pipeline: LLM-as-judge pass (use a free-tier model, e.g. Gemini, as the
                      judge -- do not spend paid-API budget on grading either) + human-review queue +
                      agreement calculator
/metrics/          -- ECE, Brier, hallucination rate, abstention precision/recall, risk-coverage, bootstrap CIs
/results/          -- raw run logs (one JSONL per model per run) + computed metrics tables
/report/           -- generated tables/charts + the written methodology report
```

**Suggested stack** (lightweight, matches typical Python ML tooling, no need to over-engineer):

- Python throughout for the runner/scoring/metrics pipeline
- Provider adapters behind one common interface (mirrors the "swappable provider" pattern already
  proven useful elsewhere: one interface, pluggable backends, including a local-model backend via
  vLLM or Ollama for the open-source models)
- A plain SQLite or DuckDB file for run results if a full database feels like overkill — this
  project's data volume does not need Postgres
- Charts via matplotlib/plotly for the risk-coverage curves and calibration diagrams
- A minimal static site (or a single Jupyter/Observable notebook) to publish the leaderboard —
  do not over-invest in a fancy dashboard before the numbers are trustworthy

## 8. Deliverables

1. The dataset (JSONL, versioned, publicly released with a clear license and the review methodology
   documented)
2. The runner + scoring + metrics code (open source)
3. A written report: methodology, per-model results with confidence intervals, the risk-coverage
   charts, and an honest limitations section (dataset size, judge-model validation results, dialect/
   register scope, which models could not be fairly evaluated and why)
4. Optionally, a small public leaderboard page others can submit new model results against later

## 9. Phased build plan

- **Phase 0 (methodology, ~1–2 weeks):** finalize the category taxonomy and JSONL schema, write
  the question-construction guidelines, recruit the second native-speaker reviewer.
- **Phase 1 (dataset, ~3–4 weeks):** write and review the first 400–600 questions, two-reviewer
  sign-off on every question, freeze v0.1 of the dataset.
- **Phase 2 (runner, ~1–2 weeks):** build the provider adapters and confidence-elicitation logic,
  do a small smoke-test run (20–30 questions) to catch schema/prompting bugs before spending API
  budget on the full run.
- **Phase 3 (full evaluation run, ~1 week):** run all models against the full dataset, log
  everything raw before computing any metrics.
- **Phase 4 (grading, ~2 weeks):** LLM-as-judge pass, human-validation sample, resolve
  judge/human disagreement, finalize scores.
- **Phase 5 (metrics + report, ~1–2 weeks):** compute ECE/Brier/hallucination rate/abstention
  metrics with bootstrap CIs, generate risk-coverage charts, write the report.
- **Phase 6 (release):** publish dataset + code + report; consider submitting the writeup as a
  paper or workshop submission once results are solid.

## 10. Known risks / honest limitations to carry into the writeup

- Small dataset size (400–600 questions) limits statistical power for fine-grained per-category
  claims — the bootstrap CIs will make this visible rather than hiding it, which is the correct
  behavior, not a flaw to fix by inflating the dataset artificially.
- LLM-as-judge grading has known biases (can favor certain phrasing styles); the judge/human
  agreement check in Phase 4 is not optional.
- Standard/formal Bengali only in v1 — regional dialect coverage is future work, state this
  explicitly rather than implying broader coverage than what was tested.
- Model behavior can change between the evaluation run and publication (API model updates) —
  timestamp every run and note the exact model version/snapshot used.

## 11. Success criteria

The project succeeds if it produces a **specific, defensible, previously-unknown finding** stated
with a number and a confidence interval — for example (illustrative, not a prediction of the
actual result): "Model X's stated confidence is well-calibrated in the factual-high-certainty
category (ECE 0.04, 95% CI [0.02, 0.07]) but its hallucination rate on unanswerable
Bangladesh-specific questions is 3.2x higher than on the equivalent English-language version of the
same questions." That sentence — concrete, numeric, honestly bounded — is the actual deliverable.
Everything else in this document exists to make that sentence true and defensible.
