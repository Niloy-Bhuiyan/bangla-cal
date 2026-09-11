# Interface design decisions

The maintainer requested a minimal, more usable interface and rejected the
original green/cream palette. This revision uses a white canvas, charcoal text
and buttons, gray separators, and blue only for links and keyboard focus. Chart
colors remain part of the existing research artifacts.

## What changed

- Replace the large sidebar, numbered navigation, decorative mark, and marketing
  headlines with four plain top-level destinations.
- Present results in a table with estimate and confidence interval columns.
  Summary counts use one text line, not a row of metric cards.
- Keep the preliminary-data notice visible once per selected report. Simplifying
  the presentation must not imply that incomplete research is validated.
- Display one chart at a time, with explicitly labeled chart buttons. Charts
  cover all models in the report; the table's model/category filters are separate.
- Open evaluation and judging forms only on request. Put token/interval settings
  behind Advanced settings, retain explicit labels, and show the actual request
  count before starting an evaluation.
- Use undecided yes/no radio groups for human review. Preserve unfinished forms
  while navigating during the current page session. Refreshing the page clears
  unsaved drafts; submitted reviews remain in the local files.
- Place less common run actions in an expandable menu and collapse completed
  task logs. Keep controls visibly clickable and keyboard accessible.

## Research that informed this revision

An [independent design critique of repetitive AI-generated sites](https://www.joshuasnoddy.com/blog/why-ai-websites-look-the-same/)
describes recurring template choices such as generic hero sections, repeated
cards, and default decorative treatments. This is practitioner commentary,
not evidence that any single font or component proves AI authorship.

[NN/g's aesthetic and minimalist design guidance](https://www.nngroup.com/articles/aesthetic-minimalist-design/)
focuses on removing information and decoration that do not support user tasks.
Its [minimalism analysis](https://www.nngroup.com/articles/characteristics-minimalism/)
also cautions against removing the cues that make controls understandable.
Those task-oriented principles guide this application rather than a universal
ban on common web components.

The question validator, raw evidence, grading rules, model adapters, and numerical
results are unchanged. Browser checks cover task navigation, draft preservation,
dialog controls, data filters, and narrow-screen layouts; they do not confer any
human review on the benchmark data.
