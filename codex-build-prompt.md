# Build instructions

Reconstructed from the maintainer's instructions in this task; the file was
absent from the original workspace. The full research scope is in
`bengali-ai-reliability-benchmark-spec.md`.

- GitHub account: Niloy-Bhuiyan; repository: bangla-cal (maintainer-approved rename).
- Commit author: Niloy Bhuiyan. Use the locally configured GitHub noreply email
  (maintainer-approved replacement for the original private address).
- Keep git identity local to this repo. Commit and push each step separately to
  origin/main. Commits must run, be reviewable, and have descriptive messages
  without AI attribution or coauthor trailers.
- Remaining order: (1) schema, validator, examples; (2) draft dataset across all
  six categories; (3) Gemini/Groq free-tier and Ollama adapters; (4) verbalized
  confidence and self-consistency; (5) metrics with synthetic unit tests including
  bootstrap CIs; (6) judge pipeline and human queue/agreement; (7) draft smoke
  test; (8) report generation from smoke output; (9) setup/status README.
- $0 API budget. Do not implement or call paid OpenAI/Anthropic integrations.
  Leave an unimplemented future interface. No automatic paid fallbacks.
- Research/data, not a fancy product. Use the specification's simple Python layout.
- Draft a first batch toward 400–600 questions, roughly evenly split. Every
  AI-drafted record must have reviewed_by: [] and say AWAITING HUMAN REVIEW.
  Two independent native Bengali speakers must actually review each question.
- Any output from draft data must say PRELIMINARY, UNREVIEWED DATA.
- Bootstrap 95% confidence intervals and random 10–15% judge/human validation
  are essential. Do not manufacture reviews, human grades, or empirical results.
- Stop for missing GitHub auth/repo access, proposed changes to the target
  size/category split, human sign-off, or actual free-tier limits that require
  a batching plan. Report actual blockers; never fake success or buy API access.
- Continue useful authorized work through all remaining steps, without pausing
  merely because a small checkpoint is finished.
