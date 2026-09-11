# Local research interface

Run from the repository root after installing `requirements.txt`:

```sh
python -m interface.server
```

Open **http://127.0.0.1:8765**. Use `--port 8766` if the port is occupied.
The interface uses the Python standard library and local HTML/CSS/JavaScript;
there is no frontend installation, build step, cloud hosting, or additional
dependency. Keep the terminal running; Ctrl+C stops the server and its task.

## Four workspaces

- **Results & overview:** select an archived or locally generated report,
  inspect model/category metrics and 95% bootstrap intervals, view calibration
  and risk–coverage charts, and download the report, CSV, or JSON. Small sample
  sizes, incomplete judging, and pending human validation remain visible.
- **Dataset review:** filter/search questions, inspect Bengali text and source
  notes, and submit your own native-speaker review. All checks start undecided.
  Other reviewers' submissions are not displayed. The first decision for each
  reviewer/question revision is preserved; substantive changes need fresh review.
- **Evaluations:** create a local copy of an archived run, start or resume
  generation, use a separate free/local judge, prepare/assess human queues,
  expand a queue after low agreement, and generate reports. The task log shows
  actual progress and provider errors. Only one task runs at a time.
- **Human grading:** work through the blinded queue, supplying actual reviewer
  IDs, dates, labels, and rationales. Saving a grade advances to the next answer.
  Refresh assessment to calculate agreement; saving a grade alone does not
  claim validation or update an existing report.

## A practical first session

1. Open Results to inspect the actual preliminary smoke report without API calls.
2. In Evaluations, create a local working copy of an archived run. The archive
   remains read-only. Preparing its existing queue and generating a report from
   saved grades require no provider calls.
3. A real human can complete its queue in Human grading. Use Prepare / assess
   queue afterwards, then Generate report to include those submissions.
4. Resume machine judging only when the actual free quota is available. Keep the
   original judge/provider, token limit, and interval on existing runs; the runner
   rejects changed plans. A different judge requires a separate grading workflow.

For a new evaluation, explicitly allow drafts if needed. The default smoke plan
is 24 questions with three samples per primary answer: 96 generation requests.
Full evaluations normally use ten samples. Five held-out pilot example IDs stay
excluded. Gemini/Groq model IDs can change; enter a currently available ID from
your free-tier account, or an installed local Ollama model. Keys load from the
repo's `.env` or existing environment variables; restart after changing them.

Stopping a task terminates its worker. Saved raw samples remain resumable; an
in-flight request may not have been saved and may need to be repeated. Stop or
finish the current task before making another submission. The interface makes
no paid fallback and never changes account billing settings.

## Files and independent review

All interface-created runs and submissions are under gitignored `results/local/`.
Native-speaker submissions are stored in
`results/local/interface/dataset-reviews/REVIEWER_HASH.jsonl`. The save message
identifies the file. These are actual human submissions only: the software and
its tests do not assign reviewer identities to the real dataset or change
`reviewed_by`. The maintainer must verify identity/independence, adjudicate, and
update reviewed dataset revisions using the construction protocol.

Each local run keeps human grades in `grading/interface_human.jsonl` and creates
`grading/interface_assessment.jsonl` when assessing. Keep the first submissions
unchanged. For disagreement resolution, a human supplies `resolution_note` in
a separate completed copy and ingests it with `scoring.human assess --human-file`;
the interface preserves already ingested human decisions and resolution notes.
The interface does not automate adjudication. Generated reports go under
`report/generated/RUN_NAME/` and become selectable in Results after refresh.

Dataset corrections, evidence export/submission in a review PR, and final
reviewed release remain maintainer workflows described in the root README.
This is a single-machine research tool, not an authenticated multi-user service.
It binds only to loopback, requires an unpredictable token for writes, checks
request origin/host, and serves only named assets and report files. Do not expose
it through a public tunnel or change its binding to publish it as a service.
