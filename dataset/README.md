# Dataset

**AWAITING HUMAN REVIEW.** No frozen or native-speaker-verified dataset exists.
Every AI-drafted record must have `reviewed_by: []`. Release requires two
independent native Bengali reviewers per question and a documented revision.

Target: 400–600 original questions, roughly balanced across six categories;
4–5 reserved for a pilot. JSONL files are UTF-8, one question per line.

## First candidate batch

`draft-v0.1-batch01.jsonl`: 60 candidates, 10 per category, IDs 0101–0160.
**AWAITING HUMAN REVIEW** appears in every record; every reviewed_by is empty.
This is a first batch toward 400–600, not a reduced release target. The six schema
examples are separate; five example IDs are reserved in pilot_ids.json.

Known draft gaps: Bangladesh-specific items currently emphasize heritage;
subsequent batches need regional geography, local history, literature and services.
Unanswerable items emphasize missing information and logically false premises;
human-checked fictional-entity items are still needed. Temporal ground truths
remain null pending dated source capture, so they support behavioral grading but
not factual calibration yet. Do not infer topic coverage or statistical findings
from this deliberately small draft.

Validate with `python -m dataset.validate dataset/draft-v0.1-batch01.jsonl`.
Release gating uses `--require-reviewed`, which intentionally fails on drafts.
See CONSTRUCTION.md for review evidence and release requirements.
