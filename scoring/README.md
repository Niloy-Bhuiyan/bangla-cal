# Scoring

Use a separate free-tier judge for initial correct/incorrect/partial scoring.
Humans must validate a random 10–15% sample; report agreement and expand human
grading when agreement is low. Behavioral categories need additional human
attention. An empty human queue result is pending validation, not agreement.

`python -m scoring.judge RUN_DIR --provider gemini --model gemini-3.5-flash`
grades a completed run using a separate model. Original raw judge replies are
saved before parsing; malformed labels are logged and routed for human grading.
Use `--resume` after interruption. The judge never sets dataset reviewed_by.

`python -m scoring.human queue RUN_DIR` selects a seeded uniform 15% validation
sample (rounded up, actual fraction saved) and adds every behavioral-category
response and failed judge parse. The queue omits model identity, judge labels,
and structured confidence when a parsed answer exists. For a malformed response,
raw text is shown, so blinding may be imperfect; reviewers should record this.

Humans copy the queue to a local completed file and fill in grade, abstained,
behavior_met, specific_unfounded, confident_language, rationale, reviewer_id,
and reviewed_at. They must not edit the question, answer or response hash.
AI assistants must leave these human fields null. Dataset review is a separate
two-native-speaker process. If a human disagrees with a judge, preserve the
independent first grade and document adjudication in resolution_note.

`python -m scoring.human assess RUN_DIR --human-file COMPLETED.jsonl` measures
agreement on the random sample only (not the behavior-enriched queue), including
95% question bootstrap intervals and Cohen's kappa. Original judge grades remain
unchanged. Human decisions take precedence in the derived scored.json artifact.
Unfilled queues yield null agreement and PENDING HUMAN VALIDATION.

Any agreement field below 0.8 requires expanded human grading and revalidation;
do not prompt-tune the judge until it agrees. Full human queue completion and
documented disagreement resolution are required by the validation gate. A passing
gate does not replace dataset review or justify strong findings from a small pilot.

Use `queue RUN_DIR --expand` to create a separate full-response queue while
preserving the original random sample and existing queue. Real humans can copy
their previous independent grades into the new completed file. If every response
is human graded, low judge agreement remains reported and the resulting scores
are labeled HUMAN GRADED; JUDGE LOW AGREEMENT, rather than claiming the judge passed.
