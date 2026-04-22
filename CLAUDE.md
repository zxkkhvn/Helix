# Helix — Agent Context

> Project-specific rules only. Global defaults live in `~/.claude/CLAUDE.md`.

## Identity

Psychological self-exploration platform using validated psychometric instruments.
Process-Based Therapy (PBT) framework. Solar system metaphor for UX.
Python FastAPI backend + Next.js frontend monorepo.

## Tech Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy, Pydantic v2, numpy
- **Scoring:** Deterministic Python only. AI excluded from all score computation.
- **Database:** SQLite v1 (Postgres migration path). UUIDs as PKs, JSON columns.
- **Frontend:** Next.js (React) + Tailwind CSS (Phase 5 — not started)
- **AI pipeline:** LLM wrapper (Ollama local / Anthropic+OpenAI cloud). Narrative only.
- **Cognitive tasks:** jsPsych (Phase 6 — not started)
- **Reports:** WeasyPrint + pandas (scoped to `reports/` only)
- **Dependency mgmt:** uv, `pyproject.toml`

## Dev Commands

```bash
source .venv/bin/activate       # activate venv
pytest backend/helix/tests/ -q  # run all tests
uvicorn helix.main:app --reload # start API server (from backend/)
```

## File Map

```text
backend/
└── helix/
    ├── main.py                    # FastAPI app entry
    ├── config.py                  # Settings, env vars, model config
    ├── models/                    # SQLAlchemy ORM models
    ├── scoring/
    │   ├── base.py                # BaseScorer, ScoreResult
    │   ├── registry.py            # Scorer registry
    │   ├── generic.py             # GenericScorer (loads JSON defs)
    │   ├── composite.py           # Composite index engine (mean_z)
    │   ├── planet_state.py        # Planet state calculator
    │   └── instruments/
    │       ├── definitions/       # JSON instrument definitions (48 total)
    │       ├── paq.py             # Custom: 5 subscales, valence-specific
    │       ├── vlq.py             # Custom: gap scoring
    │       ├── mss_ysq.py         # Custom: 19 schemas, 6 clusters
    │       ├── lsas_sr.py         # Custom: paired fear+avoidance
    │       ├── ecr_rs.py          # Custom: multi-target (4 relationships)
    │       ├── meq.py             # Custom: chronotype classification
    │       ├── psqi.py            # Custom: 7-component derivation
    │       └── pbat.py            # Custom: formative, item-profile
    ├── routing/                   # Deterministic routing engine
    ├── ai/                        # Prompt builder, LLM client, formulation
    ├── api/                       # FastAPI route modules
    ├── db/                        # Database abstraction + migrations
    ├── reports/                   # PDF/JSON export (pandas allowed here only)
    └── tests/
        ├── conftest.py            # Shared fixtures: load_definition(), score(), mock responses
        ├── test_scoring.py        # GenericScorer + custom scorer tests
        ├── test_definitions.py    # JSON schema validation for all definitions
        ├── test_routing.py        # Expansion triggers, carry-forward, safety flags
        ├── test_composite.py      # Composite index computation
        └── test_api.py            # FastAPI endpoint integration tests
frontend/                          # Next.js — Phase 5, not started
Documents/                         # Implementation state doc (versioned)
Test Battery/                      # PDF source instruments (git-ignored)
```

## Testing

**Test-driven development is mandatory.** Write tests before or alongside implementation — never after.

```bash
pytest backend/helix/tests/ -q            # all tests
pytest backend/helix/tests/ -q -x         # stop on first failure
pytest backend/helix/tests/ -k "phq9"     # single instrument
```

### Test categories

| Category | File | What it covers |
|---|---|---|
| Definition validation | `test_definitions.py` | Every JSON def loads, conforms to schema, items match response_option_sets, score ranges are consistent |
| Scoring correctness | `test_scoring.py` | Known test vectors per instrument. Min/max/mid/edge scores. Band assignment. Subscale computation. |
| Routing logic | `test_routing.py` | Expansion triggers fire at correct thresholds. Carry-forward maps correct items. Safety flags trigger SAFETY_PROTOCOL. |
| Composite indices | `test_composite.py` | mean_z computation. required_core enforcement. Partial composite labelling. Sign inversions. |
| API integration | `test_api.py` | Submit responses → get scores. Session management. Safety pause flow. |

### Test rules

- **Every scorer (generic or custom) must have test vectors.** Minimum: all-min, all-max, midpoint, threshold boundaries (e.g. PHQ-2 score=2 vs score=3).
- **Safety flag tests are mandatory.** PHQ-9 item 9 at every value (0, 1, 2, 3). PC-PTSD-5 at threshold.
- **Carry-forward tests must verify item mapping.** Submit PHQ-2, expand to PHQ-9, confirm items 1-2 are pre-filled and score includes them.
- **Never mock the scorer in scoring tests.** Test the real computation path. Mocking is for API/DB layers only.
- **Run `pytest -q` before every commit.** No broken tests in main.

## Architecture Rules

- **Scoring is deterministic.** AI never computes scores, never diagnoses.
- **Instrument definitions are declarative JSON.** GenericScorer handles ~40 instruments. 8 custom scorers for non-trivial logic.
- **Carry-forward pattern:** PHQ-2 → PHQ-9, GAD-2 → GAD-7, PAQ-S → PAQ. Parent responses map to child items via `carry_forward_items` in JSON def. User sees only new items.
- **Safety protocol is non-negotiable.** PHQ-9 item 9 > 0 or PC-PTSD-5 >= 3: immediate pause, crisis resources, no bypass. Exception: if Uranus (Neurodivergence) is activated, item 9 shows a clarification screen (urgent vs passive/philosophical) per Section 37.1.
- **Composite indices are platform-derived.** Always labelled "n of N components". Never treated as validated clinical measures. Mean of z-scores, not sum.
- **Planet states are computed projections**, not stored tables. Memoised on Session, invalidated on every score submission.
- **No pandas in scoring path.** pandas scoped to `reports/` only.
- **Item text on validated instruments: verbatim, never changed.**

## Instrument JSON Contract

Every definition in `scoring/instruments/definitions/` conforms to the schema in the implementation state doc (Section 5). Key fields: `instrument_id`, `items[]` with `response_options_key` referencing `response_option_sets`, `scoring.method` (`sum`/`mean`/`custom`), `routing.carry_forward_items`, `composite_contributions[]`.

## Current Build Status

Phase 1 in progress. Venus vertical slice definitions complete (PHQ-2, PHQ-9, GAD-2, GAD-7, PAQ-S, PAQ). Scoring engine, routing engine, API, database, frontend: not started.

## Key References

- **Implementation state:** `Documents/helix-implementation-state-7.md` (2100-line spec, Sections 1–37)
- **Battery:** 48 instruments, 8 planets, frozen. See Section 31.5.
- **8 custom scorers:** PBAT, VLQ, MSS-YSQ, PAQ, LSAS-SR, ECR-RS, MEQ, PSQI
- **Section 37:** AASPIRE/REALS research integration — PHQ-9 item 9 ND non-invariance, accessible presentation mode, v2 candidates (AASPIRE Burnout, REALS scales)

## LEARNINGS.md

Read `LEARNINGS.md` before touching scoring logic or instrument definitions.
