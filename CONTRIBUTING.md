# Contributing

Start with the [specification](bengali-ai-reliability-benchmark-spec.md) and
[construction protocol](dataset/CONSTRUCTION.md). Contributions should improve
the dataset or the reliability of the measurements, with small reproducible changes.

## Questions and native-speaker review

Submit original Bengali questions using the exact JSONL schema and new stable
`ban-cal-NNNN` identifiers. Include an English gloss for reviewers, a precise
answer or expected behavior, and a primary-source URL or self-contained proof.
Keep `reviewed_by: []` and **AWAITING HUMAN REVIEW** in notes until actual review.

Two independent native Bengali reviewers must check phrasing, factual truth,
false premises, ambiguities, and the behavior rubric. Record reviewer identity,
date, decision and content revision before adjudication. Do not count an AI pass
as either review. Never copy another person's reviewer ID onto a question.
Changing an accepted question requires renewed review.

The current 60-item batch needs broader local history, regional geography,
literature and government-service coverage. Temporal items need archived sources
and dates. The 400–600 target and balanced six-category taxonomy remain unchanged.

## Human grading

Human response grading is separate from dataset review. Use the blinded queues
and retain initial independent decisions. Supply factual/behavioral reasons for
grades, especially abstention versus a disclaimer followed by an invention.
Do not fill confidence gaps with guessed numbers. Report judge disagreements;
low agreement calls for expanded human grading, not hiding inconvenient items.

## Code and results

Run `python -m unittest discover -v` and the dataset validator before proposing
changes. Document metric denominator or prompt changes and increment the relevant
protocol version before new runs. Synthetic test fixtures belong in tests, never
in published empirical results. Do not overwrite old raw responses or queues.

Use only Gemini/Groq free-tier accounts or local Ollama. Never commit keys, `.env`,
private reviewer contact details or private input data. Inspect raw outputs before
publishing. Preserve hashes, model versions, dates, and negative or null findings.

Code, original drafts and documentation are MIT licensed. External references
retain their own copyright and terms; links do not relicense source material.
