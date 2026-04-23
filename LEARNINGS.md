# Helix — Learnings

Non-obvious decisions and gotchas. Read before modifying scoring or instrument logic.

## Instrument Definitions

- **PAQ-S items are a subset of PAQ.** The 6 PAQ-S items map to specific PAQ items via `carry_forward_items`. The mapping is NOT sequential (paq_s_01 maps to paq_09, not paq_01). Always check the JSON def.
- **PAQ scoring method is `custom`**, not `sum`. Despite being a Likert scale, the 5-subscale structure with valence-specific grouping requires a custom scorer. The total score is technically a sum but the subscale output is the clinically meaningful result.
- **Instrument item text is verbatim from published sources.** Never rephrase, simplify, or localise. This is a locked architectural decision — changing validated wording invalidates psychometric properties.
- **`response_option_sets` is a top-level key**, not inline per item. Items reference sets by key (`response_options_key`). This keeps definitions DRY when all items share the same scale.
- **CPQ licence is restrictive.** The PDF copyright reads "permission to photocopy granted to purchasers of this book for personal use only" (Fairburn, Cooper & Shafran 2003, Guilford Press). This covers personal/clinical photocopying, not digital deployment. Explicit permission from the authors or Guilford Press is required before Helix can present CPQ items to users.
- **DSS-B is the DSM-5 Level 2 Cross-Cutting Symptom Measure for Dissociation** (not the Brief DES-B). 10 items, 0–4 Likert, free from APA. Replaces "Brief DES-B" throughout the spec. Instrument ID: `dss_b`.
- **DTS scoring: item 6 is the only reverse-scored item.** Scale is 1=Strongly agree → 5=Strongly disagree. All items are negatively worded (agreement = low tolerance) *except* item 6 ("I can tolerate being distressed or upset as well as most people"), which must be reversed (5-x+1). Sum after reversal, range 15–75. Higher = greater distress tolerance. Sign-invert for composite contributions where higher z = worse outcome.
- **CPQ scoring: items 2 and 8 are reverse-scored.** Forward items (1,3,4,5,6,7,9,10,11,12): 1=not at all → 4=all of the time. Reverse items (2,8): 4=not at all → 1=all of the time. Total = sum, range 12–48. No published clinical cut-off; higher = more clinical perfectionism.

## Scoring Engine

- **No pandas in the scoring path.** numpy only. pandas is allowed exclusively in `reports/`.
- **Composite indices use mean of z-scores**, not sum. Re-standardisation after mean-z is explicitly excluded — composite SD < 1.0 is expected and acceptable.
- **PBAT is exempt from composite z-standardisation.** It's formative, not reflective. Item-level profile is the output. No total score as primary metric.

## Safety

- **Safety flags persist in the database.** Closing the browser does not clear SAFETY_PAUSED state. On session resume, unacknowledged safety flags must display crisis resources before any other content.
- **PHQ-9 item 9 has a neurodivergent non-invariance exception (Section 37.1).** When Uranus (Neurodivergence) is AVAILABLE or higher, item 9 > 0 shows a clarification screen ("urgent/frightening" vs "passing/philosophical") instead of immediate SAFETY_PROTOCOL. "Yes, urgent" fires full protocol. "No, passing" shows crisis resources as information but allows continuation. `item9_clarified_passive: bool` stored on AssessmentInstance. For all users without Uranus activation, item 9 > 0 fires full SAFETY_PROTOCOL unconditionally.
- **Accessible instrument presentation mode (Section 37.3).** When Uranus reaches SCANNED or intake intent = \"neurodivergent\", framing text is simplified and idioms removed. Validated item text is NEVER changed — only surrounding instructions and AI narration adapt.

## Testing

- **SQLite `:memory:` requires `StaticPool` in FastAPI tests.** Each call to `create_engine("sqlite:///:memory:")` without a pool class creates a fresh empty database per connection. `Base.metadata.create_all(engine)` writes tables to connection A; `SessionLocal()` opens connection B — empty DB, `no such table` error. Fix: pass `poolclass=StaticPool` so all connections share the same in-memory instance. Required whenever using an in-memory SQLite DB with FastAPI's `TestClient`.

  ```python
  from sqlalchemy.pool import StaticPool
  engine = create_engine(
      "sqlite:///:memory:",
      connect_args={"check_same_thread": False},
      poolclass=StaticPool,
  )
  ```

## Routing

- **`unlock_planet` routing action.** Added for cross-planet triggers. When ASRS Part A scores >= 12, it fires both `trigger_expansion` (→ asrs_full) and `unlock_planet` (→ uranus). The routing engine collects unlock targets in `RoutingAction.unlock_planets: list[str]`. The API layer is responsible for persisting planet state changes.
- **ASRS Part A threshold is 12** (Likert sum), not the original dichotomous "4 shaded boxes". Average of 2.0 per item = "Sometimes" frequency, chosen for sensitivity. Can be tuned with real data.

## Instrument Definitions

- **GenericScorer supports two reverse-scoring patterns.** Per-item `"reverse_scored": true` (used by PSS-10, DTS) and scoring-level `"reverse_items": ["item_id", ...]` list (used by CompACT, MLQ). The list approach is cleaner for instruments with many reversed items (CompACT has 14).
- **VLQ scoring is custom.** The `total_score` is the mean gap (importance - consistency) across domains where importance >= 7. The composite score (mean of importance * consistency) is stored in `metadata["composite_score"]`. The `valued_living_gap` composite in `composites.json` uses `computation: "custom"` and delegates to the VLQ scorer output rather than z-standardising.
- **BDEFS-SF item text is placeholder.** All 20 items have TODO markers. The instrument is proprietary (Guilford Press). Structural definition (subscales, scoring, range) is correct. Verbatim text needs to be transcribed from the licensed PDF in `Test Battery/Mars/`.
- **CompACT is the full 23-item version** (Francis et al. 2016), not a 10-item brief. The implementation state spec explicitly says "Full 23-item version used — no validated brief form exists."
