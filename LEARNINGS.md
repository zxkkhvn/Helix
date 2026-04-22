# Helix — Learnings

Non-obvious decisions and gotchas. Read before modifying scoring or instrument logic.

## Instrument Definitions

- **PAQ-S items are a subset of PAQ.** The 6 PAQ-S items map to specific PAQ items via `carry_forward_items`. The mapping is NOT sequential (paq_s_01 maps to paq_09, not paq_01). Always check the JSON def.
- **PAQ scoring method is `custom`**, not `sum`. Despite being a Likert scale, the 5-subscale structure with valence-specific grouping requires a custom scorer. The total score is technically a sum but the subscale output is the clinically meaningful result.
- **Instrument item text is verbatim from published sources.** Never rephrase, simplify, or localise. This is a locked architectural decision — changing validated wording invalidates psychometric properties.
- **`response_option_sets` is a top-level key**, not inline per item. Items reference sets by key (`response_options_key`). This keeps definitions DRY when all items share the same scale.

## Scoring Engine

- **No pandas in the scoring path.** numpy only. pandas is allowed exclusively in `reports/`.
- **Composite indices use mean of z-scores**, not sum. Re-standardisation after mean-z is explicitly excluded — composite SD < 1.0 is expected and acceptable.
- **PBAT is exempt from composite z-standardisation.** It's formative, not reflective. Item-level profile is the output. No total score as primary metric.

## Safety

- **Safety flags persist in the database.** Closing the browser does not clear SAFETY_PAUSED state. On session resume, unacknowledged safety flags must display crisis resources before any other content.
