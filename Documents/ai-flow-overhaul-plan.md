# Helix — AI Flow & Planet Navigation Overhaul Plan

> **Audience:** implementation agent.
> **Read order:** phases are dependency-ordered. Do not skip ahead. Each phase must pass its own tests before the next begins.
> **Test-driven development is mandatory** (per `CLAUDE.md`). Write tests before or alongside each change.
> **Do not introduce abstractions beyond what each phase requires.** Three similar lines is better than premature factoring.

---

## 0. Context

The current AI flow (`backend/helix/ai/`) is mechanically correct but has six issues:

1. **Milestone trigger is semantically blind** — `delta >= 3 instruments` lives client-side and ignores theme saturation. Three instruments on one planet trigger a Full Formulation that produces SPARSE refusals.
2. **AI outputs are verbose** — Full Formulation worst-case is ~1250 words; Planet Summary ~400; user fatigue is high.
3. **No planet recommendation despite intake ranking** — `intake_data.top3_ranked` is collected (`routes_session.py:48`) then never used to scaffold the journey.
4. **`autoNarrate` is a binary client-side footgun** — no backend rate limiting; controlled by localStorage.
5. **No defined terminus** — the journey has no "done" state, so AI re-fires indefinitely.
6. **Theme saturation is invisible to the user** — drives backend behaviour but is never surfaced.

Backend is Python 3.12 + FastAPI + SQLAlchemy. Frontend is Phase 5 — not started. Phases 1–6 are backend-only; Phase 7 introduces the new state machine; Phase 8 is the frontend GUI.

---

## Phase 1 — Tighten AI verbosity

**Goal:** cut narrative lengths roughly in half across the board. No behavioural change.

**Files touched:** `backend/helix/ai/prompts.py`

**Changes:**

1. Rewrite the WORD BUDGET lines in `TASK_TEMPLATES`:

| Task | Current | New |
|---|---|---|
| `INTER_INSTRUMENT` | 50–100 total | **40–70 total** |
| `MISSION_CONTROL` | 30–60 per field | **20–35 per field** (60–105 total) |
| `PLANET_SUMMARY` | 100–200 per field | **60–90 per field** (120–180 total) |
| `FULL_FORMULATION` RICH | 150–250 per theme | **90–140 per theme** |
| `FULL_FORMULATION` PARTIAL | 80–120 per theme | **50–75 per theme** |
| `FULL_FORMULATION` SPARSE | refusal string | unchanged |
| `RED_THREAD` | (none) | **40–60 per field** |

2. Add a hard-rule line to every template:
   > `STRICT WORD LIMIT: Each field has a maximum word count. Exceeding it produces an invalid response.`

3. Add a global post-processing truncation as a safety net in `backend/helix/ai/formulation.py`. New helper:

```python
def _enforce_word_limit(text: str | None, max_words: int) -> str | None:
    if text is None:
        return None
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "…"
```

Apply in each `generate_*` method *after* the LLM returns, *before* returning the schema object. Per-field max words:

- `InterInstrumentNarration`: convergent 30, divergent 30, composite 25.
- `MissionControlSuggestion`: each of 3 narrative fields 40.
- `PlanetSummary`: each field 100.
- `FullFormulation`: each theme 150; `safety_paragraph` 60; `so_what_layer` 80.
- `RedThreadIntegration`: each field 70.

Truncation must **not** be applied to SPARSE refusal strings — check for the exact `SPARSE_REFUSAL_TEXT` before truncating.

**Tests:** in `backend/helix/tests/test_formulation_engine.py`

- `test_enforce_word_limit_truncates_long_text` — string > limit gets clipped, ends with `…`.
- `test_enforce_word_limit_passes_short_text` — string ≤ limit returns unchanged.
- `test_enforce_word_limit_preserves_sparse_refusal` — exact refusal string never truncated.
- For each `generate_*` method: feed a mock LLM response with each field at 2× its limit, assert returned object has every field within limit.

**Acceptance:** all existing tests still pass. New tests pass. Manual sanity: a Full Formulation with all RICH themes produces output ≤ ~750 words total.

---

## Phase 2 — Replace `delta >= 3` with theme-saturation triggers

**Goal:** move milestone gating server-side and tie it to meaningful state changes (a new theme reaching PARTIAL or RICH), not raw instrument count.

**Files touched:**

- `backend/helix/ai/readiness.py` — already has `_compute_theme_states`; reuse.
- `backend/helix/api/routes_assessment.py` — emit a milestone signal in the submit response.
- New: `helix/models/models.py` field `Session.theme_states_snapshot: JSON | None`.

**Schema migration:** add `theme_states_snapshot` JSON column to `sessions` table. Default `None`. Store the most recent theme state dict for change detection across requests.

**Changes:**

1. In `routes_assessment.py:200` (after Score persisted, before AI bridge block), compute the new theme states from all session scores. Compare against `session.theme_states_snapshot`. Define:

```python
def _theme_milestones(prev: dict | None, curr: dict) -> dict[str, list[str]]:
    """Return themes that newly entered PARTIAL or RICH this submit."""
    prev = prev or {}
    became_partial = [t for t, s in curr.items()
                      if s == "PARTIAL" and prev.get(t) == "SPARSE"]
    became_rich = [t for t, s in curr.items()
                   if s == "RICH" and prev.get(t) in (None, "SPARSE", "PARTIAL")]
    return {"became_partial": became_partial, "became_rich": became_rich}
```

2. After computing milestones, persist `session.theme_states_snapshot = curr`.

3. Add a `milestones` field to `SubmitResponse`:

```python
class MilestonesOut(BaseModel):
    became_partial: list[str]
    became_rich: list[str]
    full_formulation_unlocked: bool   # any became_partial AND ≥ 2 non-sparse themes
    red_thread_unlocked: bool         # any became_rich AND ≥ 3 non-sparse themes
```

4. The frontend will read `milestones` and enqueue Red Thread / Full Formulation only when the relevant flag is true. **Do not fire them from the backend submit handler** — keep submit fast.

5. **Remove the `delta >= 3` logic from the frontend spec** in `Documents/helix-implementation-state-7.md` and update with the new milestone contract. (If the frontend doesn't exist yet, just update the doc.)

**Tests:** in `backend/helix/tests/test_routing.py` or new `test_milestones.py`:

- `test_first_partial_theme_signals_full_formulation_unlock`
- `test_first_rich_theme_signals_red_thread_unlock`
- `test_no_signal_when_theme_state_unchanged`
- `test_signal_only_fires_on_first_transition` (going SPARSE→PARTIAL→RICH→PARTIAL must not re-fire `became_partial`)
- `test_milestones_persisted_across_submits` (verify `theme_states_snapshot` is written)

**Acceptance:** `delta >= 3` logic is removed from the design doc. Backend emits `milestones` on every submit. Existing tests still pass.

---

## Phase 3 — Backend rate-limiting for Mission Control

**Goal:** make `autoNarrate` toggle irrelevant to cost. Mission Control may only generate once per N seconds per session, regardless of client polling.

**Files touched:** `backend/helix/ai/orchestrator.py`

**Changes:**

1. Add constant `MISSION_CONTROL_DEBOUNCE_SECONDS = 60` at module top.

2. In `NarrativeOrchestrator.generate`, *before* the LLM call (after cache miss decision), if `task_type == MISSION_CONTROL and not force_regenerate`:
   - Query the most recent `Narrative` row of `task_type=mission_control` for this session.
   - If `created_at` is within the debounce window, return it as `cached=True` even if the context hash differs.

3. Document the behaviour: rate-limiting *only* applies to Mission Control. Other task types remain context-hash-driven.

**Tests:** in `backend/helix/tests/test_orchestrator.py`:

- `test_mission_control_debounced_within_window` — two calls < 60s apart → second returns cached row.
- `test_mission_control_regenerates_after_debounce` — second call > 60s later → fresh.
- `test_mission_control_force_regenerate_bypasses_debounce` — `force_regenerate=True` always generates.
- `test_debounce_does_not_apply_to_other_tasks` — Full Formulation still cache-hashes normally.

**Acceptance:** backend caps Mission Control LLM cost at 1 call/minute/session. Manual: hit dashboard 5× in 30s → first generates, next four return cached.

---

## Phase 4 — `PlanetState` + intake-ranked recommendations

**Goal:** the session response tells the client which planet to suggest next, computed from intake ranking + scored coverage. Pure backend, no LLM.

**Files touched:**

- New: `backend/helix/scoring/planet_progress.py`
- `backend/helix/api/routes_session.py` — surface in `SessionStateResponse`.

**Changes:**

1. Define the per-planet state enum:

```python
# planet_progress.py
from enum import Enum

class PlanetState(str, Enum):
    LOCKED = "LOCKED"           # conditional, not unlocked
    RECOMMENDED = "RECOMMENDED" # intake-ranked, no scores yet
    AVAILABLE = "AVAILABLE"     # unranked, no scores yet
    IN_PROGRESS = "IN_PROGRESS" # ≥1 score, < quick_scan complete
    COMPLETE = "COMPLETE"       # all quick_scan instruments scored
    DEEP = "DEEP"               # any deep_dive instrument scored
```

2. Function:

```python
def compute_planet_progress(session, scores) -> list[dict]:
    """
    Returns per-planet records:
    {
      "planet_id": "venus",
      "state": "RECOMMENDED",
      "rank": 1,                 # null if not in top3_ranked
      "scored_count": 2,
      "quick_scan_total": 3,
      "deep_dive_total": 5,
      "theme_contributions": ["current_distress"],
      "next_suggested_instrument": "phq2"  # first unscored from quick_scan, null if none
    }
    """
```

   - `rank` comes from `session.intake_data["top3_ranked"]` mapped via `INTAKE_CATEGORIES` (`routes_session.py:31`) to planet IDs.
   - Multiple categories can map to the same planet — take the lowest (best) rank.
   - Uranus: LOCKED unless `neurodivergence` is in `categories` OR PHQ-9 item 9 triggered the clarification screen.
   - `next_suggested_instrument`: first item in `quick_scan` array that isn't scored. Null when all quick_scan complete.

3. Add `planet_progress: list[dict]` to `SessionStateResponse` (`routes_session.py:94`). Populate via the existing `_build_session_state_response`.

**Tests:** new `backend/helix/tests/test_planet_progress.py`:

- `test_top_ranked_planet_marked_recommended_with_no_scores`
- `test_planet_with_partial_scoring_marked_in_progress`
- `test_planet_with_all_quick_scan_done_marked_complete`
- `test_planet_with_deep_dive_score_marked_deep`
- `test_uranus_locked_without_neurodivergence_category`
- `test_uranus_unlocked_with_neurodivergence_category`
- `test_uranus_unlocked_by_phq9_item9_safety_flag`
- `test_next_suggested_instrument_is_first_unscored_quick_scan`
- `test_next_suggested_instrument_null_when_quick_scan_complete`
- `test_multiple_categories_collapse_to_planet_with_best_rank`

**Acceptance:** `/sessions/{id}` returns a `planet_progress` array. `intake.top3_ranked = ["mood_anxiety", ...]` produces `venus.state == "RECOMMENDED"`.

---

## Phase 5 — Safety acknowledgment correctness + red_thread_quality gating

**Goal:** close two correctness gaps.

**Files touched:**

- `backend/helix/api/routes_session.py` — `acknowledge_safety`.
- `backend/helix/ai/readiness.py` — `_check_red_thread`.

**Changes:**

1. **Safety narrative cleanup.** In `acknowledge_safety` (`routes_session.py:336`):
   - After clearing `safety_flags` and transitioning to `EXPLORING`, mark all Mission Control narratives for this session where `output_json.safety_triggered == true` as superseded. Simplest approach: delete those rows. They have no value once safety has been acknowledged, and the next dashboard visit will regenerate a normal Mission Control.
   - **Do not** delete `planet_summary` / `full_formulation` rows — those weren't safety-overridden.

2. **`red_thread_quality` gate.** Extend `_check_red_thread` (`readiness.py:244`):
   - Read `intake_data.red_thread_quality`. If value is `"empty"` or `"low"` (define both), reject with reason `"Guiding question is too vague to support longitudinal synthesis."`
   - Quality is currently set by the intake submission but never validated. Add validation: in `submit_intake`, compute a quality score:
     - `< 8 words` → `"low"`
     - `< 4 words` or contains only filler → `"empty"`
     - else → `"present"`
   - Store as `intake_data.red_thread_quality`. (Already in the context payload, so no schema migration needed.)

**Tests:**

- `test_acknowledge_safety_deletes_safety_triggered_mission_control_narratives` — pre-seed two narratives (one safety-triggered, one not). Acknowledge. Confirm only safety-triggered one is gone.
- `test_acknowledge_safety_preserves_non_mission_control_narratives` — planet_summary row survives.
- `test_red_thread_blocks_on_low_quality_question`
- `test_red_thread_allows_present_quality_question`
- `test_intake_assigns_quality_low_for_short_question`
- `test_intake_assigns_quality_empty_for_filler`
- `test_intake_assigns_quality_present_for_full_question`

**Acceptance:** ack-safety wipes stale safety narratives. Red Thread refuses to synthesise around "idk" or "depression".

---

## Phase 6 — Report-ready terminus

**Goal:** define an explicit "done" condition. The session reaches it; spontaneous Full Formulation firing stops; the user can generate a report.

**Files touched:**

- `backend/helix/models/models.py` — add `Session.report_ready_at: datetime | None`.
- `backend/helix/api/routes_session.py` — compute and surface.
- `backend/helix/ai/readiness.py` — gate Full Formulation auto-firing.

**Schema migration:** add `report_ready_at` timestamp column to `sessions`. Nullable.

**Changes:**

1. Define "report-ready" in `planet_progress.py` (new function):

```python
def is_report_ready(theme_states: dict, planet_progress: list[dict]) -> bool:
    rich_count = sum(1 for s in theme_states.values() if s == "RICH")
    non_locked_planets = sum(
        1 for p in planet_progress if p["state"] not in ("LOCKED",)
    )
    progressed_planets = sum(
        1 for p in planet_progress
        if p["state"] in ("IN_PROGRESS", "COMPLETE", "DEEP")
    )
    return rich_count >= 3 and progressed_planets >= 4
```

2. In `routes_assessment.py` submit handler, after recomputing theme states, also recompute report-ready. If newly true and `session.report_ready_at is None`, set `report_ready_at = now()`.

3. Add `report_ready: bool` and `report_ready_at: str | None` to `SessionStateResponse`.

4. Add a new readiness reason: when `report_ready` is true AND the user did not manually trigger, `_check_full_formulation` returns `ready=False, reason="Session has reached report-ready state; further auto-formulation suppressed. Use force_regenerate to override."` This stops spontaneous re-firing. Manual button-press in the UI uses `force_regenerate=True`.

**Tests:**

- `test_is_report_ready_requires_three_rich_themes`
- `test_is_report_ready_requires_four_progressed_planets`
- `test_report_ready_at_set_on_first_eligibility`
- `test_report_ready_at_not_overwritten_on_subsequent_submits`
- `test_full_formulation_auto_blocks_after_report_ready`
- `test_full_formulation_manual_allowed_after_report_ready` (`force_regenerate=True`)

**Acceptance:** session response carries `report_ready` boolean. Once true, dashboard auto-firing stops. Manual button still works.

---

## Phase 7 — Three-mode navigation state

**Goal:** replace flat `EXPLORING` with a navigation mode that constrains/guides planet access. Backend tracks; frontend uses for UI gating.

**Files touched:**

- `backend/helix/models/models.py` — `Session.navigation_mode: str`.
- `backend/helix/api/routes_session.py` — new endpoint to switch mode.
- `backend/helix/routing/engine.py` — `compute_available_instruments` honours mode.

**Schema migration:** add `navigation_mode` text column, default `"GUIDED"`, NOT NULL.

**Changes:**

1. Define modes (constants in `routing/engine.py`):
   - `GUIDED` — default after core flow. Available instruments restricted to the top-ranked planet's quick_scan, in order.
   - `EXPLORER` — current behaviour. All planets, all instruments available.
   - `FOCUSED` — top-ranked planet's deep_dive available; other planets' quick_scan also available. Used after one planet's quick_scan completes.

2. In `compute_available_instruments`, branch on `session.navigation_mode`:
   - `GUIDED`: return only unscored instruments from the **single highest-ranked** planet's quick_scan list.
   - `FOCUSED`: union of (highest-ranked planet's deep_dive) + (other planets' quick_scan).
   - `EXPLORER`: current behaviour (unchanged).

3. Auto-promotion rules (applied in `routes_assessment.py` after score persist):
   - `GUIDED` → `FOCUSED` when the top-ranked planet's quick_scan is fully scored.
   - `FOCUSED` stays unless user explicitly switches.
   - Never auto-demote.

4. New endpoint `POST /sessions/{id}/navigation-mode`:
   ```python
   class NavigationModeRequest(BaseModel):
       mode: Literal["GUIDED", "EXPLORER", "FOCUSED"]
   ```
   Update + return full session state. User can always opt out to `EXPLORER`.

5. Add `navigation_mode: str` to `SessionStateResponse`.

**Tests:**

- `test_guided_mode_restricts_to_top_ranked_planet_quick_scan`
- `test_guided_mode_auto_promotes_to_focused_when_quick_scan_done`
- `test_focused_mode_exposes_deep_dive_and_other_quick_scans`
- `test_explorer_mode_exposes_everything`
- `test_user_can_switch_to_explorer_at_any_time`
- `test_navigation_mode_endpoint_rejects_invalid_mode`
- `test_session_starts_in_guided_after_core_flow` (sessions created via standard route).

**Acceptance:** in GUIDED, `/sessions/{id}` shows only top-ranked planet's quick_scan in `available`. After scoring all of them, mode auto-flips to FOCUSED and exposes deep_dive + other planets' quick_scans.

---

## Phase 8 — Solar system GUI (Phase 5 frontend kickoff)

**Goal:** spatial visualisation of session state. This is the user-facing payoff of phases 4 + 6 + 7.

**Stack:** as set in `CLAUDE.md` — Next.js + Tailwind. For the solar system rendering use `react-three-fiber` (Three.js wrapper). No new state libraries — keep session state in a single context provider fetching `/sessions/{id}`.

**Files created:** entire `frontend/` directory; treat this phase as a separate scoped implementation task. Below is the contract only — implementation detail is the frontend agent's job.

**Visual contract:**

| Planet attribute | Visual mapping |
|---|---|
| `state: LOCKED` | dim grey sphere, faint orbit, click shows lock reason |
| `state: RECOMMENDED` | pulsing gold ring around sphere |
| `state: AVAILABLE` | normal sphere, dim ring |
| `state: IN_PROGRESS` | partial luminosity ring (= scored_count / quick_scan_total) |
| `state: COMPLETE` | full bright sphere |
| `state: DEEP` | full sphere + secondary outer glow |
| `theme_contributions` | colour tint per theme (5 themes = 5 hues) |
| `rank == 1` | central position; remaining planets orbit at intake-ranked distance |

**State-driven UI gates:**

- `navigation_mode == "GUIDED"`: only the highest-ranked planet is clickable. Others show a "Coming next" tooltip.
- `report_ready == true`: a "Generate Report" CTA appears in mission control panel.
- `milestones.full_formulation_unlocked`: trigger Full Formulation request on next dashboard load.
- `milestones.red_thread_unlocked`: trigger Red Thread request.

**Critical: do not duplicate state derivation in the frontend.** The backend tells the frontend what's available, what's locked, what's recommended. Frontend renders, doesn't decide.

**Acceptance:** user enters dashboard post-core-flow → sees solar system → top-ranked planet pulses → clicking other planets shows locked state → on completion, system promotes to FOCUSED and unlocks more planets visually.

---

## Cross-cutting requirements

### Test coverage
Run `pytest backend/helix/tests/ -q` before every commit. No phase ships with failing tests.

### Database migrations
Phases 2, 6, 7 add columns. Use the existing migration pattern in `backend/helix/db/`. Each migration in its own commit.

### Backwards compatibility
Per `CLAUDE.md`: no shims. The `delta >= 3` logic is removed entirely. The old `EXPLORING` state is renamed/extended — sessions in the old state get `navigation_mode = "EXPLORER"` (least restrictive) as a one-shot upgrade in the migration.

### Verbosity guardrails
Phase 1's `_enforce_word_limit` is a safety net, not a substitute for prompt tuning. If a model regularly hits the truncation, the prompt budget is wrong — re-tighten the prompt rather than relying on truncation.

### Out of scope
- Don't redesign the scorer layer.
- Don't change instrument JSON definitions.
- Don't add new instruments.
- Don't introduce a frontend state management library before Phase 8 actually starts.

---

## Suggested commit ordering

```
feat(ai): tighten word budgets and add truncation safety net      # Phase 1
feat(milestones): replace delta>=3 with theme-saturation signals  # Phase 2
feat(ai): debounce mission_control to 60s per session             # Phase 3
feat(planets): compute and surface PlanetState + recommendations  # Phase 4
fix(safety): wipe stale safety narratives on acknowledge          # Phase 5a
feat(red-thread): gate on red_thread_quality                      # Phase 5b
feat(session): add report_ready terminus                          # Phase 6
feat(navigation): introduce GUIDED/FOCUSED/EXPLORER modes         # Phase 7
feat(frontend): solar system dashboard (initial)                  # Phase 8
```

Each commit lands its own tests. No phase depends on the next.
