# HELIX — Implementation State Document

**Version:** 2.0  
**Date:** April 2026  
**Status:** Pre-implementation (planning complete, adversarial review resolved, no code written)

---

## 1. Locked Decisions

These decisions are finalised across planning. They are not open for re-evaluation unless a hard technical blocker is discovered.

### 1.1 Architecture Principles

| Decision | Detail | Rationale |
|---|---|---|
| Scoring engine | Deterministic Python only. AI excluded from all calculation. | Auditability, reproducibility, zero hallucination risk on clinical data. |
| AI role boundary | Chat + narrative synthesis only. Receives pre-scored JSON. Never computes scores, never diagnoses. | Hard separation prevents scope creep into clinical territory. |
| Instrument definitions | Declarative JSON per instrument. Generic scorer loads definition and applies standard algorithm. Custom subclass only for non-trivial logic (VLQ, CAT-Q). | Adding instruments = writing JSON, not Python. Scales cleanly. |
| Routing engine | Backend-owned, deterministic, rule-based. AI has zero gating authority. | AI cannot skip safety flags, override expansions, or change instrument order. |
| Item delivery (v1) | Form per instrument. AI narrates between instruments (mission control framing). | Preserves psychometric integrity. Conversational delivery is v2. |
| Item text | Validated wording presented verbatim always. AI may frame context around items but never rephrase. | Changing validated wording invalidates psychometric properties. |
| Carry-forward pattern | PHQ-2 responses become items 1–2 of PHQ-9. User sees only items 3–9 after expansion. Linked via `parent_instance_id`. | Reduces respondent burden, maintains data continuity. |
| PlanetStates | Computed projection from session/assessment data, not a stored table. Memoised via `planet_states_cache` on Session. Cache invalidated on every new score submission and on composite definition updates. Computation remains the source of truth. | Always consistent with source data. No sync maintenance. |
| Cultural policy | No ethnicity-based score corrections. Visible validity labels per instrument. Caveat text when high-risk instrument used by non-Western user. | Honest, transparent, avoids pseudo-scientific adjustments. |
| Safety protocol | PHQ-9 item 9 > 0 or PC-PTSD-5 ≥ 3: immediate pause, crisis resources, no resume until acknowledged. | Non-negotiable safety floor. |

### 1.2 Technical Stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend | Next.js (React) + Tailwind CSS | Thin client. Zero business logic. Rendering + chat UI + solar system canvas only. |
| Solar system renderer | Decision deferred | D3.js baseline. Will prototype alternatives (PixiJS, SVG + Framer Motion) before committing. |
| Backend | Python FastAPI | All business logic: scoring, routing, AI orchestration, report generation. |
| Scoring engine | Pure Python (stdlib) | numpy deferred to composite engine only. No pandas in scoring path. Strict JSON in / JSON out. |
| Reports / export | Python + pandas + WeasyPrint | pandas scoped to `reports/` only. WeasyPrint for PDF v1. |
| Database (v1) | SQLite | UUIDs as PKs, JSON columns for flexible payloads. Designed for Postgres migration. |
| Database (scale) | PostgreSQL | Migration path, not v1. |
| AI pipeline | LLM wrapper with structured prompt builder | Local (Ollama) for dev, cloud fallback (Anthropic/OpenAI). Model swappable via config. |
| Cognitive tasks | jsPsych (MIT) | Standalone web pages. Results posted to FastAPI scoring endpoint. |
| Auth (v1) | Google OAuth via NextAuth.js / Auth.js | FastAPI validates token. Low-friction, verified identity. |
| Dependency mgmt | uv | `pyproject.toml` + `uv.lock`. |
| IDE | Google Antigravity | Cloud-based development environment. |
| VCS | GitHub | Monorepo: `backend/` + `frontend/`. |

### 1.3 Consistency Checks (v1 Scope)

| Check | v1 Status | Method |
|---|---|---|
| Longstring detection | INCLUDED | Flag if 8+ identical consecutive responses. |
| Rapid-response flagging | INCLUDED | Timestamp-based. Flag if response time below threshold. |
| Semantic consistency pairs | DEFERRED to v2 | Requires careful item placement design across instruments. |
| Infrequency items | DEFERRED to v2 | Requires embedded items with predictable responses. |

---

## 2. Current Build Status

Phase 2 Venus vertical slice complete. 169 tests passing. API is runnable with `uvicorn helix.main:app --reload` from `backend/`.

| Component | Status |
|---|---|
| Scoring engine — BaseScorer + ScoreResult | COMPLETE — `scoring/base.py`. Longstring detection, rapid-response flagging, band assignment, restrictive safety condition parser (no eval). |
| Scoring engine — GenericScorer | COMPLETE — `scoring/generic.py`. Handles sum/mean instruments. Carry-forward merge. Reverse scoring and subscale computation support. |
| Scoring engine — Scorer registry | COMPLETE — `scoring/registry.py`. Auto-discovers definitions on startup. Routes custom instruments to their module via `create_scorer()` factory. |
| Scoring engine — PAQ custom scorer | COMPLETE — `scoring/instruments/paq.py`. 5 subscales (N_DIF, P_DIF, N_DDF, P_DDF, G_EOT), total = sum of subscales. |
| Scoring engine — composite engine | COMPLETE — `scoring/composite.py`. mean_z computation with norms. |
| All instrument scorers (48 instruments) | IN PROGRESS — Venus 9 generic + 1 custom complete. Core Flow 2 generic + 1 custom complete. Mercury 4 generic + 2 custom complete. Earth 7 generic complete. Mars 4 generic complete. Jupiter 4 generic + 1 custom (VLQ) complete. Remaining 13 not started. |
| Instrument JSON definitions | IN PROGRESS — Venus (10/10), Mercury (6/6), Earth (7/7), Mars (4/4), Jupiter (5/5), Core Flow (3/3) complete. Remaining: Saturn (5), Neptune (7), Uranus (3), Core Flow PCL-5 = 16 not started. |
| Routing engine | COMPLETE — `routing/engine.py`. Evaluates `on_completion` rules from JSON definitions. `evaluate_routing()` + `compute_available_instruments()`. PHQ-2→PHQ-9, GAD-2→GAD-7, PAQ-S→PAQ, ASRS-A→ASRS-Full, PHQ-9 flag_elevated, safety_pause. `unlock_planet` action for cross-planet triggers (ASRS→Uranus). |
| Database schema | COMPLETE — `models/models.py`. Session, AssessmentInstance (with parent_instance_id), Score. UUID PKs, JSON columns, designed for Postgres migration. SQLite v1 via `db/database.py`. |
| FastAPI application | COMPLETE — `main.py`. Lifespan handler bootstraps DB + scorer registry. CORS configured for dev. |
| Assessment submission API | COMPLETE — `POST /sessions/{id}/assessments/{instrument_id}/submit`. Server-side carry-forward. Scores, persists, routes, handles safety in one endpoint. |
| Session management API | COMPLETE — `POST /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/acknowledge-safety`. Enforces CORE_FLOW_IN_PROGRESS state before EXPLORING. |
| Safety protocol | COMPLETE — PHQ-9 item 9 > 0 or PC-PTSD-5 ≥ 3 → SAFETY_PAUSED state. 409 on all further submissions. Structured safety flag. |
| Test suite | IN PROGRESS — 169/169 passing. Definition + scoring + routing + API integration. (Tests for new Core/Mercury items pending). |
| Planet state calculator | NOT STARTED — designed, not coded |
| Intake flow | COMPLETE — `POST /sessions/{id}/intake` and `POST /sessions/{id}/anchors`. Captures presenting concerns and session anchors. |
| AI pipeline (prompt builder, LLM wrapper) | NOT STARTED |
| Formulation narrative engine | NOT STARTED |
| Report engine (PDF/JSON export) | NOT STARTED |
| Next.js frontend | NOT STARTED |
| Solar system renderer | NOT STARTED |
| Chat interface (mission control) | NOT STARTED |
| jsPsych cognitive tasks (Layer 5) | NOT STARTED |
| Google OAuth integration | NOT STARTED |

---

## 3. Repository Structure

Monorepo layout. Backend-first development sequence. Files marked ✓ exist; unmarked are planned.

```
helix/
├── backend/
│   ├── pyproject.toml                       ✓ FastAPI, SQLAlchemy, Pydantic v2, uvicorn, httpx
│   └── helix/
│       ├── __init__.py                      ✓
│       ├── main.py                          ✓ FastAPI app entry, lifespan handler
│       ├── config.py                          Settings, env vars, model config
│       ├── models/
│       │   ├── __init__.py                  ✓
│       │   └── models.py                    ✓ Session, AssessmentInstance, Score (SQLAlchemy ORM)
│       ├── scoring/
│       │   ├── __init__.py                  ✓
│       │   ├── base.py                      ✓ BaseScorer, ScoreResult, condition parser
│       │   ├── registry.py                  ✓ Scorer registry, auto-discovery
│       │   ├── generic.py                   ✓ GenericScorer (sum/mean)
│       │   ├── composite.py                   Composite index engine (mean_z)
│       │   ├── planet_state.py                Planet state calculator
│       │   └── instruments/
│       │       ├── __init__.py              ✓ Exposes _DEFINITIONS_DIR
│       │       ├── definitions/
│       │       │   ├── phq2.json            ✓
│       │       │   ├── phq9.json            ✓
│       │       │   ├── gad2.json            ✓
│       │       │   ├── gad7.json            ✓
│       │       │   ├── paq_s.json           ✓
│       │       │   ├── paq.json             ✓
│       │       │   ├── pbat.json            ✓
│       │       │   ├── wsas.json            ✓
│       │       │   ├── pcptsd5.json         ✓
│       │       │   ├── isi.json             ✓
│       │       │   ├── wemwbs.json          ✓
│       │       │   ├── ffmq15.json          ✓
│       │       │   ├── composites.json        Versioned composite index definitions
│       │       │   └── ...                    Remaining 32 instrument definitions
│       │       ├── paq.py                   ✓ Custom: 5 subscales, valence-specific
│       │       ├── pbat.py                  ✓ Custom: formative, item-profile output
│       │       ├── vlq.py                     Custom: gap scoring
│       │       ├── mss_ysq.py                 Custom: 19 schemas, 6 clusters
│       │       ├── lsas_sr.py                 Custom: paired fear+avoidance ratings
│       │       ├── ecr_rs.py                  Custom: multi-target (4 relationships)
│       │       ├── meq.py                     Custom: chronotype classification
│       │       └── psqi.py                    Custom: 7-component derivation
│       ├── routing/
│       │   ├── __init__.py                  ✓
│       │   └── engine.py                    ✓ evaluate_routing, compute_available_instruments
│       ├── ai/
│       │   ├── prompt_builder.py              Structured prompt assembly
│       │   ├── formulation.py                 FormulationEngine class
│       │   └── llm_client.py                  Ollama / cloud abstraction
│       ├── api/
│       │   ├── __init__.py                  ✓
│       │   ├── routes_assessment.py         ✓ POST .../submit (server-side carry-forward)
│       │   ├── routes_session.py            ✓ POST/GET /sessions, acknowledge-safety
│       │   ├── routes_formulation.py          Formulation generation
│       │   ├── routes_auth.py                 Google OAuth validation
│       │   └── routes_debug.py                Debug-only endpoints (DEBUG_MODE=true)
│       ├── db/
│       │   ├── __init__.py                  ✓
│       │   ├── database.py                  ✓ SQLite engine, SessionLocal, get_db, create_tables
│       │   └── migrations/                    Alembic (deferred to Postgres migration)
│       ├── reports/
│       │   ├── pdf_generator.py               WeasyPrint + pandas
│       │   └── json_export.py                 JSON report export
│       └── tests/
│           ├── __init__.py                  ✓
│           ├── conftest.py                  ✓ Shared fixtures, score() helper, make_specific_responses()
│           ├── test_definitions.py          ✓ 16 JSON schema validation tests
│           ├── test_scoring.py              ✓ 78 scoring tests (Venus instruments)
│           ├── test_routing.py              ✓ 34 routing unit tests
│           ├── test_api.py                  ✓ 26 API integration tests
│           └── test_composite.py              Composite index tests
├── frontend/                                  Next.js — Phase 5, not started
├── Documents/
│   └── helix-implementation-state-7.md      ✓ This document
├── LEARNINGS.md                             ✓ Non-obvious decisions and gotchas
├── GEMINI.md                                ✓ Agent context
├── .gitignore                               ✓
└── README.md
```

---

## 4. Phased Build Plan

Backend-first. Each phase produces a testable, working vertical slice.

### Phase 1: Scoring Engine

**Goal:** Every instrument has a JSON definition and a working scorer. The generic scorer handles standard instruments; custom subclasses exist for non-trivial logic. Full test coverage.

| Task | Detail | Status |
|---|---|---|
| 1.0 Audit all instruments against JSON schema | Check which of the 48 instruments fit the generic scorer (sum/mean) vs need custom handling. ~40 generic, 8 custom. | **✓ DONE** |
| 1.1 Define JSON schema for instrument definitions | Contract: items, response_options, scoring_rules, subscales, thresholds, routing_triggers, cultural_validity, time_window. | **✓ DONE** — 16 schema validation tests passing. |
| 1.2 Build BaseScorer + ScoreResult | Abstract base class with longstring detection, rapid-response checking, band assignment, safety condition parser. ScoreResult dataclass. | **✓ DONE** — `scoring/base.py` |
| 1.3 Build GenericScorer class | Loads any conforming JSON definition. Applies sum/mean/subscale algorithms. Extends BaseScorer. Carry-forward merge. | **✓ DONE** — `scoring/generic.py` |
| 1.4 Build scorer registry | Dynamic instrument registration and lookup. Auto-discovers definitions from directory. | **✓ DONE** — `scoring/registry.py` |
| 1.5 Write JSON definitions — Mercury | ISI, WEMWBS, Brief MAIA-2, MEQ, PSQI, FFMQ-15. | **✓ DONE** |
| 1.6 Write JSON definitions — Venus | PHQ-2, PHQ-9, GAD-2, GAD-7, PAQ-S, PAQ, DERS-16, PSS-10, DTS, ERQ. | **✓ DONE** |
| 1.7 Write JSON definitions — Earth | BFI-S, IPIP-50, SCS-SF, BRS, RSES, ACEs, VIA-IS-P. | **✓ DONE** |
| 1.8 Write JSON definitions — Mars | ASRS Part A, ASRS Full, BDEFS-SF, CFQ-25. | **✓ DONE** |
| 1.9 Write JSON definitions — Jupiter | VLQ, AAQ-II, CompACT, MLQ, SWLS. | **✓ DONE** |
| 1.10 Write JSON definitions — Saturn | LSAS-SR (short + full), ECR-S, ECR-RS, De Jong Gierveld. | Not started |
| 1.11 Write JSON definitions — Neptune | IUS-12, MSS-YSQ, PTQ-10, CPQ, DSS-B, PSWQ, OCI-R. | Not started |
| 1.12 Write JSON definitions — Uranus | AQ-10, CAT-Q, RAADS-R. | Not started |
| 1.13 Write JSON definitions — Core Flow + Safety | PBAT, WSAS, PC-PTSD-5, PCL-5. Optional: AUDIT-C, DAST-10. | **IN PROGRESS** — PBAT, WSAS, PC-PTSD-5 complete. |
| 1.14 Build custom scorers | PAQ (5 subscales/valence-specific). Remaining 7: PBAT, VLQ, MSS-YSQ, LSAS-SR, ECR-RS, MEQ, PSQI. | **IN PROGRESS** — PAQ, PBAT, MEQ, PSQI, VLQ complete. Remaining: MSS-YSQ, LSAS-SR, ECR-RS. |
| 1.15 Build composite index engine | mean_z computation, required_core and required_minimum enforcement, partial composite labelling. Custom delegation for VLQ gap. | **✓ DONE** |
| 1.16 Build routing engine | Deterministic rule evaluation. Expansion triggers. Safety protocols. Deep dive unlock triggers. `unlock_planet` action. | **IN PROGRESS** — Venus + Mars + Jupiter slices complete. Core Flow sequence enforced. ASRS→Uranus unlock wired. |
| 1.17 Build planet state calculator | Derives planet opacity, moon unlocks, ring assignments from completion state. | Not started |
| 1.18 Full test suite | Every instrument scored against known test vectors. Edge cases for routing, carry-forward, safety. | **IN PROGRESS** — 195 passing tests |

### Phase 2: Data Layer + API Shell

**Goal:** SQLite database with complete schema. FastAPI app serving assessment endpoints. Sessions, responses, and scores persisting correctly.

| Task | Detail | Status |
|---|---|---|
| 2.1 Database schema design | Session, AssessmentInstance (with `parent_instance_id`), Score. UUIDs as PKs. JSON columns for flexible payloads. Designed for Postgres migration. | **✓ DONE** — `models/models.py` |
| 2.2 SQLAlchemy models + create_tables | ORM models matching schema. `create_tables()` via `Base.metadata.create_all()`. Alembic deferred to Postgres migration. | **✓ DONE** — `db/database.py` |
| 2.3 FastAPI app shell | Application factory, lifespan handler, CORS config, health check, dependency injection for DB sessions. | **✓ DONE** — `main.py` |
| 2.4 Assessment submission endpoint | `POST /sessions/{id}/assessments/{instrument_id}/submit` — accepts responses + optional parent_instance_id, computes carry-forward server-side, runs scorer, persists results, evaluates routing, returns score + routing action + session_state. | **✓ DONE** — `api/routes_assessment.py` |
| 2.5 Session management endpoints | `POST /sessions` (create), `GET /sessions/{id}` (state + completed + available). Available instruments computed from Score rows (not stored state). | **✓ DONE** — `api/routes_session.py` |
| 2.6 Intake flow endpoints | Captures presenting concerns, red-thread question, cultural background, state anchors, exclusion screen. | **✓ DONE** — Implemented `/intake` and `/anchors`. |
| 2.7 Safety protocol handler | PHQ-9 item 9 > 0 or PC-PTSD-5 ≥ 3 → SAFETY_PAUSED. 409 on all further submissions. Structured safety flags. `POST /sessions/{id}/acknowledge-safety` resumes EXPLORING. | **✓ DONE** |
| 2.8 Integration tests | Full flow: create session → submit PHQ-2 → expansion to PHQ-9 → carry-forward → score → safety pause → acknowledge → resume. | **✓ DONE** — `tests/test_api.py` |
| 2.9 Dev Shell | Vanilla HTML/JS thin client to drive session testing locally without Swagger. Includes `GET /sessions/{id}/instruments/{id}` session-aware render payload to enforce zero-logic frontend. | **✓ DONE** — `dev_shell.html` + `api/routes_session.py` |

### Phase 3: AI Pipeline

**Goal:** LLM abstraction layer working. Prompt builder assembling context from scored JSON. Formulation engine producing themed narratives. Mission control suggesting next destinations.

| Task | Detail | Depends On |
|---|---|---|
| 3.1 LLM client abstraction | `LLMClient` class with `generate()` method. Ollama adapter for local dev. Cloud adapter (Anthropic/OpenAI) for production. Config-switchable. | Nothing |
| 3.2 Prompt builder | Assembles system prompt (role + safety rules + epistemic constraints) + context block (current scores JSON, flags, red-thread question, cultural context) + task instruction. | 3.1 |
| 3.3 Formulation engine | `FormulationEngine.generate(session_scores)` → 5-theme narrative output. | 3.2, Phase 2 |
| 3.4 Mission control logic | Given current completion state + scores + routing rules, suggest next planet/instrument. Natural language framing. | 3.2, Phase 2 |
| 3.5 Inter-instrument narration | AI generates brief contextual bridging text between instruments. References red-thread question. | 3.2 |
| 3.6 Prompt quality testing | Test formulation output against known score profiles. Verify AI never computes, never diagnoses, always cites uncertainty. | 3.3–3.5 |

### Phase 4: Auth + Session Persistence

**Goal:** Google OAuth integrated. Users can log in, persist progress, and resume from where they left off.

| Task | Detail | Depends On |
|---|---|---|
| 4.1 NextAuth.js / Auth.js setup | Google OAuth provider. Session token in cookie. Refresh token handling. | Frontend shell |
| 4.2 FastAPI token validation | Middleware validates Google OAuth token on protected endpoints. Maps Google identity to User record. | 4.1, Phase 2 |
| 4.3 Session resume logic | On login, load latest incomplete session. Restore completion state, planet states, pending routing actions. | 4.2, Phase 2 |

### Phase 5: Frontend + Solar System UI

**Goal:** Working web application. Assessment forms render, AI narration displays between instruments, solar system visualises progress.

| Task | Detail | Depends On |
|---|---|---|
| 5.1 Next.js app shell | Routing, layout, Tailwind config. Pages: landing, assessment, solar system view, formulation report. | Nothing |
| 5.2 Assessment form renderer | Generic component that renders any instrument from its JSON definition. Handles Likert, VAS, yes/no, free text. Submits to FastAPI. | 5.1, Phase 1 |
| 5.3 Solar system renderer prototype | Evaluate D3.js vs PixiJS vs SVG + Framer Motion. Build planet display with opacity, moon, ring bindings. | 5.1 |
| 5.4 Chat / mission control UI | Chat panel displaying AI narration. Mission control suggestions as tappable cards. | 5.1, Phase 3 |
| 5.5 Formulation display | Themed narrative rendered as structured cards. Composite indices as rings. Cultural caveats inline. | 5.1, Phase 3 |
| 5.6 Report export | Trigger PDF generation. Download link. JSON export option. | 5.5, Phase 2 reports/ |

### Phase 6: Cognitive Tasks (Layer 5)

**Goal:** jsPsych cognitive tasks running as standalone pages. Results submitted to scoring endpoint.

| Task | Detail | Depends On |
|---|---|---|
| 6.1 jsPsych task shell | Standalone HTML pages with jsPsych. Shared config for styling, data submission. | Phase 2 |
| 6.2 Implement 7 cognitive tasks | Flanker, Stroop, N-back, Digit span, Symbol matching, Trail Making B, Tower planning. | 6.1 |
| 6.3 Cognitive scoring integration | FastAPI endpoint receives jsPsych JSON. Scores RT, accuracy, consistency. Feeds Executive Load composite. | 6.2, Phase 1 |

---

## 5. Instrument Definition JSON Schema

This is the contract that every instrument definition file must conform to. The GenericScorer loads this and applies the scoring algorithm.

```json
{
  "instrument_id": "phq9",
  "name": "Patient Health Questionnaire-9",
  "abbreviation": "PHQ-9",
  "version": "1.0",
  "layer": 1,
  "planet": "venus",
  "time_window": "past_2_weeks",
  "time_window_text": "Over the last 2 weeks, how often have you been bothered by the following?",
  "cultural_validity": "broadly_cross_cultural",
  "licence_status": "public_domain",

  "items": [
    {
      "item_id": "phq9_01",
      "text": "Little interest or pleasure in doing things",
      "response_options": [
        {"value": 0, "label": "Not at all"},
        {"value": 1, "label": "Several days"},
        {"value": 2, "label": "More than half the days"},
        {"value": 3, "label": "Nearly every day"}
      ],
      "safety_flag": false
    },
    {
      "item_id": "phq9_09",
      "text": "Thoughts that you would be better off dead, or of hurting yourself in some way",
      "response_options": ["...same as above..."],
      "safety_flag": true,
      "safety_trigger": {
        "condition": "value > 0",
        "action": "SAFETY_PROTOCOL"
      }
    }
  ],

  "scoring": {
    "method": "sum",
    "range": [0, 27],
    "bands": [
      {"min": 0, "max": 4, "label": "minimal"},
      {"min": 5, "max": 9, "label": "mild"},
      {"min": 10, "max": 14, "label": "moderate"},
      {"min": 15, "max": 19, "label": "moderately_severe"},
      {"min": 20, "max": 27, "label": "severe"}
    ],
    "subscales": null
  },

  "routing": {
    "parent_instrument": "phq2",
    "expansion_trigger": {
      "instrument": "phq2",
      "condition": "score >= 3"
    },
    "carry_forward_items": ["phq9_01", "phq9_02"],
    "on_completion": [
      {"condition": "score >= 10", "action": "flag_elevated"},
      {"condition": "item.phq9_09 > 0", "action": "SAFETY_PROTOCOL"}
    ]
  },

  "composite_contributions": ["distress_index"],
  "consistency_pairs": []
}
```

### Schema Fields Reference

| Field | Type | Description |
|---|---|---|
| `instrument_id` | string | Unique identifier, used as registry key. |
| `name` | string | Full instrument name. |
| `abbreviation` | string | Short display name. |
| `version` | string | Definition version (for tracking changes). |
| `layer` | int | Assessment layer (1-5). Retained for reference but superseded by planet + tier model. |
| `planet` | string | Solar system mapping (mercury, venus, earth, mars, jupiter, saturn, uranus, neptune, or null for cohesion/safety). |
| `tier` | enum | `quick_scan` or `deep_dive`. Determines when instrument becomes available. |
| `time_window` | string | Machine-readable time frame (e.g. `past_2_weeks`, `past_month`). |
| `time_window_text` | string | Human-readable prompt shown before items. |
| `cultural_validity` | enum | `broadly_cross_cultural` / `moderate_bias_risk` / `high_bias_risk` / `insufficient_evidence`. |
| `licence_status` | string | Current licensing status. |
| `items[]` | array | Ordered list of item objects. |
| `items[].item_id` | string | Unique item identifier. |
| `items[].text` | string | Validated item text, presented verbatim. |
| `items[].response_options[]` | array | Ordered value/label pairs. |
| `items[].safety_flag` | bool | Whether this item can trigger safety protocol. |
| `items[].safety_trigger` | object? | Condition and action if safety_flag is true. |
| `scoring.method` | enum | `sum` / `mean` / `custom`. Custom requires a dedicated scorer subclass. |
| `scoring.range` | [int, int] | Theoretical min/max for the total score. |
| `scoring.bands[]` | array | Interpretive severity bands with min/max/label. |
| `scoring.subscales` | object? | Subscale definitions (item groupings, scoring method per subscale). Null if none. |
| `routing.parent_instrument` | string? | If this instrument is an expansion of another. |
| `routing.expansion_trigger` | object? | Condition on parent that triggers this instrument. |
| `routing.carry_forward_items` | string[]? | Item IDs carried from parent (not re-asked). |
| `routing.on_completion` | array | Post-scoring routing rules (conditions + actions). |
| `composite_contributions` | string[] | Which composite indices this instrument feeds into. |
| `consistency_pairs` | array | Semantic consistency pair definitions (v2). |
| `sensitive_content` | bool | If true, instrument requires opt-in screen before first item and persistent pause button during administration (e.g. ACEs). |
| `sensitive_content_warning` | string? | Text shown on the opt-in screen. Required if sensitive_content is true. |
| `min_trials_for_scoring` | int? | Required for cognitive task definitions (Layer 5). Minimum trial count for valid scoring. Null for all non-cognitive instruments. |

**Versioning note:** The `version` field is semver-style (e.g. 1.0, 1.1). Any change to items, response options, scoring rules, routing triggers, or bands must increment version. Version is stored on AssessmentInstance at time of administration. Historical scores are interpreted against the definition version that was active when they were collected.

---

## 6. Assessment Flow State Machine (SUPERSEDED — see Section 15)

**Note:** This layer-based state machine is outdated. The definitive planet-centric state machine is in **Section 15**, which replaces linear layer progression with non-linear planet exploration and depth tiers.

The original states are retained below for reference only.

| State | Description | Transitions |
|---|---|---|
| `INTAKE_PENDING` | Session created, intake not started. | → `INTAKE_IN_PROGRESS` |
| `INTAKE_IN_PROGRESS` | User completing intake form. | → `INTAKE_COMPLETE` · → `EXCLUDED` |
| `INTAKE_COMPLETE` | Intake done. Layer 1 instruments queued. | → `LAYER_1_IN_PROGRESS` |
| `LAYER_1_IN_PROGRESS` | Completing Layer 1. Routing rules fire after each instrument. | → `LAYER_1_COMPLETE` · → `SAFETY_PAUSED` |
| `SAFETY_PAUSED` | Safety trigger fired. Crisis resources displayed. | → `SAFETY_ACKNOWLEDGED` → resumes previous state |
| `LAYER_1_COMPLETE` | All Layer 1 scored. Session 1 split point. | → `LAYER_2_IN_PROGRESS` |
| `LAYER_2_IN_PROGRESS` | Completing Layer 2. | → `LAYER_2_COMPLETE` |
| `LAYER_2_COMPLETE` | Layers 1+2 done. Partial formulation available. | → `FORMULATION_READY` (partial) |
| `LAYER_3_IN_PROGRESS` | Session 2: deep patterns. | → `LAYER_3_COMPLETE` |
| `LAYER_4_IN_PROGRESS` | Conditional: ASRS ≥ 4 or user opt-in. | → `LAYER_4_COMPLETE` |
| `FORMULATION_READY` | Full formulation can be generated. | → `REPORT_AVAILABLE` |
| `LAYER_5_PENDING` | Cognitive tasks available (separate session). | → `LAYER_5_IN_PROGRESS` |
| `COMPLETE` | All elected layers done. Full report available. | Terminal state. |

---

## 7. Composite Index Definitions (REVISED — Item 3)

Platform-derived summary scores. Calculated as **mean of z-scores** across available components. **NOT validated standalone instruments.** Always labelled as platform-derived. All partial composites labelled as "Index Name (n of N components)" in all outputs. Composite definitions are versioned in `composites.json`.

| Index | Components | required_core | required_minimum | Planet Ring | Compute |
|---|---|---|---|---|---|
| Distress Index | PHQ-9, GAD-7, LSAS total, WEMWBS (inverted) | [phq9, gad7] | 2 | Venus | mean_z. Fires as soon as Venus deep dives complete. |
| Regulatory Burden | DERS-16 total, AAQ-II, IUS-12 total | none | 2 | Neptune (Deep patterns) | mean_z. Any 2 of 3. |
| Social Friction | LSAS total, ECR-S avoidance, MSS-YSQ disconnection domain | none | 1 | Saturn | mean_z. |
| Executive Load | ASRS full, BDEFS-SF total, ISI (inverted) | [asrs_full, bdefs_sf] | 2 | Mars | mean_z. |
| Valued Living Gap | VLQ domain gaps where importance >= 7 | n/a | n/a | Jupiter | Mean gap score. Self-contained on Jupiter quick scan. |
| Protective Resources | SCS-SF, BRS, RSES, WEMWBS | none | 2 (from Earth) | Earth | mean_z. VIA-120 top-5 strengths represented as qualitative assets, not in composite. |

**Composite definition JSON schema (`instruments/definitions/composites.json`):**

```json
{
  "index_id": "distress_index",
  "version": "1.0",
  "components": ["phq9", "gad7", "lsas", "wemwbs_inv"],
  "required_core": ["phq9", "gad7"],
  "required_minimum": 2,
  "computation": "mean_z",
  "sign_inversions": ["wemwbs"]
}
```

**Composite engine pattern:**

```python
available = [z for instrument, z in components.items() if instrument in completed]
core_present = all(c in completed for c in required_core)
if core_present and len(available) >= required_minimum:
    score = mean(available)
    label = f"{len(available)} of {len(components)} components"
```

---

## 8. AI Prompt Architecture

The AI layer uses a structured three-block prompt. The system block is constant; context and task blocks are assembled dynamically.

### 8.1 System Block (constant)

| Section | Content |
|---|---|
| Role | You are a psychological exploration guide. You help users understand patterns in their assessment data. You are warm, curious, and intellectually honest. |
| Hard constraints | You NEVER compute scores. You NEVER diagnose. You NEVER make clinical recommendations. You NEVER present composite indices as validated clinical measures. You NEVER rephrase validated instrument items. |
| Epistemic rules | State uncertainty explicitly. Use "your responses suggest" not "you are". Distinguish self-report from objective measurement. Note cultural validity limitations. |
| Safety rules | If a safety flag is present, acknowledge with care. Do not minimise. Direct to crisis resources. Do not counsel. |
| Output rules | Respond in natural language. Reference the user's red-thread question. Group insights by theme, not by test name. |
| Red-thread quality rules | If red_thread_quality is 'low', avoid overclaiming specificity in narration. If red_thread_risk_flag is true, do not proceed with normal exploration. |
| Anchor change rules | If anchor_flag is present, acknowledge the change in the user's state with warm, non-alarming language before anything else. Do not proceed to instrument narration until acknowledged. |
| Theme state rules | For RICH themes: synthesise fully, group by pattern not test name. For PARTIAL themes: synthesise available data, note explicitly what is missing and which planet would add more. For SPARSE themes: one sentence only, state the area is unexplored, name the specific planet, do not speculate. |

### 8.2 Context Block (dynamic)

| Field | Source |
|---|---|
| `red_thread_question` | User's central question from intake (raw text) |
| `red_thread_quality` | enum: "good" / "low" / "empty" |
| `red_thread_risk_flag` | bool — true if crisis language detected in red-thread input |
| `red_thread_categories` | Array of up to 5 selected intake categories |
| `cultural_background` | Ethnicity and cultural context from intake |
| `session_anchors` | Current mood/energy/focus VAS scores |
| `anchor_delta` | Object: mood, energy, focus deltas vs previous session |
| `anchor_flag` | "notable_drop" / "significant_deterioration" / null |
| `completed_scores` | JSON array of all ScoreResult objects |
| `pbat_profile` | PBAT item-level scores + flagged areas to strengthen. First context signal for routing suggestions. |
| `active_flags` | Safety flags, elevated flags, cultural caveats |
| `composite_indices` | Computed composites (with platform-derived label, n of N component count) |
| `completion_state` | Which layers/instruments are done, pending, available |
| `theme_states` | Object: per-theme state (RICH / PARTIAL / SPARSE) for the 5 formulation themes |

### 8.3 Task Block (per interaction type)

| Interaction Type | Task Instruction |
|---|---|
| Inter-instrument narration | 2–3 sentence bridge between completed and next instrument. Reference red-thread. Explain what next instrument measures. |
| Mission control suggestion | Suggest next planet/instrument based on completion state and flags. Give reason. User can override. |
| Planet summary | Synthesise all scored data for this planet. 1–2 paragraphs. Group by theme, not test. Note uncertainty and caveats. |
| Full formulation | 5-theme narrative. Theme 1: Current distress. Theme 2: Maintaining processes. Theme 3: Relational/cognitive patterns. Theme 4: Values and friction. Theme 5: Protective resources. 1–2 paragraphs each. |

---

## 9. Open Questions

Items that need resolution but do not block Phase 1 work unless noted.

| Question | Context | Blocking |
|---|---|---|
| Solar system renderer technology | D3.js vs PixiJS vs SVG + Framer Motion. Prototype before committing. | Phase 5 |
| ~~PBAT (18-item anchor measure)~~ | **RESOLVED.** 29-item formative scale. Freely available, no licence required. Full spec in Section 11. | — |
| Instrument licensing | Priority order defined. No licences secured. LSAS-SR, CAT-Q, BDEFS-SF may be hard to licence commercially. PBAT confirmed free. | Pre-commercial deployment |
| z-score reference norms | Composites use z-standardisation. Against published population norms or within-user across sessions? | Phase 1 (composite engine) |
| Deployment target | Local only for v1? Cloud (Vercel + Fly.io / Railway)? | Phase 4+ |
| ~~PBAT integration point~~ | **RESOLVED.** Runs at session start in the cohesion layer. Item profile used by AI as first context signal for planet routing suggestions. See Section 11. | — |

---

## 10. Immediate Next Actions (SUPERSEDED — see Section 24)

**Note:** This section is outdated. The definitive next actions list is in **Section 24**, which reflects the revised battery (48 instruments), planet-centric architecture, and all gap analysis findings.

| # | Action | Output | Est. Effort |
|---|---|---|---|
| 1 | Finalise instrument definition JSON schema | Schema spec + example (phq9.json) | 1 session |
| 2 | Build BaseScorer + ScoreResult + GenericScorer | Core scoring abstractions | 1 session |
| 3 | Build scorer registry | Dynamic registration/lookup | 0.5 sessions |
| 4 | Write all Layer 1 instrument definitions | 11 JSON files | 2 sessions |
| 5 | Write Layer 2 instrument definitions | 6 JSON files (VLQ, Readiness, AAQ-II, CompACT, SCS-SF, BRS) | 1 session |
| 6 | Write Layer 3 instrument definitions | 6 JSON files | 1–2 sessions |
| 7 | Write Layer 4 instrument definitions + custom scorers | 3 JSON files + custom scorer classes (VLQ, BESQ, CAT-Q, Readiness, PBAT) | 1–2 sessions |
| 8 | Build composite index engine | z-standardisation, all 6 indices | 1 session |
| 9 | Build routing engine | Deterministic rule evaluation | 1 session |
| 10 | Build planet state calculator | Derived projection from completion state | 0.5 sessions |
| 11 | Full test suite across all instruments | pytest with known test vectors | 1 session |
| 12 | Resolve z-score norms open question | Decision document | 0.5 sessions |
| 13 | Database schema design | SQL DDL + SQLAlchemy models | 1 session |
| 14 | FastAPI app shell + assessment endpoints | Working API | 1–2 sessions |

---

## 11. PBAT Specification (Resolved)

The Process-Based Assessment Tool is freely available with no licence required (permanently free, confirmed via pbatsupport.com). It serves as the cohesion-layer process profile, administered at the start of every session alongside state anchors (mood/energy/focus VAS).

**Source:** Ciarrochi, J., Sahdra, B., Hofmann, S. G., & Hayes, S. C. (2022). Developing an item pool to assess processes of change in psychological interventions: The Process-Based Assessment Tool (PBAT). *Journal of Contextual Behavioral Science, 23*, 200–213.

### What Helix uses: Section 1 only (18 items)

Section 2 (outcome measures: items 19–29 covering mood, anxiety, stress, vitality, health, burnout) is **excluded** — these constructs are covered more rigorously by dedicated instruments in the battery (PHQ-9, GAD-7, WEMWBS, WSAS). Including both creates item fatigue and conceptual redundancy.

Modules excluded from v1: PBAT Compassion (under evaluation), PBAT Therapeutic Alliance (irrelevant — no therapist).

Scale: 0–100 VAS (Strongly Disagree → Strongly Agree). Time window: last week.

| # | Item | Domain | Valence |
|---|---|---|---|
| 1 | Able to change behaviour when it helped my life | Behavioural flexibility | + |
| 2 | Did things that hurt connection with people who matter | Social | − |
| 3 | Able to experience a range of emotions appropriate to the moment | Emotion regulation | + |
| 4 | Struggled to keep doing something good for me | Self-regulation | − |
| 5 | Did not find a meaningful way to challenge myself | Values/motivation | − |
| 6 | Acted in ways that helped my physical health | Physiological | + |
| 7 | My thinking got in the way of things important to me | Cognition | − |
| 8 | Paid attention to important things in my daily life | Attention | + |
| 9 | Did things only because complying with what others wanted | Autonomy | − |
| 10 | Stuck to strategies that seemed to have worked | Behavioural persistence | + |
| 11 | Found personally important ways to challenge myself | Values/motivation | + |
| 12 | Felt stuck and unable to change my ineffective behaviour | Flexibility | − |
| 13 | Used my thinking in ways that helped me live better | Cognition | + |
| 14 | Struggled to connect with moments in day-to-day life | Attention | − |
| 15 | Did things to connect with people who are important to me | Social | + |
| 16 | Chose to do things that were personally important to me | Values/autonomy | + |
| 17 | Acted in ways that hurt my physical health | Physiological | − |
| 18 | Did not find an appropriate outlet for my emotions | Emotion regulation | − |

Positive items: 1, 3, 6, 8, 10, 11, 13, 15, 16
Negative items: 2, 4, 5, 7, 9, 12, 14, 17, 18

### Critical: Formative scale, not reflective

PBAT items are **not expected to correlate**. Each adds unique process information. A total sum score is technically calculable but theoretically weak. The meaningful output is the **item-level profile** — which processes are active, which are low. Interpretation is **within-person** (relative highs and lows), not norm-referenced.

### Scoring Rules

| Rule | Detail |
|---|---|
| Reverse-score negative items | Items 2, 4, 5, 7, 9, 12, 14, 17, 18 — invert (100 - value) before aggregation. |
| Primary output | Item-level profile (18 scores). |
| Secondary output | Positive-process aggregate (mean of positive items after reverse-scoring negatives). Negative-process aggregate (mean of raw negative items). |
| Flag threshold | Any item < 30/100 flagged as "area to strengthen". |
| Do NOT report | A single total score as the primary metric. |
| Within-person interpretation | Most meaningful comparison is within-person — which processes are relatively high vs low for this individual. |
| Cultural validity | Broadly cross-cultural (VAS format, universal process constructs). |
| Licence | Free. No licence required. Permanently. |

### Integration in Helix

| Aspect | Decision |
|---|---|
| Position in flow | Runs at session start, alongside state anchors (mood/energy/focus VAS). Part of the cohesion layer, not assigned to a specific planet. |
| AI usage | The PBAT item profile is the AI agent's first context signal. It informs which planets to suggest visiting first (e.g. low scores on social items → suggest Saturn). |
| Repeat administration | Re-administered at the start of each session to track within-person change over time. |
| JSON definition | Requires a custom scorer (formative, item-profile output, not standard sum/mean). Add `pbat.py` to `scoring/instruments/`. |

### Revised Cohesion Layer Definition

The cohesion layer is no longer a single anchor score. It is a **process profile** comprising:

- PBAT Section 1 item scores (18 items, available from Session 1)
- Session state anchors: mood / energy / focus VAS (captured every session)
- Composite indices (available after Session 2 when component scores exist)

The AI agent reads this profile — not a single number — to determine which planet domains are weakest and which to suggest visiting first.


---

## 12. Red Team Findings

Critical issues identified through adversarial analysis. Severity rated as Blocking (must resolve before building), High (must resolve before shipping), or Medium (should resolve before scaling).

### 12.1 Blocking Issues

| # | Finding | Detail | Resolution |
|---|---|---|---|
| 1 | z-score norms must be resolved before composite engine | Composites use z-standardisation. Without a reference frame, they are meaningless on first administration. Within-user z-scores require n>1 sessions. | Use published population mean/SD where available (PHQ-9, GAD-7, WEMWBS all have published norms). For instruments without published norms, defer that composite until platform has sufficient user data, or use within-user change tracking from Session 2+. **Decide per-composite before building.** |
| 2 | More instruments need custom scorers than assumed | JSON schema assumes most instruments are simple sum/mean. LSAS-SR (paired fear/avoidance per item), BDEFS-SF (5 subscales), ASRS (Part A vs full clinical significance) may all need custom handling. | **Audit every instrument against the JSON schema before building GenericScorer.** List which truly fit generic vs custom. Expected split may be closer to 50/50 than 80/20. |

### 12.2 High Severity

| # | Finding | Detail | Resolution |
|---|---|---|---|
| 3 | Safety flag persistence on browser close | If user triggers SAFETY_PAUSED then closes browser, can they bypass safety acknowledgment on return? | Safety flags persist in database. On session resume, unacknowledged safety flags display crisis resources before any other content. SAFETY_PAUSED cannot be bypassed by closing/reopening. Design into schema. |
| 4 | AI must not over-weight composite indices | Composites look like real clinical scores but are unvalidated platform summaries. Risk that AI narratives treat them as primary evidence. | Add explicit system prompt instruction: "Composite indices are exploratory summaries. Weight them less than individual instrument scores. Never use a composite as the primary basis for a theme." |
| 5 | Formulation language must avoid quasi-diagnosis | Battery includes clinical screening instruments. "Your responses suggest significant depressive symptoms" reads as diagnosis regardless of disclaimer. | Formulation prompt: "Never say 'you have' or 'you suffer from'. Use 'your responses on [instrument] were in the [band] range, which is associated with [description]'. Follow elevated findings with 'a professional assessment could explore this further'." |
| 6 | VLQ importance ratings vulnerable to social desirability | Users overrate importance of things they feel they "should" care about, inflating gaps. | AI prompt note: "VLQ gaps may reflect social expectations rather than intrinsic values. Cross-reference with PBAT social/values items and AAQ-II avoidance patterns." |

### 12.3 Medium Severity

| # | Finding | Detail | Resolution |
|---|---|---|---|
| 7 | Session 1 completion time unknown | Full core flow plus initial exploration could exceed 40 minutes. May undermine "exploration not examination" philosophy. | Time yourself through the full core flow once assessment forms exist. If >25 minutes, cut scope. |
| 8 | Instrument licensing risk | LSAS-SR, CAT-Q, BDEFS-SF flagged as hard to licence commercially. | **Decision: Build with official instruments first** to validate product experience. Accept risk. Swap only if licensing fails. Do not pre-optimise around this. |
| 9 | LLM latency for formulation on local hardware | Full formulation from 20+ instruments of context may take 15-30s on M1 with Ollama 8B model. | Use task-appropriate model routing (see Section 13). Cloud fallback acceptable for full formulations. |
| 10 | Solar system metaphor adds cognitive load | "Your anxiety is on Venus" requires learning a mapping. Not all users want this. | Build both views: solar system (immersive, default) and dashboard (flat, direct). Let user switch. |
| 11 | User persona undefined | "Self-exploration platform" could serve therapy-curious, neurodivergent, clinician, or general curiosity audiences. | Capture user intent at intake ("what brings you here"). Adapt flow based on mode, not persona. See Section 14. |

---

## 13. AI Model Routing Strategy

Different AI tasks have different quality/speed requirements. Route to the most appropriate model per task.

| Task | Context Size | Quality Need | Latency Tolerance | Recommended Model | Fallback |
|---|---|---|---|---|---|
| Inter-instrument narration | Small (~200 tokens) | Medium | Low (immediate) | Semi-templated with light LLM polish, or local 8B | Cloud API |
| Planet summary | Medium (~500 tokens) | Medium-High | Medium (2-5s acceptable) | Local 8B (Llama 3.1 8B or equivalent) | Cloud API |
| Mission control suggestion | Small (~300 tokens) | Medium | Low | Local 8B or rule-based with LLM framing | Cloud API |
| Full 5-theme formulation | Large (~2-4K tokens) | High | High (15-30s acceptable with loading state) | Cloud API (Anthropic Sonnet/Opus) | Local 70B if available |
| Red-thread integration | Variable | High | Medium | Same as current task model | -- |

**Design principle:** The `LLMClient` abstraction accepts a `task_type` parameter. Config maps task types to model endpoints. Switching models per task is a config change, not a code change.

---

## 14. UX Design Decisions (Post-Red-Team)

### 14.1 Progressive Reward Model

Each instrument completion produces an immediate, visible result. The user gains information after every test, not only after completing an entire layer.

| Event | User Sees |
|---|---|
| Instrument completed | Planet illuminates further. Brief scored summary displayed (e.g. "Your responses were in the mild range"). AI narration connects result to red-thread question. |
| Moon unlocked | Extended test available (e.g. "You can go deeper on this dimension"). Framed as optional exploration, not required. |
| Composite index computable | Ring appears around planet. Brief explanation of what it represents. |
| Full formulation ready | "Your map is ready for a full reading" -- framed as a milestone reward. |

### 14.2 Quick Scan to Deep Dive Pattern

Generalise the PHQ-2 to PHQ-9 expansion pattern across the battery. Every planet has a quick entry point and an optional extended assessment.

| Planet | Quick Scan | Deep Dive |
|---|---|---|
| Mercury (Sleep, function, body) | ISI (7 items) | + WEMWBS (14) + Brief MAIA-2 (24) + MEQ (19) |
| Venus (Mood, emotion, awareness) | PHQ-2 + GAD-2 + PAQ-S (10 items) | PHQ-9 + GAD-7 + DERS-16 + PAQ full (24) |
| Earth (Core self) | BFI-S (15 items) + VIA-IS-P (24 items) | IPIP-50 + SCS-SF + BRS + RSES (10) + ACEs (10) + VIA-120 (standalone session) |
| Mars (Attention and drive) | ASRS Part A (6 items) | ASRS Full + BDEFS-SF |
| Jupiter (Values, motivation, meaning) | VLQ (10 domains) | + AAQ-II + CompACT + MLQ (10) |
| Saturn (Social and relational) | LSAS-SR short (~12 items) | LSAS-SR full + ECR-S + ECR-RS (36) + De Jong Gierveld (6) |
| Neptune (Deep patterns) | IUS-12 (12 items) | + MSS-YSQ (76) + PTQ-10 + CPQ (12) + DSS-B (10) + PSWQ (16) + OCI-R (18) |
| Uranus (Neurodivergence) | AQ-10 (10 items, conditional) | + CAT-Q + RAADS-R (80, standalone session) |

**Note — SDS:** Moved to core flow (administered universally as functional impairment baseline).

**Note — Uranus (Neurodivergence):** LOCKED by default. Not in default quick scan. Activates via: (a) intake intent "I think I might be neurodivergent", (b) ASRS Part A >= 4 routing trigger from Mars, or (c) explicit user opt-in. Uranus is visible in the solar system but dim/locked until activated.

**Note — Readiness Rulers:** CUT from v1. Redundant with VLQ gap, AAQ-II, CompACT valued action subscale. v2 candidate.

**Routing rule change:** Quick scans are available from the start (after core flow). Deep dives unlock based on either (a) routing triggers from quick scan scores, or (b) user choice ("I want to explore this more"). This replaces the rigid Layer 1 to Layer 2 to Layer 3 sequence with a planet-centric exploration model.

**Implication for state machine:** The layer-based state machine in Section 6 needs revision. Instead of layer-based states, it becomes planet-based with depth tiers. This is a significant redesign -- see Section 15.

### 14.3 Core Flow (Universal) — REVISED

All users complete this regardless of intent. Total core flow: ~32 items + intake.

1. **Intake** — Two-step red-thread design:
   - Step 1: "In one or two sentences, what would you most like to understand about yourself right now?" (free text, soft min 20 chars, 4 example answers shown). Crisis language detection on input — if flagged, triggers SAFETY_PROTOCOL immediately.
   - Step 2: "Choose up to 5 areas you'd like to focus on" from 10 categories: Mood and anxiety (Venus), Sleep and energy (Mercury), Relationships and connection (Saturn), Attention and focus (Mars), Identity and personality (Earth), Values and meaning (Jupiter), Childhood and history (Earth/ACEs), Neurodivergence (Uranus), Trauma and past experiences (Neptune), General self-understanding (AI selects). Optional: rank top 3.
   - Also captures: presenting concerns, cultural background, existing reports.
2. **PBAT Section 1** (18 items — process profile, first routing signal)
3. **Session state anchors** (mood / energy / focus VAS, 3 items)
4. **WSAS** (5 items — functional impairment baseline, IAPT standard, cross-domain context)
5. **PC-PTSD-5** (5 items) — minimally framed pre-exploration screen. No clinical label shown. Items presented verbatim under framing: "Before your first exploration, a few brief questions about recent experiences." Score < 3: session continues, result stored as context. Score >= 3: SAFETY_PROTOCOL fires before solar system opens.
6. **AI recommends 2-3 planets** based on PBAT profile and intake categories. User visits 2-3 planets in Session 1. Remaining planets available from Session 2+.

**ACEs auto-deferral:** If PC-PTSD-5 >= 3 or red_thread_risk_flag is true, ACEs is automatically deferred. Not surfaced until user is in SAFETY_ACKNOWLEDGED state and explicitly navigates to Earth deep dive.

After the core flow, the experience branches based on what the user wants to explore. The AI mission control suggests planets based on PBAT profile, intake categories, and completed scores. The user can always override.

### 14.4 Intent Capture at Intake

Add to intake: "What brings you here?" -- maps to adaptive flow behaviour.

| Intent | Flow Adaptation |
|---|---|
| "I want to understand myself better" | Broad exploration. AI suggests diverse planets. Encourage breadth. |
| "I'm struggling and want to understand why" | Prioritise distress-related planets (Venus, Mercury). Surface safety screening early. |
| "I think I might be neurodivergent" | Fast-track to Mars (ADHD) and Uranus (neurodivergence). Deep dives available immediately. |
| "I'm curious about my personality and patterns" | Start with Earth (core self), then Neptune (deep patterns). |
| "Someone recommended I try this" | Guided mode. AI takes stronger lead on routing. More narration. |

### 14.5 Language Simplification Policy

- **Item text on validated instruments:** verbatim, never changed. (Locked decision.)
- **Framing text around items:** can be simplified. E.g. instead of "Over the last 2 weeks, how often have you been bothered by the following problems?" use "Thinking about the last 2 weeks..."
- **AI narration:** warm, accessible, avoids clinical jargon. Explains concepts in plain language.
- **Result summaries:** plain language with option to see clinical detail. E.g. "Your mood responses suggest things have been quite tough recently" with expandable "PHQ-9 score: 14/27 -- moderate range".

---

## 15. Revised State Machine (Draft)

The layer-based state machine (Section 6) is superseded by this planet-centric exploration model. Full redesign is Phase 2 work.

### Session States

| State | Description |
|---|---|
| `INTAKE_PENDING` | Session created, intake not started. |
| `CORE_FLOW_IN_PROGRESS` | User completing intake, PBAT, state anchors, safety screen. |
| `EXPLORING` | Core flow complete. User navigating planets freely. Can complete quick scans or deep dives in any order. |
| `SAFETY_PAUSED` | Safety trigger fired. Crisis resources displayed. **Persists across browser sessions. Cannot be bypassed.** |
| `SAFETY_ACKNOWLEDGED` | User acknowledged safety screen. Resumes `EXPLORING`. |
| `FORMULATION_AVAILABLE` | Sufficient data for partial formulation (at least 3 planets with quick scan complete). |
| `FULL_FORMULATION_READY` | All quick scans complete OR user requests full formulation with current data. |
| `COGNITIVE_TASKS_AVAILABLE` | Layer 5 unlocked (separate session, always optional). |

### Planet States (per planet, per user)

| State | Description |
|---|---|
| `LOCKED` | Planet not yet available (core flow not complete). |
| `AVAILABLE` | Quick scan available. Planet visible but dim. |
| `SCANNED` | Quick scan complete. Planet partially illuminated. Result summary visible. |
| `DEEP_DIVE_AVAILABLE` | Extended tests unlocked (by routing trigger or user choice). Moons visible but dim. |
| `DEEP_DIVE_IN_PROGRESS` | User working through extended instruments. |
| `DEEP_DIVE_COMPLETE` | All available instruments for this planet scored. Planet fully illuminated. |

**Asteroid Belt States:**

| State | Description |
|---|---|
| `SCREENING_COMPLETE` | PC-PTSD-5 completed in core flow. Score stored. |
| `TRAUMA_DEEP_DIVE_AVAILABLE` | PC-PTSD-5 >= 3 AND safety acknowledged. PCL-5 unlocked. |
| `TRAUMA_DEEP_DIVE_COMPLETE` | PCL-5 scored. Full trauma profile available for formulation. |

### Key Differences from Section 6

- **Non-linear:** User chooses planet order. No mandatory sequence after core flow.
- **Depth tiers:** Quick scan to deep dive replaces Layer 1 to Layer 2 to Layer 3.
- **Always explorable:** User can return to any planet, view results, or go deeper at any time.
- **Routing still governs:** Deep dives can be auto-unlocked by routing triggers (ASRS >= 4 unlocks Mars deep dive) or manually chosen by user.
- **Formulation is progressive:** Partial formulations available as data accumulates, not only after full completion.

**Note:** Section 6 (original layer-based state machine) is retained for reference but is superseded by this design.


---

## 16. Clinical Utility Framework

Helix's value to mental health professionals depends on producing output that clinicians trust, understand, and can integrate into their practice.

### 16.1 How Helix Compares to Professional Assessment

| Dimension | Clinical Psychologist | Helix | Gap |
|---|---|---|---|
| Clinical interview | 1-2 hours face-to-face. Observes affect, incongruence, presentation. | None. Self-report only. | Fundamental. Cannot be closed by software. |
| Standardised instruments | 2-5 selected based on presenting concerns. Narrow but targeted. | 48 instruments across all PBT process domains. Broad and systematic. | Helix has greater breadth. Professional has better targeting. |
| Formal diagnosis | DSM-5/ICD-11 with legal and insurance weight. | Explicitly does not diagnose. Screens and profiles. | By design. Helix is pre-clinical, not clinical. |
| Collateral information | Partner reports, school records, workplace data, prior treatment. | Self-report only. User can upload prior reports at intake. | Significant. Partially addressed by report upload. |
| Clinical judgment | Knows when scores do not fit. Recognises minimisation, cultural distortion. | Flags patterns programmatically. AI notes uncertainty. Cannot replicate judgment. | Significant. Partially addressed by validity checks and cultural caveats. |
| Longitudinal tracking | Rare in routine practice. Usually pre/post only. | PBAT repeat administration. Session-to-session change tracking across all instruments. | Helix advantage. |
| Cross-domain synthesis | Depends on clinician expertise. Often siloed by specialism. | Systematic composite indices. AI formulation spans all domains. | Helix advantage for breadth. Professional advantage for depth. |
| Process-based formulation | Available from PBT-trained clinicians only. Minority of the profession. | Built into the platform. Every user gets a structured PBT formulation. | Helix advantage for access. Professional advantage for nuance. |

### 16.2 Making Helix Useful to Clinicians

**Output mode 1: Clinical intake packet.**
A structured PDF report that a user can bring to their first therapy session, saving the clinician 1-2 sessions of intake assessment.

Requirements: every score presented with published norms, interpretive bands referenced to validation studies, flagged clinical thresholds, cultural validity labels visible, clear disclaimer, organised by presenting concern rather than by planet.

**Output mode 2: Process-based case formulation template.**
The AI formulation output maps directly to a PBT case formulation structure that CBT, ACT, and schema therapists already use. Themes correspond to: maintaining processes, relational patterns, values friction, and protective factors.

**Output mode 3: Pre/post outcome measurement.**
If a therapist asks a client to complete Helix at intake and again at session 12/24, the change scores across the battery provide a comprehensive outcome suite. The PBAT's repeat-administration design supports this directly.

**Output mode 4: Clinician-facing dashboard.**
Flat, structured view of all scores with subscales, percentiles (where norms exist), flags, and formulation themes. No solar system metaphor. Exportable.

### 16.3 Report Structure for Clinical Use

The clinical report must include:

1. **Identifying information** -- user demographics, date of assessment, session context
2. **Presenting concerns** -- red-thread question, intake narrative
3. **Assessment validity** -- consistency check results, rapid-response flags, session-state anchors
4. **Screening results** -- safety flags, clinical threshold breaches, referral recommendations
5. **Domain-by-domain findings** -- each PBT domain with instrument scores, interpretive bands, subscale breakdowns, cultural caveats
6. **Cross-domain patterns** -- composite indices (labelled as platform-derived), interlinkage findings (e.g. ASRS x ISI, LSAS x AQ-10)
7. **Process-based formulation** -- 5-theme narrative synthesis
8. **Calibration notes** -- alexithymia level (PAQ), interoceptive awareness (MAIA-2), and how these may affect interpretation of other scores
9. **Strengths and protective factors** -- SCS-SF, BRS, WEMWBS, PBAT positive processes
10. **Appendix** -- per-instrument scoring methodology, source citations, raw score tables

---

## 17. Complete Instrument Battery (Revised)

This is the definitive instrument list incorporating all planning decisions, red team findings, independent audit, and clinical utility requirements.

### 17.1 Cohesion Layer (every session)

| Instrument | Items | Scale | Purpose | Licence | Custom Scorer |
|---|---|---|---|---|---|
| PBAT Section 1 | 18 | 0-100 VAS | Cross-domain process profile. First routing signal for AI. | Free, permanently | Yes (formative, item-profile) |
| Session state anchors | 3 | 0-10 VAS | Mood, energy, focus at session start. | N/A (platform-designed) | No |

### 17.2 Silent Safety Screen (runs in background)

| Instrument | Items | Scale | Purpose | Licence | Custom Scorer |
|---|---|---|---|---|---|
| PC-PTSD-5 | 5 | Yes/No | Trauma screen. Threshold >= 3 triggers safety protocol. | VA/NCPTSD, clear contact path | No |

### 17.3 Planet: Mercury -- Sleep, Function, and Body

| Tier | Instrument | Items | Scale | Purpose | Licence |
|---|---|---|---|---|---|
| Quick scan | ISI | 7 | 0-4 Likert | Insomnia severity | Rights check needed |
| ~~SDS~~ | — | — | **Moved to core flow as WSAS.** See Section 30.2. | — |
| Deep dive | WEMWBS | 14 | 1-5 Likert | Positive mental wellbeing | Warwick licence portal |
| Deep dive | Brief MAIA-2 | 24 | 0-5 Likert | Interoceptive awareness (8 subscales) | Free, UCSF public domain |

**Rationale for MAIA-2 addition:** Interoception underpins emotion regulation, trauma responses, anxiety, and somatic symptoms. A user high on DERS-16 but low on interoceptive awareness has a fundamentally different profile. Freely available from UCSF with no permission required.

### 17.4 Planet: Venus -- Mood, Emotion, and Emotional Awareness

| Tier | Instrument | Items | Scale | Purpose | Licence |
|---|---|---|---|---|---|
| Quick scan | PHQ-2 | 2 | 0-3 Likert | Depression screen. >= 3 expands to PHQ-9. | Public domain |
| Quick scan | GAD-2 | 2 | 0-3 Likert | Anxiety screen. >= 3 expands to GAD-7. | Public domain |
| Quick scan | PAQ-S | 6 | 1-7 Likert | Alexithymia screen (overall level) | Free (Curtin University) |
| Deep dive | PHQ-9 | 9 (7 new) | 0-3 Likert | Depression severity. Item 9 = safety flag. | Public domain |
| Deep dive | GAD-7 | 7 (5 new) | 0-3 Likert | Anxiety severity. | Public domain |
| Deep dive | DERS-16 | 16 | 1-5 Likert | Emotion dysregulation (6 subscales) | Easy-moderate licence |
| Deep dive | PAQ | 24 | 1-7 Likert | Full alexithymia profile (5 subscales, positive + negative valence) | Free (Curtin University) |

**Rationale for PAQ addition:** Alexithymia is a major calibration signal. Users who cannot identify their emotions will score unreliably on every emotion-related instrument. PAQ-S at quick scan level (6 items) costs almost nothing. Full PAQ gives valence-specific profiles (positive vs negative emotion processing). Cross-culturally validated across Western and Middle Eastern samples. If alexithymia is detected, it flags as a context modifier on all downstream emotion-related instruments.

**Alexithymia as calibration signal:** When PAQ-S or PAQ scores indicate elevated alexithymia, the AI formulation must note: "This user reports difficulty identifying and describing emotions. Self-report scores on PHQ-9, GAD-7, DERS-16, and PBAT emotion items should be interpreted with additional caution -- emotional distress may be underreported."

**PAQ-S to PAQ carry-forward (LOCKED):** PAQ-S items are a clean subset of the full PAQ. Users who expand to the full PAQ see only the 18 new items, not all 24. Carry-forward via `parent_instance_id`, consistent with PHQ-2 to PHQ-9 pattern.

### 17.5 Planet: Earth -- Core Self

| Tier | Instrument | Items | Scale | Purpose | Licence |
|---|---|---|---|---|---|
| Quick scan | BFI-S | 15 | 1-5 Likert | Big Five personality (short form) | Open/public domain |
| Deep dive | IPIP-50 | 50 | 1-5 Likert | Big Five personality (full profile) | Fully open, public domain |
| Deep dive | SCS-SF | 12 | 1-5 Likert | Self-compassion (6 subscales) | Moderate licence |
| Deep dive | BRS | 6 | 1-5 Likert | Resilience (bounce-back capacity) | Moderate licence |
| Deep dive | RSES | 10 | 0-3 Likert | Global self-esteem | Public domain |

**Rationale for RSES addition:** Self-esteem is distinct from self-compassion (SCS-SF) and schema-level defectiveness (MSS-YSQ). The Rosenberg is the most widely validated measure in psychology, 10 items, public domain. Fills a gap between trait-level (Big Five) and schema-level (MSS-YSQ) self-concept.

### 17.6 Planet: Mars -- Attention and Executive Function

| Tier | Instrument | Items | Scale | Purpose | Licence |
|---|---|---|---|---|---|
| Quick scan | ASRS Part A | 6 | 0-4 Likert | ADHD symptom screen. >= 4 triggers Uranus neurodivergence routing + Mars deep dive. | Check rights for commercial |
| Deep dive | ASRS Full v1.1 | 18 (12 new) | 0-4 Likert | Full ADHD symptom profile | Check rights for commercial |
| Deep dive | BDEFS-SF | 20 | 1-5 Likert | Executive function in daily life (5 subscales) | Hard -- likely proprietary |

### 17.7 Planet: Jupiter -- Values, Motivation, Meaning, and Flexibility

| Tier | Instrument | Items | Scale | Purpose | Licence |
|---|---|---|---|---|---|
| Quick scan | VLQ | 10 domains x 2 | 1-10 Likert | Valued living: importance vs consistency per domain | Moderate-hard licence |
| Deep dive | AAQ-II | 7 | 1-7 Likert | Psychological inflexibility / experiential avoidance | Moderate-hard licence |
| Deep dive | CompACT | 23 | 0-6 Likert | Psychological flexibility (3 subscales: openness to experience, behavioral awareness, valued action) | Free for clinical and research use |
| Deep dive | MLQ | 10 | 1-7 Likert | Meaning in Life: Presence vs Search subscales | Free from author website |

**Rationale for MLQ addition:** Values (VLQ) and meaning (MLQ) are distinct constructs. A user with clear values but no felt sense of meaning is a fundamentally different profile from one who has both or neither. 10 items, freely available.

**Rationale for CompACT alongside AAQ-II:** AAQ-II measures inflexibility (the problem). CompACT measures flexibility (the resource), with three subscales that map to PBT process domains. Together they give the richest available picture of the central PBT construct. Both are free. Full 23-item version used (Atkins et al.) — no validated brief form exists.

### 17.8 Planet: Saturn -- Social and Relational

| Tier | Instrument | Items | Scale | Purpose | Licence |
|---|---|---|---|---|---|
| Quick scan | LSAS-SR short | ~12 | 0-3 paired (fear + avoidance) | Social anxiety screen | Hard to licence commercially |
| Deep dive | LSAS-SR full | 48 (24 situations x 2 ratings) | 0-3 paired | Full social anxiety profile (performance + social interaction subscales) | Hard to licence commercially |
| Deep dive | ECR-S | 12 | 1-7 Likert | General attachment (anxiety + avoidance subscales) | Moderate licence |
| Deep dive | ECR-RS | 36 (9 items x 4 targets) | 1-7 Likert | Structured attachment: mother, father, romantic partner, best friend | Free |

**Rationale for ECR-RS addition:** Someone securely attached to a partner but anxiously attached to a parent has a completely different clinical profile. ECR-RS gives four separate attachment profiles using the same 9-item structure. Extends ECR-S for users wanting relational depth.

### 17.9 Planet: Uranus -- Neurodivergence

| Tier | Instrument | Items | Scale | Purpose | Licence |
|---|---|---|---|---|---|
| Quick scan | IUS-12 | 12 | 1-5 Likert | Intolerance of uncertainty (prospective + inhibitory) | Moderate licence |
| Deep dive | MSS-YSQ | 76 | 1-6 Likert | Maladaptive schemas (19 schemas, 6 unmet needs clusters) | Open source, no permission needed |
| Deep dive | PTQ-10 | 10 | 0-4 Likert | Perseverative thinking (content-independent rumination) | Moderate licence |
| Deep dive | CPQ | 12 | 1-4 Likert | Clinical perfectionism (maintaining factor) | Free for research/clinical |
| Deep dive | DSS-B | 10 | 0-4 Likert | Dissociative experiences screen (DSM-5 Level 2 Cross-Cutting) | Free (APA) |

**BESQ replaced by MSS-YSQ:** The MSS-YSQ has superior psychometric properties (Rasch-validated, 2024), covers 19 schemas vs BESQ's 18 with better item quality, maps to childhood unmet needs clusters (clinically actionable), is open source with no licence required, and has an adaptive version (MSS-YSQ-Dynamic) that reduces administration by ~36%.

**Rationale for CPQ addition:** Clinical perfectionism is one of the most transdiagnostic maintaining factors. It drives anxiety (GAD-7), depression (PHQ-9), schema activation (Failure, Unrelenting Standards), and social avoidance (LSAS). 12 items, free. Measuring it directly is cleaner than inferring from cross-instrument patterns.

**Rationale for DSS-B addition:** Dissociation is relevant in trauma (PC-PTSD-5), ADHD (attentional dissociation), and autism. 10 items, free (APA DSM-5 Level 2 Cross-Cutting Symptom Measure). Flags a clinically important dimension currently invisible in the battery.

### 17.10 Planet: Neptune -- Deep Patterns and Hidden Depths

| Tier | Instrument | Items | Scale | Purpose | Licence |
|---|---|---|---|---|---|
| Quick scan | AQ-10 | 10 | 4-point | Autism traits screen. >= 6 triggers referral note. | NICE-linked, usable with attribution |
| Deep dive | CAT-Q | 25 | 1-7 Likert | Camouflaging / masking (3 subscales) | Hard -- newer, author outreach |

### 17.11 Optional: Substance Use Context (user opt-in)

| Instrument | Items | Scale | Purpose | Licence |
|---|---|---|---|---|
| AUDIT-C | 3 | Varies | Alcohol use screen | Free, WHO-developed |
| DAST-10 | 10 | Yes/No | Drug use screen | Free |

**Positioning:** These are not assigned to a planet. They are offered as optional context at intake for users who want a comprehensive profile. If completed, substance use data becomes a context modifier on PHQ-9, GAD-7, ISI, and ASRS interpretation. The AI formulation notes: "Substance use patterns may be contributing to or interacting with the mood/sleep/attention patterns identified."

### 17.12 Layer 5: Cognitive Tasks (separate session, jsPsych)

| Task | Measures | Purpose |
|---|---|---|
| Flanker | Interference control, response inhibition | Attention/inhibition |
| Stroop-style | Cognitive interference | Attention/inhibition |
| N-back (2-back) | Working memory updating | Working memory |
| Digit span | Working memory capacity | Working memory |
| Symbol matching | Processing speed | Processing speed |
| Trail Making B-style | Set shifting, cognitive flexibility | Executive switching |
| Tower-style planning | Planning, sequencing | Executive planning |

---

## 18. Instrument Interlinkage Map (Revised)

These are the key cross-instrument relationships the formulation engine should surface.

| Link | Instruments | Clinical Significance |
|---|---|---|
| ADHD x Executive function | ASRS x BDEFS-SF | Self-report symptoms x daily-life executive behaviour |
| ADHD x Cognitive tasks | ASRS x Layer 5 | Self-report x objective performance discrepancy |
| Social anxiety x Attachment | LSAS x ECR-S/ECR-RS | Avoidance: anxiety-driven vs attachment-driven |
| Social anxiety x Autism | LSAS x AQ-10 | Social avoidance: anxiety vs autistic trait |
| Autism x Masking | AQ-10 x CAT-Q | Low AQ + high CAT-Q = masking pattern |
| Depression x Dysregulation | PHQ-9 x DERS-16 | Symptom severity x emotion regulation process |
| Anxiety x Uncertainty | GAD-7 x IUS-12 | Symptom severity x maintaining cognitive factor |
| Anxiety x Rumination | GAD-7 x PTQ-10 | Anxiety x perseverative thinking loop |
| Anxiety x Perfectionism | GAD-7 x CPQ | Anxiety maintained by perfectionist standards |
| Values x Schemas | VLQ x MSS-YSQ | Value gaps x schema-driven avoidance patterns |
| Meaning x Values | MLQ x VLQ | Felt meaningfulness vs specific value alignment |
| Avoidance x Dysregulation | AAQ-II x DERS-16 | Experiential avoidance x emotion dysregulation |
| Flexibility x Inflexibility | CompACT x AAQ-II | Resource (flexibility) vs problem (inflexibility) |
| Self-compassion x Schemas | SCS-SF x MSS-YSQ | Compassion moderates failure/defectiveness schemas |
| Personality x Schemas | IPIP-50 x MSS-YSQ | Trait context for schema thresholds |
| Trauma x Dysregulation | PC-PTSD-5 x DERS-16 | Trauma amplifies dysregulation interpretation |
| Trauma x Dissociation | PC-PTSD-5 x DSS-B | Trauma x dissociative coping |
| Sleep x ADHD | ISI x ASRS | Sleep deprivation compounds ADHD severity |
| Wellbeing x Resources | WEMWBS x BRS + SCS-SF | Calibrates protective factor meaning |
| Alexithymia x Emotion measures | PAQ x PHQ-9 + GAD-7 + DERS-16 + PBAT | Calibration: low emotional literacy may distort all emotion self-report |
| Interoception x Dysregulation | Brief MAIA-2 x DERS-16 | Body awareness context for emotion regulation |
| Interoception x Anxiety | Brief MAIA-2 x GAD-7 | Heightened body awareness can amplify or regulate anxiety |
| Self-esteem x Schemas | RSES x MSS-YSQ (Defectiveness, Failure) | Global self-worth vs specific maladaptive beliefs |
| Attachment structure x Social | ECR-RS x LSAS x MSS-YSQ disconnection | Relationship-specific attachment patterns vs general social functioning |

### 18.1 Calibration Signals

Two instruments serve as calibration signals that modify interpretation of the entire battery. These are architecturally distinct from regular instruments.

| Signal | Instrument | Effect |
|---|---|---|
| Alexithymia | PAQ-S / PAQ | If elevated: flag all emotion-related instruments (PHQ-9, GAD-7, DERS-16, PBAT emotion items) with caveat "emotional distress may be underreported due to difficulty identifying feelings". AI formulation adjusts confidence in emotion-domain findings. |
| Cultural background | Intake demographic | If non-Western background + high-bias-risk instrument: append cultural validity caveat. AI formulation notes where norms may not apply. |

---

## 19. Battery Statistics

### 19.1 Quick Scan Totals (all default planets)

| Component | Items |
|---|---|
| **Core flow:** | |
| PBAT Section 1 | 18 |
| State anchors | 3 |
| WSAS (functional impairment baseline) | 5 |
| PC-PTSD-5 (pre-exploration screen) | 5 |
| **Planet quick scans (default):** | |
| ISI (Mercury) | 7 |
| PHQ-2 + GAD-2 + PAQ-S (Venus) | 10 |
| BFI-S + VIA-IS-P (Earth) | 39 |
| ASRS Part A (Mars) | 6 |
| VLQ (Jupiter) | 20 (10 domains x 2 ratings) |
| LSAS-SR short (Saturn) | ~12 |
| IUS-12 (Uranus) | 12 |
| ~~AQ-10 (Neptune)~~ | ~~10~~ — conditional only, not in default |
| **Total default quick scan** | **~135 items** |

**Session 1 design:** User completes core flow (~29 items) then visits 2-3 planets (~30-60 items depending on planets chosen). Target Session 1 time: ~20-25 minutes. Remaining planets available from Session 2+.

### 19.2 Full Battery Totals (all quick scans + all deep dives)

| Component | Items |
|---|---|
| Default quick scan total | ~135 |
| Neptune quick scan (conditional) | 10 |
| Mercury deep dive | 91 (WEMWBS 14 + Brief MAIA-2 24 + MEQ 19 + PSQI 19 + FFMQ-15 15) |
| Venus deep dive | 74 (PHQ-9 7 new + GAD-7 5 new + DERS-16 16 + PAQ 18 new after carry-forward + PSS-10 10 + DTS 15 + ERQ 10) |
| Earth deep dive | 88 (IPIP-50 50 + SCS-SF 12 + BRS 6 + RSES 10 + ACEs 10) |
| Mars deep dive | 57 (ASRS Full 12 new + BDEFS-SF 20 + CFQ-25 25) |
| Jupiter deep dive | 45 (AAQ-II 7 + CompACT 23 + MLQ 10 + SWLS 5) |
| Saturn deep dive | 90 (LSAS full ~36 new + ECR-S 12 + ECR-RS 36 + De Jong Gierveld 6) |
| Uranus deep dive | 105 (CAT-Q 25 + RAADS-R 80, standalone session) |
| Neptune deep dive | 142 (MSS-YSQ 76 + PTQ-10 10 + CPQ 12 + DSS-B 10 + PSWQ 16 + OCI-R 18) |
| VIA-120 (standalone session) | 120 |
| Optional substance | 13 (AUDIT-C 3 + DAST-10 10) |
| **Total full battery** | **~1,063 items** (excluding cognitive tasks) |

This is a comprehensive battery comparable in breadth to a full clinical assessment. No user is expected to complete everything -- the quick scan to deep dive architecture means users explore at their own depth.

### 19.3 Instrument Count Summary

| Category | Count |
|---|---|
| Validated instruments | 48 (including short forms counted separately) |
| Custom scorers needed | 8 (PBAT, VLQ, MSS-YSQ, PAQ, LSAS-SR, ECR-RS, MEQ, PSQI) |
| Generic scorer handles | ~40 |
| Free / public domain | 24 |
| Licence required | 10 |
| Hard to licence | 3 (LSAS-SR, CAT-Q, BDEFS-SF) |
| Open source | 2 (MSS-YSQ/MSS, IPIP-50) |


---

## 20. Legal and Compliance (Deferred to Post-MVP)

**Decision:** Legal compliance work is deferred until after MVP is functional. The scoring engine, instrument definitions, and data architecture are the priority. Legal requirements will be layered on top of a working system.

**Items to address before any deployment to real users:**

- GDPR Special Category Data: mental health data requires explicit consent and lawful basis
- Mandatory DPIA (Data Protection Impact Assessment) before collecting user data
- ICO registration (UK data protection authority)
- Encryption at rest for all stored assessment data
- Right to erasure: schema must support full user data deletion (design for this in Phase 2 schema, even if the endpoint is built later)
- Data retention policy: define how long assessment data is stored
- MHRA medical device risk: the AI formulation narrative is the liability point -- if it could be interpreted as providing clinical advice, the product may fall under medical device regulation. The persistent disclaimer and the strict "never diagnose" AI constraints are the first line of defence, but this needs formal review.

**Schema design note for Phase 2:** Even though legal compliance is deferred, the database schema should be designed with erasure in mind from the start. This means: user data must be deletable in a single cascade operation, no orphaned assessment data, and no hard dependencies on user identity in scoring or composite calculation logic.

---

## 21. Additional Open Questions (from Gap Analysis)

These are added to the open questions identified in Section 9.

| Question | Context | Blocking |
|---|---|---|
| Test-retest interval enforcement | PHQ-9 has a 2-week time window. Re-administering within that window produces psychometrically invalid scores. Other instruments have their own windows (WEMWBS = 2 weeks, PBAT = 1 week, ISI = 2 weeks). The routing engine must enforce minimum intervals between re-administrations of the same instrument. | Phase 2 (routing engine must know about time windows) |
| Partial session handling | What happens when a user closes the browser mid-instrument? Options: (a) save item-by-item and resume from last answered, (b) discard incomplete instrument and restart, (c) save partial and flag as incomplete. Option (a) is best for UX but requires item-level persistence. | Phase 2 (schema + API design) |
| Longitudinal data model | The schema stores scores per session but has no explicit trend calculation or time-series design. For repeat PBAT administration and pre/post measurement, the system needs: score deltas between sessions, trend direction per instrument, and time-series queries. This is a schema and API concern, not a scoring engine concern. | Phase 2 (schema design) |

---

## 22. UX Gaps (from Gap Analysis)

### 22.1 The Empty Solar System Problem

When a new user first sees the solar system, every planet is dark. This is the correct state (nothing assessed yet) but it's a terrible first impression -- it communicates "you have nothing" rather than "you have everything to explore."

**Design options:**
- All planets visible but dim, with gentle pulsing or atmospheric effects suggesting life/potential
- The Sun (red-thread question) is already lit after intake, giving the system a warm centre
- AI mission control welcomes the user and suggests the first planet to visit, framing darkness as mystery rather than emptiness
- Brief animated reveal sequence after intake: planets fade in one by one as the AI explains what each dimension represents

**Decision needed:** Phase 5 (frontend), but the concept should be defined in the UX spec before then.

### 22.2 Post-Formulation Pathways

After the user receives their formulation, the current spec has no "what next." Options:

| Pathway | Description | Feasibility |
|---|---|---|
| Therapist export | "Bring this to your first session" -- generate clinical intake packet PDF. Named as a core use case. | Phase 2 (report engine). High priority. |
| Resource recommendations | Based on formulation themes, suggest relevant resources (books, apps, techniques). Not clinical recommendations -- educational pointers. | Phase 3 (AI pipeline). Medium priority. |
| Repeat assessment | "Come back in 4 weeks and see how things have changed." Re-administer PBAT + selected instruments. Track change over time. | Phase 2 (longitudinal model). Medium priority. |
| Therapist directory | Link to therapist finder services (e.g. BACP, Psychology Today). Not a referral -- a pointer. | Phase 5 (frontend). Low priority for MVP. |
| Deep dive invitation | "You've done the quick scan. Want to explore Venus in more depth?" Encourage deeper exploration of specific planets. | Already designed in the quick scan to deep dive architecture. |

**Decision:** Therapist export is the highest-priority post-formulation pathway. Frame it as: "Your Helix report is designed to give a therapist a head start. Download your clinical intake packet to bring to your first session."

### 22.3 Re-engagement and Longitudinal Change UX

How does the solar system communicate change over time?

**Options:**
- Planet brightness changes between sessions (brighter = improvement, dimmer = deterioration). Risk: oversimplification.
- Dual-state planets: current state + previous state visible as a ghost/shadow. Shows direction of change.
- Timeline slider: scrub through past sessions to see how the solar system looked at each point.
- Change indicators: small arrows on planets (up/down/stable) showing score direction since last assessment.

**Decision needed:** Phase 5, but the data model must support it (Phase 2).

---

## 23. Updated Phase 2 Tasks

The following tasks are added to Phase 2 based on the gap analysis.

| Task | Detail | Depends On |
|---|---|---|
| 2.9 Right-to-erasure schema design | Ensure all user data is deletable in a single cascade. No orphaned records. No hard identity dependencies in scoring logic. | 2.1 |
| 2.10 Item-level persistence for partial sessions | Each item response saved individually with timestamp. Enables resume-from-last-item on browser close. Flag incomplete instruments. | 2.1, 2.4 |
| 2.11 Test-retest interval enforcement | Routing engine checks last completion date per instrument. Blocks re-administration within the instrument's defined time window (e.g. PHQ-9 = 14 days, PBAT = 7 days). | 2.4, Phase 1 |
| 2.12 Longitudinal data model | Score deltas between sessions. Trend direction per instrument. Time-series query support. Enables repeat PBAT tracking and pre/post measurement. | 2.1, 2.2 |
| 2.13 Clinical intake packet export | PDF report structured per Section 16.3 (10-part clinical report). Therapist-facing format. Downloadable. | 2.2, Phase 1 (scoring), reports/ |

---

## 24. Updated Immediate Next Actions

Revised from Section 10, incorporating all gap analysis findings. Status updated after Phase 1 + Phase 2 completion.

| # | Action | Output | Status | Notes |
|---|---|---|---|---|
| 1 | Audit all 48 instruments against JSON schema | List of generic vs custom scorer split | **DONE** | Completed pre-Phase 1. 40 generic, 8 custom. |
| 2 | Finalise instrument definition JSON schema | Schema spec + phq9.json example | **DONE** | Schema locked. 16 definition tests passing. |
| 3 | Build BaseScorer + ScoreResult + GenericScorer | Core scoring abstractions | **DONE** | `scoring/base.py`, `scoring/generic.py`. |
| 4 | Build scorer registry | Dynamic registration/lookup | **DONE** | `scoring/registry.py`. Auto-discovers from definitions dir. |
| 5 | Write all instrument JSON definitions | ~40 generic JSON files | **IN PROGRESS** | Venus complete (6/48). Remaining 42 not started. |
| 6 | Build custom scorers | PBAT, VLQ, MSS-YSQ, PAQ, LSAS-SR, ECR-RS, MEQ, PSQI | **IN PROGRESS** | PAQ complete (1/8). 7 custom scorers not started. |
| 7 | Build composite index engine | z-standardisation, all 6 indices. | **NOT STARTED** | numpy needed. Blocking for full planet formulation. |
| 8 | Build routing engine (Venus) | Deterministic rules for Venus slice | **DONE** | `routing/engine.py`. PHQ-2→PHQ-9, GAD-2→GAD-7, PAQ-S→PAQ, safety_pause. Full routing engine (all planets) not started. |
| 9 | Build planet state calculator | Derived projection from completion state | **NOT STARTED** | Venus available instruments computation done as part of routing engine. Full planet state (LOCKED/AVAILABLE/SCANNED/DEEP_DIVE) not started. |
| 10 | Full test suite | pytest with known test vectors for all instruments | **IN PROGRESS** | 152/152 passing. Venus fully covered (definitions, scoring, routing, API). Remaining 42 instruments not started. |
| 11 | Database schema + SQLAlchemy models | Session, AssessmentInstance, Score. Cascade delete, longitudinal fields. | **DONE** | `models/models.py`, `db/database.py`. UUID PKs, JSON columns, designed for Postgres migration. |
| 12 | FastAPI app shell + assessment endpoints | Session management, assessment submission, safety protocol handler | **DONE** | `main.py`, `api/routes_session.py`, `api/routes_assessment.py`. Server-side carry-forward. 409 safety block. Acknowledge-safety endpoint. |
| 13 | Clinical intake packet export | PDF report via WeasyPrint. Therapist-facing format. | **NOT STARTED** | First post-formulation pathway. High priority after AI pipeline. |

### Remaining priority order (post-Phase 2)

| Priority | Action | Rationale |
|---|---|---|
| Next | Intake flow endpoints | Red-thread question, state anchors, PBAT, exclusion screen. Unblocks full session lifecycle. |
| Next | Remaining Venus JSON definitions complete (already done) — expand to Mercury | ISI, WEMWBS, MAIA-2 Brief, MEQ, PSQI definitions + custom scorers for MEQ + PSQI. |
| Later | Composite index engine | Needs numpy z-score norms. Blocked until ≥2 instruments per composite are scored. |
| Later | AI formulation experiments | Can start with hardcoded Venus scores in a notebook to de-risk prompt quality early. |
| Later | Auth (Google OAuth) | Phase 4. Not needed until multi-user / persistence across devices. |



---

## 25. Additional Instruments (from Gap Analysis)

The following instruments were identified as gaps in the battery and are added to the definitive instrument list.

### 25.1 ACEs (Adverse Childhood Experiences Questionnaire)

| Field | Detail |
|---|---|
| Items | 10 |
| Scale | Yes/No |
| Measures | Childhood abuse, neglect, and household dysfunction |
| Licence | Free (Felitti et al. 1998, CDC) |
| Planet | Earth (Core self) -- deep dive. **(LOCKED)** |
| Rationale | Everything else in the battery measures current state. Nothing asks how the user got here. ACEs scores predict adult depression, anxiety, ADHD severity, substance use, physical health, and attachment patterns. Provides the AI formulation with a narrative bridge between childhood experience and adult psychological patterns. One of the most predictive single instruments in psychological research. |
| Scoring | Sum of yes responses (0-10). No clinical cutoffs officially defined, but scores of 4+ are associated with significantly elevated risk across multiple health domains. |
| Integration | ACEs score contextualises MSS-YSQ schema activation (why certain schemas exist), ECR-S/ECR-RS attachment patterns, and PC-PTSD-5 trauma screening. The AI formulation should reference ACEs when explaining schema origins, but must do so with care -- framing as context, not determinism. |
| Sensitivity note | This instrument asks about abuse, neglect, and household dysfunction. It must be presented with appropriate framing, opt-in consent, and a clear "skip this" option. It should never be in the core flow -- always a deep dive that the user actively chooses. |

### 25.2 UCLA Loneliness Scale-3 (ULS-3) or De Jong Gierveld Scale

| Field | Detail |
|---|---|
| Items | UCLA-3: 20 items. De Jong Gierveld: 6 items (short) or 11 items (full). |
| Scale | UCLA: 1-4 Likert (Never to Always). De Jong: Yes/More or less/No. |
| Measures | Subjective social isolation and loneliness |
| Licence | Free |
| Planet | Saturn (Social and relational) -- deep dive |
| Rationale | LSAS measures social anxiety (fear and avoidance). Loneliness is a distinct construct. A person can be socially confident and profoundly lonely, or socially anxious yet feel deeply connected. Post-pandemic, subjective loneliness is one of the most clinically significant unmeasured variables in the adult population. |
| Recommendation | **(LOCKED)** Use De Jong Gierveld 6-item short form. It distinguishes emotional loneliness (absence of close attachment) from social loneliness (absence of broader social network), which maps directly to the ECR-S/ECR-RS attachment data. Saturn deep dive, alongside ECR-RS. |
| Integration | Cross-reference with ECR-S avoidance subscale and LSAS. High loneliness + low LSAS = lonely but not anxious (isolation pattern). High loneliness + high LSAS = anxious and isolated (compounding pattern). |

### 25.3 MEQ (Morningness-Eveningness Questionnaire)

| Field | Detail |
|---|---|
| Items | 19 |
| Scale | Multiple choice (varying response formats per item) |
| Measures | Chronotype -- biological preference for sleep/wake timing |
| Licence | Free (Horne and Ostberg 1976) |
| Planet | Mercury (Sleep, function, body) -- deep dive |
| Rationale | ISI measures insomnia severity but not when the person's biological clock wants them to sleep. Extreme eveningness (delayed sleep phase) is strongly associated with ADHD, depression, and mood instability, and is often misread as laziness or lack of motivation. This is a circadian pattern, not a character flaw. Particularly relevant for Helix's likely audience. |
| Integration | Cross-reference with ISI (insomnia + extreme eveningness = likely circadian mismatch, not primary insomnia) and ASRS (ADHD + eveningness is a well-documented pattern). The AI formulation should note: "Your sleep difficulties may partly reflect a mismatch between your biological clock and your schedule, rather than a primary sleep disorder." |
| Custom scorer | Yes -- MEQ uses a non-standard scoring system with different point values per item and a composite chronotype classification (definitely morning / moderately morning / intermediate / moderately evening / definitely evening). |

### 25.4 VIA-120 (Values in Action Character Strengths Inventory)

| Field | Detail |
|---|---|
| Items | 120 |
| Scale | 1-5 Likert (Very much like me to Very much unlike me) |
| Measures | 24 character strengths across 6 virtue categories |
| Licence | Free from viacharacter.org |
| Planet | Earth (Core self) -- extended deep dive |
| Rationale | The battery is almost entirely deficit-focused. SCS-SF and BRS are the only real strengths instruments. VIA-120 provides a ranked profile of 24 character strengths. This is not a soft addition -- strengths profiles predict therapeutic outcomes, resilience, and values alignment in ways that deficit measures cannot. It gives the formulation something affirmative to say, which matters for engagement and for not leaving users feeling they are a collection of problems. |
| Integration | Cross-reference with VLQ (do the user's top strengths align with their valued domains?) and with MSS-YSQ (do strengths buffer against active schemas?). The Protective Resources composite could incorporate top-5 strength scores. |
| Note | **(LOCKED)** Two-tier implementation: VIA-IS-P (24 items, 1 per strength) as Earth quick scan for strengths. VIA-120 (120 items) as extended deep dive, offered as a standalone optional session -- not inline with other deep dives. User opt-in only, never auto-triggered. VIA-120 is longer than the entire quick scan battery combined and must be positioned as a dedicated session. |

### 25.5 Updated Planet Mappings (with new instruments)

| Planet | Quick Scan | Deep Dive (updated) |
|---|---|---|
| Mercury (Sleep, function, body) | ISI (7) | + WEMWBS (14) + Brief MAIA-2 (24) + MEQ (19) + PSQI (19) + FFMQ-15 (15) |
| Venus (Mood, emotion, awareness) | PHQ-2 + GAD-2 + PAQ-S (10) | PHQ-9 + GAD-7 + DERS-16 + PAQ (24) + PSS-10 (10) + DTS (15) + ERQ (10) |
| Earth (Core self) | BFI-S (15) + **VIA-IS-P (24)** | IPIP-50 + SCS-SF + BRS + RSES + **ACEs (10)** + **VIA-120 (120, standalone session)** |
| Mars (Attention and drive) | ASRS Part A (6) | ASRS Full + BDEFS-SF + CFQ-25 (25) |
| Jupiter (Values, motivation, meaning) | VLQ (10 domains) | + AAQ-II + CompACT (23) + MLQ (10) + SWLS (5) |
| Saturn (Social and relational) | LSAS-SR short (~12) | LSAS-SR full + ECR-S + ECR-RS (36) + **De Jong Gierveld (6)** |
| Uranus (Neurodivergence) | AQ-10 (10, conditional) | + CAT-Q + RAADS-R (80, standalone) |
| Neptune (Deep patterns) | IUS-12 (12) | + MSS-YSQ (76) + PTQ-10 + CPQ (12) + DSS-B (10) + PSWQ (16) + OCI-R (18) |

### 25.6 Updated Battery Statistics

| Metric | Previous | Updated |
|---|---|---|
| Total instruments (incl. short forms) | 31 | 37 (+ ACEs, De Jong Gierveld, MEQ, VIA-IS-P, VIA-120) |
| Custom scorers needed | 7 | 8 (+ MEQ) |
| Quick scan items | ~118 | ~142 (+ VIA-IS-P 24 on Earth) |
| Full battery items (all deep dives) | ~571 | **~1,063 (see Section 31.5 for definitive count)** |
| Free / public domain instruments | 19 | 24 |

### 25.7 Updated Interlinkage Map Additions

| Link | Instruments | Clinical Significance |
|---|---|---|
| Developmental history x Schemas | ACEs x MSS-YSQ | Childhood adversity explains schema origins |
| Developmental history x Attachment | ACEs x ECR-S/ECR-RS | Early disruption predicts attachment patterns |
| Developmental history x Trauma | ACEs x PC-PTSD-5 | Childhood adversity contextualises trauma screen |
| Loneliness x Social anxiety | De Jong Gierveld x LSAS | Distinguishes lonely-but-confident from anxious-and-isolated |
| Loneliness x Attachment | De Jong Gierveld x ECR-S | Emotional loneliness maps to attachment avoidance |
| Chronotype x Sleep | MEQ x ISI | Circadian mismatch vs primary insomnia |
| Chronotype x ADHD | MEQ x ASRS | Eveningness compounds ADHD presentation |
| Chronotype x Depression | MEQ x PHQ-9 | Eveningness associated with mood instability |
| Strengths x Values | VIA-120 x VLQ | Do top strengths align with valued domains? |
| Strengths x Schemas | VIA-120 x MSS-YSQ | Do strengths buffer against active schemas? |
| Strengths x Resilience | VIA-120 x BRS + SCS-SF | Strengths enrich the Protective Resources composite |

---

## 26. Trust Framework (Pre-Launch)

Before showing Helix to any second user, these four questions must have clear, visible answers in the product.

### 26.1 "Is this safe for someone who is very unwell?"

**Answer to design into the product:**
Helix includes safety screening (PC-PTSD-5, PHQ-9 item 9) that pauses the assessment and provides crisis resources if risk indicators are detected. However, Helix is not a crisis intervention tool. The persistent disclaimer states: "Helix is a self-exploration tool. It is not a clinical assessment, does not produce diagnoses, and is not a substitute for professional mental health support." Safety pauses cannot be bypassed. Crisis resources are UK-specific (Samaritans 116 123, 999). For users in acute distress, Helix should actively recommend professional support rather than continuing assessment.

### 26.2 "Can I use this instead of therapy?"

**Answer to design into the product:**
No. Helix helps you understand patterns in how you think, feel, and relate. It does not treat anything. The formulation is a structured map, not a treatment plan. If Helix surfaces patterns that concern you, the most valuable next step is to bring your Helix report to a qualified therapist -- it will give them a head start. The "therapist export" feature (clinical intake packet PDF) is designed for exactly this purpose.

### 26.3 "Who made this and are they qualified?"

**Answer to design into the product:**
Helix was built by [your name/team]. The assessment battery uses validated psychological instruments developed by clinical researchers. The scoring is entirely deterministic -- no AI involvement in calculating scores. The AI only narrates and synthesises pre-scored results. The theoretical framework is Process-Based Therapy (Hayes and Hofmann, 2018). Every instrument, scoring rule, and interpretive threshold is documented and traceable to its published source. An "About the science" page should list every instrument with its citation and validation status.

### 26.4 "What happens to my data?"

**Answer to design into the product:**
Your assessment data is stored securely and is never shared with third parties. You can delete all your data at any time (right to erasure). Your data is never used to train AI models. Detailed data policy to be defined post-MVP but the architecture supports full deletion from day one (cascading delete design in Phase 2 schema).


---

## 27. Adversarial Review Resolutions

All 14 items from the adversarial review have been assessed and accepted. Critical changes have been applied inline to Sections 1, 3, 5, 7, 8, 14, and 17. This section documents the full resolution details and remaining implementation notes.

### Item 1 — VIA-IS-P Licensing Contingency

VIA-IS-P carries identical licensing risk to VIA-120. Contingency instruments confirmed:
- **GACS-24** (General Assessment of Character Strengths, 24 items, free) — Earth quick scan replacement
- **GACS-72** (72 items, free) — VIA-120 standalone session replacement
- GACS has lower clinician recognition than VIA but is psychometrically sound
- Build with VIA instruments. Swap if permission denied. No architecture changes required.

### Item 2 — Quick Scan Time Budget (APPLIED)

Changes applied to Sections 14.2 and 14.3:
- Neptune removed from default quick scan (conditional only)
- SDS moved to core flow
- Readiness Rulers cut (Item 7)
- Session 1 design: core flow then 2-3 planets only

Revised default quick scan: ~129 items (excluding Neptune's 10). Target Session 1 time: ~20-25 minutes.

### Item 3 — Composite Indices Mean Z (APPLIED)

Full revision applied to Section 7. Key changes:
- Sum of z-scores replaced with mean of z-scores
- required_core and required_minimum fields added per composite
- Partial composites labelled "n of N components"
- composites.json added to definitions directory (versioned)

### Item 4 — Instrument Definition Versioning

**Schema changes for Phase 2:**
- Add `instrument_version: string` to AssessmentInstance table. Populated at instance creation from instrument JSON version field.
- Add `index_id: string` and `index_version: string` to Score table (for composite scores).
- Add norms table:

```
norms:
  id: UUID
  target_type: "instrument" | "composite"
  target_id: string
  version: string
  population: string
  mean: float
  sd: float
  source_citation: string
```

- When a definition is updated, bump version. New instances use new version. Old instances retain original version.
- Cache invalidation (Item 10) must also fire when composites.json is updated.

### Item 5 — Red-Thread Guardrails (APPLIED)

Two-step intake design applied to Section 14.3. New intake fields for Phase 2 schema:
- `red_thread_question_raw: string`
- `red_thread_question_normalized: string`
- `red_thread_quality: enum ("good", "low", "empty")`
- `red_thread_risk_flag: bool`
- `red_thread_risk_reason: string | null`
- `red_thread_categories: array of up to 5 category strings`
- `red_thread_top3_ranked: array of up to 3 category strings | null`

AI context fields added to Section 8.2. System prompt rules added to Section 8.1.

### Item 6 — ACEs UX Framing

ACEs requires dedicated UX handling (sensitive_content flag added to JSON schema in Section 5):

**Opt-in screen (before first item):**
> "This section asks about experiences from your childhood. Some people find these questions difficult. You can skip this section at any time -- it won't affect your exploration elsewhere."
> Buttons: "I'm ready" / "Skip for now" (stores aces_status: "deferred")

**During administration:**
- Persistent "Pause this section" button on every ACEs item screen
- Partial responses preserved. Not scored until all 10 items complete.

**Post-completion check-in:**
> "Thank you for completing that section. Take a moment if you need one."
> Buttons: "Continue exploring" / "Take a break" (returns to solar system)

**Auto-deferral rules:**
- If PC-PTSD-5 >= 3 or red_thread_risk_flag is true: ACEs automatically deferred
- Only accessible after SAFETY_ACKNOWLEDGED state and explicit Earth deep dive navigation

**Display rule:** ACEs raw score (0-10) is never shown to the user. AI references as "your early life experiences" only. Raw score appears in clinician-facing report only.

### Item 7 — Readiness Rulers Cut (APPLIED)

Cut from v1. Redundant with VLQ gap, AAQ-II, CompACT valued action. Removed from:
- Section 14.2 Jupiter deep dive
- Repository structure (readiness.py removed)
- Custom scorer count reduced from 8 to 7

Jupiter deep dive is now: VLQ -> AAQ-II -> CompACT -> MLQ -> SWLS. v2 candidate.

### Item 8 — Session State Anchor Longitudinal Model

**Delta computation:** On GET /sessions/{id}/state, compute current minus previous session anchors for mood, energy, focus.

**Two-tier flag system:**

| Drop | Flag | AI action |
|---|---|---|
| Any single anchor drops >= 4 points | notable_drop | AI acknowledges before proceeding |
| Any single anchor drops >= 6 points, or all three drop >= 3 | significant_deterioration | AI leads with check-in before any narration |

**Schema additions:**
- StateAnchors table must have session_id FK for time-series
- Add `anchor_flag: string | null` to Session table

Context block fields added to Section 8.2 (anchor_delta, anchor_flag). System prompt rule added to Section 8.1.

### Item 9 — Saturn SPIN Contingency

Pre-commercial concern only. Build with LSAS-SR as planned.

**Contingency:** SPIN (Social Phobia Inventory, 17 items, free, Connor et al. 1999, Duke University). Replaces LSAS-SR short as Saturn quick scan if licence fails. Generic scorer compatible (sum, three subscales: fear, avoidance, physiological). LSAS-SR full may remain as deep dive on separate licence negotiation.

### Item 10 — Planet State Caching (APPLIED)

Memoisation note added to Section 1.1 locked decisions. Implementation:

**Schema additions:**
- `planet_states_cache: JSON | null` on Session table
- `planet_states_cache_valid_at: timestamp | null` on Session table

**Logic:**
- Cache is null on creation
- Populated on first GET /sessions/{id}/state
- Invalidated (set to null) on every POST /assessments/{id}/submit and on composites.json version update
- State endpoint: return cache if non-null, otherwise compute, store, return

### Item 11 — jsPsych Crash and Partial Handling

**Three-layer fix:**

Layer 1 — localStorage autosave (client-side):
- After every 10 trials, write current trial array to localStorage
- On page load: check for saved data, offer "Resume" or "Restart"

Layer 2 — POST retry with exponential backoff:
- 3 retries (1s, 2s, 4s) on failed POST
- Final retry failure: retain in localStorage for manual recovery
- Successful POST: clear localStorage

Layer 3 — partial_complete flag (server-side):
- Endpoint accepts `partial_complete: bool` and `trial_count: int`
- trial_count >= min_trials_for_scoring: score normally
- trial_count >= 50% of min_trials_for_scoring: score with reliability caveat
- trial_count < 50%: store raw data, do not score, mark INCOMPLETE

`min_trials_for_scoring` field added to JSON schema (Section 5).

### Item 12 — Formulation Sparse-Data Handling (APPLIED)

Theme state rules added to Section 8.1 system prompt.

**Three-state theme model:**
- **RICH** (>= 2 instruments for theme): synthesise fully
- **PARTIAL** (1 instrument): synthesise with explicit uncertainty, name what's missing
- **SPARSE** (0 instruments): one sentence, name planet to visit, do not speculate

**Guard rule:** If sparse_count > 2, FormulationEngine returns INSUFFICIENT_DATA rather than generating a hollow formulation.

**Revised FORMULATION_AVAILABLE condition (Section 15):** >= 3 planets with quick scan complete AND sparse_count <= 2 across the 5 formulation themes.

`theme_states` field added to Section 8.2 context block.

### Item 13 — Trust Framework UX Placement

Section 26 trust answers annotated with placements:

**Landing page:**
- One-paragraph purpose statement
- Three trust statements: "Free to explore / Not a diagnosis / Your data stays yours"
- Link to full privacy policy

**Onboarding screen (after sign-in, before intake):**
- Three points: not a clinical service / data stored securely / delete anytime
- Checkbox: "I understand this is not a substitute for professional support" (required)

**Settings page (/settings):**
- "Download my data" (JSON export)
- "Delete my account and all data" (cascade delete)
- "What we store" (plain language inventory)
- Privacy policy link

### Item 14 — Debug Endpoints

**Five debug-only endpoints** (gated by DEBUG_MODE=true, returns 404 in production):

```
GET /debug/sessions/{id}              — Full session dump
GET /debug/sessions/{id}/composite/{index_id}  — Composite diagnostic
GET /debug/sessions/{id}/routing      — Routing history
GET /debug/sessions/{id}/prompt       — Exact LLM prompt assembly
GET /debug/instruments/{id}/score-test?test_vector=[...]  — Score test without pytest
```

routes_debug.py added to repository structure (Section 3). Primary tool for Phase 3 prompt quality testing.

---

## 28. Updated Open Questions (Post-Adversarial Review)

| Question | Status | Notes |
|---|---|---|
| Solar system renderer | OPEN | Phase 5. Prototype before committing. |
| z-score reference norms | PARTIALLY RESOLVED | Norms table added (Item 4). Population norms to be sourced per instrument. |
| Deployment target | OPEN | Phase 4+. |
| VIA-IS-P licensing | OPEN | Same risk as VIA-120. Contingency: GACS-24/72. |
| Saturn licensing | OPEN | Contingency: SPIN (17 items). Pre-commercial only. |
| Readiness Rulers | RESOLVED — CUT | v2 candidate. |
| Session anchor longitudinal | RESOLVED | Delta computation + two-tier flags (Item 8). |
| PBAT | RESOLVED | Section 11. |
| Instrument versioning | RESOLVED | norms table + version tracking (Item 4). |

---

## 29. Revised Custom Scorer Count (SUPERSEDED — see Section 31.4)

With Readiness Rulers cut (Item 7), the custom scorer list is:

| # | Instrument | Reason |
|---|---|---|
| 1 | PBAT | Formative scale, item-profile output |
| 2 | VLQ | Gap scoring (importance - consistency) |
| 3 | MSS-YSQ | 19 schemas, 6 unmet needs clusters |
| 4 | PAQ | 5 subscales, valence-specific (positive + negative) |
| 5 | LSAS-SR | Paired fear + avoidance ratings per item |
| 6 | ECR-RS | Multi-target (4 relationship structures) |
| 7 | MEQ | Non-standard per-item weighting, chronotype classification |

**Total: 7 custom scorers. ~30 generic scorers.**


---

## 30. Psychometric Validation Report Integration

This section documents changes arising from the Helix Psychometric Test Battery validation report (deep research audit) and subsequent cross-review by Gemini and Perplexity.

### 30.1 Composite Scoring Methodology — Clarifications

**Mean-z variance note (LOCKED):**
When averaging k correlated z-scores (r < 1), the composite variance is (1 + (k-1) * mean_r) / k, which is less than 1. The composite SD shrinks below 1.0. This is mathematically expected and acceptable for Helix's purposes.

Composite scores are **not re-standardised** after mean-z computation. Re-standardising would require a population distribution of the composite itself, which does not exist for platform-derived indices and would reintroduce within-sample norm dependency.

**Interpretive guardrail (LOCKED):** Composite scores must never be interpreted against absolute SD thresholds. They are used for within-person ring display and relative change tracking only. The "platform-derived and exploratory" label applies to all composites without exception.

**PBAT exemption (confirmed):** PBAT is explicitly exempt from composite z-standardisation. It is a formative scale scored idiographically. Within-person item-level profiling is the primary output. PBAT does not contribute to any composite index.

### 30.2 SDS Replaced by WSAS

**Decision: LOCKED.** The Sheehan Disability Scale (3 items) is replaced by the Work and Social Adjustment Scale (5 items) throughout the battery.

| Attribute | SDS | WSAS |
|---|---|---|
| Items | 3 | 5 |
| Domains | Work, social, family | Work, home management, social leisure, private leisure, relationships |
| Sensitivity to change | Moderate | High — IAPT treatment-change standard |
| UK clinical recognition | Lower | Higher — NHS IAPT mandated |
| Licence | Rights check needed | Public domain |

WSAS replaces SDS in the core flow (administered universally as functional impairment baseline after session state anchors). All references to SDS in Sections 14.3, 17.3, 19, and 25 are superseded by WSAS.

### 30.3 New Instruments Accepted from Validation Report

The following instruments are added to the battery based on the validation report. All are deep dive instruments unless otherwise noted.

#### 30.3.1 PSWQ (Penn State Worry Questionnaire)

| Field | Detail |
|---|---|
| Items | 16 |
| Scale | 1-5 Likert |
| Measures | Pathological worry — excessiveness and uncontrollability |
| Licence | Free for clinical/research |
| Planet | Uranus (Neurodivergence) — deep dive |
| Rationale | GAD-7 measures anxiety severity. PSWQ measures the worry process specifically — a maintaining factor that drives anxiety. Distinct construct. Gold-standard worry measure. |
| Interlinkage | GAD-7 x PSWQ: elevated GAD-7 + high PSWQ = worry-driven anxiety. GAD-7 elevated + PSWQ low = somatic/physiological anxiety. |

#### 30.3.2 PCL-5 (PTSD Checklist for DSM-5)

| Field | Detail |
|---|---|
| Items | 20 |
| Scale | 0-4 Likert |
| Measures | 20 DSM-5 PTSD symptoms (intrusion, avoidance, negative cognitions/mood, arousal/reactivity) |
| Licence | Public domain (VA/NCPTSD) |
| Planet | Asteroid belt — deep dive (unlocks only if PC-PTSD-5 >= 3) |
| Rationale | PC-PTSD-5 is a 5-item screen. PCL-5 provides comprehensive dimensional PTSD assessment. Essential for users who screen positive on trauma. |
| Routing | Auto-unlocked when PC-PTSD-5 >= 3 AND user has acknowledged safety protocol. Never available before safety acknowledgment. |
| Cutoff | 31-33 for probable PTSD. Internal consistency alpha = 0.94-0.95. |
| IES-R excluded | IES-R (22 items) measures similar constructs (intrusion, avoidance, hyperarousal). Redundant with PCL-5. PCL-5 preferred because it maps directly to DSM-5 criteria. |

#### 30.3.3 PSS-10 (Perceived Stress Scale)

| Field | Detail |
|---|---|
| Items | 10 |
| Scale | 0-4 Likert |
| Measures | Perceived unpredictability, uncontrollability, and overload in life |
| Licence | Free |
| Planet | Venus (Mood, emotion) — deep dive |
| Rationale | Perceived stress is distinct from anxiety (GAD-7) and depression (PHQ-9). A user with high PSS-10 but low GAD-7 has situational overload, not clinical anxiety. |
| Interlinkage | PSS-10 x GAD-7: stress vs anxiety distinction. PSS-10 x ISI: stress-driven sleep disruption. PSS-10 x DERS-16: stress amplifies dysregulation. |

#### 30.3.4 OCI-R (Obsessive-Compulsive Inventory — Revised)

| Field | Detail |
|---|---|
| Items | 18 |
| Scale | 0-4 Likert |
| Measures | OCD severity across 6 dimensions: washing, checking, ordering, obsessing, hoarding, neutralising |
| Licence | Free for research/clinical |
| Planet | Uranus (Neurodivergence) — deep dive |
| Rationale | OCD is a genuine gap in the current battery. OCD symptoms interact with anxiety (GAD-7), perfectionism (CPQ), and intolerance of uncertainty (IUS-12). Currently invisible. |
| Interlinkage | OCI-R x IUS-12: uncertainty intolerance drives checking/obsessing. OCI-R x CPQ: perfectionism drives ordering. OCI-R x GAD-7: co-occurring anxiety. |

#### 30.3.5 RAADS-R (Ritvo Autism Asperger Diagnostic Scale — Revised)

| Field | Detail |
|---|---|
| Items | 80 |
| Scale | 0-3 Likert |
| Measures | Comprehensive autism traits: language, social relatedness, sensory-motor, circumscribed interests |
| Licence | Free for clinical use |
| Planet | Uranus (Neurodivergence) — extended deep dive |
| Rationale | AQ-10 is a brief screen. CAT-Q measures masking only. RAADS-R provides comprehensive dimensional autism assessment equivalent to clinical screening. 80 items — standalone session recommended. |
| Routing | Available when AQ-10 >= 6 OR user opt-in from Uranus. Standalone session (not inline with other deep dives). |
| Cutoffs (UPDATED) | Original cutoff of 65 is deprecated (81% false positive rate in general mental health populations). Updated thresholds: >= 106 = traits consistent with autism. >= 140 = pronounced autism traits. |

#### 30.3.6 CFQ-25 (Cognitive Failures Questionnaire)

| Field | Detail |
|---|---|
| Items | 25 |
| Scale | 0-4 Likert |
| Measures | Frequency of everyday cognitive mistakes (perception, memory, motor) |
| Licence | Public domain |
| Planet | Mars (Attention and drive) — deep dive |
| Rationale | ASRS measures ADHD symptoms. BDEFS-SF measures executive function in daily life. CFQ measures subjective everyday cognitive slips — a different angle. Useful for distinguishing ADHD-related attention problems from general cognitive load. |
| Interlinkage | CFQ x ASRS: ADHD-specific vs general cognitive failures. CFQ x ISI: sleep deprivation compounds cognitive errors. CFQ x PSS-10: stress-driven cognitive failures. |

#### 30.3.7 DTS (Distress Tolerance Scale)

| Field | Detail |
|---|---|
| Items | 15 |
| Scale | 1-5 Likert |
| Measures | Perceived capacity to withstand negative emotional states |
| Licence | Free |
| Planet | Venus (Mood, emotion) — deep dive |
| Rationale | Distinct from emotion regulation (DERS-16 measures regulation capacity) and alexithymia (PAQ measures emotional identification). DTS measures tolerance — can the person sit with distress without acting on it? Transdiagnostic variable across mood disorders. |
| Interlinkage | DTS x DERS-16: low tolerance + poor regulation = high crisis risk. DTS x AAQ-II: low tolerance drives experiential avoidance. |

#### 30.3.8 ERQ (Emotion Regulation Questionnaire)

| Field | Detail |
|---|---|
| Items | 10 |
| Scale | 1-7 Likert |
| Measures | Two regulation strategies: cognitive reappraisal and expressive suppression |
| Licence | Free |
| Planet | Venus (Mood, emotion) — deep dive |
| Rationale | DERS-16 measures dysregulation (the deficit). ERQ measures specific strategies the person actually uses. A user high on DERS-16 who primarily uses suppression (ERQ) has a clear intervention target. Complementary, not redundant. |

#### 30.3.9 SWLS (Satisfaction with Life Scale)

| Field | Detail |
|---|---|
| Items | 5 |
| Scale | 1-7 Likert |
| Measures | Global cognitive life satisfaction |
| Licence | Free |
| Planet | Jupiter (Values, motivation, meaning) — deep dive |
| Rationale | MLQ measures meaning (presence + search). SWLS measures satisfaction — a related but distinct construct. Someone can find meaning in hardship (high MLQ presence) while being dissatisfied with life (low SWLS). 5 items, minimal burden. |

### 30.4 Instruments Excluded from Validation Report

| Instrument | Reason for exclusion |
|---|---|
| IES-R (22 items) | Redundant with PCL-5. Both measure trauma responses. PCL-5 maps to DSM-5 criteria and is preferred. |
| PSQI (19 items) | Significant overlap with ISI. PSQI adds sleep quality components but at 19 items is heavy. ISI + MEQ covers insomnia severity + chronotype. PSQI is a v2 candidate. |
| FFMQ (39 items) | Mindfulness is a meaningful construct but 39 items is excessive. Brief FFMQ (15 items) is a v2 candidate. |
| PERMA Profiler (23 items) | Overlaps substantially with WEMWBS (wellbeing), MLQ (meaning), VIA (accomplishment/engagement). Redundant. |
| CBF-PI-15 | Redundant with BFI-S already in battery. |
| BFI-10 | Redundant with BFI-S already in battery. Ultra-short version adds nothing. |

### 30.5 Updated Planet Mappings (Post-Validation)

| Planet | Quick Scan | Deep Dive (updated) |
|---|---|---|
| Mercury (Sleep, function, body) | ISI (7) | + WEMWBS (14) + Brief MAIA-2 (24) + MEQ (19) |
| Venus (Mood, emotion, awareness) | PHQ-2 + GAD-2 + PAQ-S (10) | PHQ-9 + GAD-7 + DERS-16 + PAQ (24) + **PSS-10 (10)** + **DTS (15)** + **ERQ (10)** |
| Earth (Core self) | BFI-S (15) + VIA-IS-P (24) | IPIP-50 + SCS-SF + BRS + RSES + ACEs (10) + VIA-120 (standalone) |
| Mars (Attention and drive) | ASRS Part A (6) | ASRS Full + BDEFS-SF + **CFQ-25 (25)** |
| Jupiter (Values, motivation, meaning) | VLQ (10 domains) | AAQ-II + CompACT (23) + MLQ (10) + **SWLS (5)** |
| Saturn (Social and relational) | LSAS-SR short (~12) | LSAS-SR full + ECR-S + ECR-RS (36) + De Jong Gierveld (6) |
| Uranus (Neurodivergence) | AQ-10 (10, conditional) | CAT-Q + **RAADS-R (80, standalone)** |
| Neptune (Deep patterns) | IUS-12 (12) | MSS-YSQ (76) + PTQ-10 + CPQ (12) + DSS-B (10) + **PSWQ (16)** + **OCI-R (18)** |
| Asteroid belt (safety) | PC-PTSD-5 (5, core flow) | **PCL-5 (20, unlocks on PC-PTSD-5 >= 3)** |

### 30.6 Core Flow Update

WSAS (5 items) replaces SDS (3 items) in the core flow. Updated core flow sequence:

1. Intake (two-step red-thread)
2. PBAT Section 1 (18 items)
3. Session state anchors (3 items)
4. WSAS (5 items — functional impairment baseline)
5. PC-PTSD-5 (5 items — pre-exploration screen)
6. AI recommends 2-3 planets

Core flow total: ~34 items.

### 30.7 Updated Battery Statistics (Post-Validation)

| Metric | Previous | Updated |
|---|---|---|
| Total instruments | 37 | 46 (+ WSAS, PSWQ, PCL-5, PSS-10, OCI-R, RAADS-R, CFQ-25, DTS, ERQ, SWLS; - SDS) |
| Quick scan items (default) | ~135 | ~137 (WSAS 5 replaces SDS 3 in core flow = +2 net) |
| Full battery items | ~750 | ~1,063 (+ PSWQ 16 + PCL-5 20 + PSS-10 10 + OCI-R 18 + RAADS-R 80 + CFQ-25 25 + DTS 15 + ERQ 10 + SWLS 5 + PSQI 19 + FFMQ-15 15 - SDS 3 + WSAS 5 + CompACT 23 vs old 10 = +13) |
| Custom scorers | 7 | 7 (no new custom scorers needed — all new instruments are generic sum/mean) |
| Free / public domain | 24 | 33 |

### 30.8 New Interlinkages

| Link | Instruments | Clinical Significance |
|---|---|---|
| Worry vs anxiety | GAD-7 x PSWQ | High GAD-7 + high PSWQ = worry-driven anxiety. High GAD-7 + low PSWQ = somatic/physiological anxiety. |
| Trauma depth | PC-PTSD-5 x PCL-5 | Screen positive -> dimensional PTSD assessment |
| Stress vs anxiety | PSS-10 x GAD-7 | Perceived overload vs clinical anxiety disorder |
| Stress x sleep | PSS-10 x ISI | Stress-driven insomnia pattern |
| Stress x cognition | PSS-10 x CFQ-25 | Cognitive failures under stress load |
| OCD x uncertainty | OCI-R x IUS-12 | Uncertainty intolerance drives obsessive checking |
| OCD x perfectionism | OCI-R x CPQ | Perfectionism drives ordering/arranging |
| Distress tolerance x avoidance | DTS x AAQ-II | Low tolerance drives experiential avoidance |
| Distress tolerance x regulation | DTS x DERS-16 | Low tolerance + poor regulation = high crisis risk |
| Regulation strategies x dysregulation | ERQ x DERS-16 | Suppression strategy + high dysregulation = clear intervention target |
| ADHD x cognitive failures | ASRS x CFQ-25 | ADHD-specific vs general cognitive slips |
| Life satisfaction x meaning | SWLS x MLQ | Satisfied but meaningless vs meaningful but unsatisfied |
| Autism comprehensive x masking | RAADS-R x CAT-Q | Full trait profile + masking depth |
| Autism x social anxiety | RAADS-R x LSAS-SR | Social avoidance: autistic trait vs anxiety |


---

## 31. Final Instrument Additions and Battery Freeze

### 31.1 PSQI (Pittsburgh Sleep Quality Index) — Added

| Field | Detail |
|---|---|
| Items | 19 |
| Scale | Mixed (0-3 Likert, time entries, yes/no) |
| Measures | Sleep quality across 7 components: subjective quality, latency, duration, efficiency, disturbances, medication use, daytime dysfunction |
| Licence | Free for clinical/research |
| Planet | Mercury (Sleep, function, body) -- deep dive |
| Rationale | ISI measures insomnia severity. PSQI measures sleep quality broadly. A user without clinical insomnia but with poor sleep quality (irregular schedule, unrefreshing sleep, frequent disturbances) will score low on ISI but elevated on PSQI. This distinction matters for formulation. |
| Custom scorer | Yes -- PSQI has a non-standard scoring system (7 component scores derived from 19 items via specific algorithms, global score 0-21). Adds to custom scorer count. |
| Interlinkage | PSQI x ISI: insomnia severity vs overall sleep quality. PSQI x MEQ: chronotype mismatch compounds poor sleep quality. PSQI x PHQ-9: sleep disruption maintaining depression. PSQI x ASRS: sleep quality impacts ADHD presentation. |

### 31.2 FFMQ-15 (Five Facet Mindfulness Questionnaire -- Short Form) — Added

| Field | Detail |
|---|---|
| Items | 15 |
| Scale | 1-5 Likert |
| Measures | Five mindfulness facets: observing, describing, acting with awareness, non-judging, non-reactivity |
| Licence | Free |
| Planet | Mercury (Sleep, function, body) -- deep dive (body-mind awareness cluster alongside Brief MAIA-2) |
| Rationale | Mindfulness is a core PBT process. Excluding it from a PBT-based platform is a genuine gap. FFMQ-15 covers all five facets in 15 items. Cross-links with PBAT attention items, DERS-16 awareness, Brief MAIA-2 interoception, and PAQ emotional awareness. |
| Interlinkage | FFMQ-15 x DERS-16: mindfulness facets contextualise regulation capacity. FFMQ-15 x Brief MAIA-2: mindful attention to body vs interoceptive awareness. FFMQ-15 x PAQ: non-judging facet interacts with alexithymia. FFMQ-15 x PBAT: direct PBT process alignment. |

### 31.3 Updated Mercury Deep Dive

Mercury now has the richest deep dive for body-mind assessment:

| Tier | Instrument | Items |
|---|---|---|
| Quick scan | ISI | 7 |
| Deep dive | WEMWBS | 14 |
| Deep dive | Brief MAIA-2 | 24 |
| Deep dive | MEQ | 19 |
| Deep dive | PSQI | 19 |
| Deep dive | FFMQ-15 | 15 |
| **Mercury total (all tiers)** | | **98** |

### 31.4 Updated Custom Scorer Count

PSQI requires a custom scorer (non-standard component derivation). Total custom scorers: **8**.

| # | Instrument | Reason |
|---|---|---|
| 1 | PBAT | Formative scale, item-profile output |
| 2 | VLQ | Gap scoring (importance - consistency) |
| 3 | MSS-YSQ | 19 schemas, 6 unmet needs clusters |
| 4 | PAQ | 5 subscales, valence-specific |
| 5 | LSAS-SR | Paired fear + avoidance ratings |
| 6 | ECR-RS | Multi-target (4 relationships) |
| 7 | MEQ | Non-standard per-item weighting, chronotype classification |
| 8 | PSQI | 7 component scores derived via specific algorithms |

### 31.5 Final Battery Statistics

| Metric | Count |
|---|---|
| Total instruments (including short forms) | 48 |
| Quick scan items (default, excluding conditional Neptune) | ~137 |
| Core flow items (intake + PBAT + anchors + WSAS + PC-PTSD-5) | ~34 |
| Full battery items (all deep dives + standalone sessions) | ~1,063 |
| Custom scorers | 8 |
| Generic scorers | ~40 |
| Free / public domain | 35 |
| Licence required | 10 |
| Hard to licence | 3 (LSAS-SR, CAT-Q, BDEFS-SF) |
| Standalone sessions (extended) | 2 (VIA-120, RAADS-R) |

---

## 32. Battery Freeze

**The instrument battery is now FROZEN at 48 instruments.**

No further instruments will be added to v1. The coverage is comprehensive across all six PBT process domains, all eight planets, safety screening, developmental history, neurodivergence, cognitive tasks, and strengths. Additional instruments (PSQI full, FFMQ-39, PERMA, IES-R) are documented as v2 candidates in Section 30.4.

Any proposal to add a new instrument must demonstrate that it fills a gap not covered by existing instruments AND that it does not create construct redundancy with instruments already in the battery.

**The next action is to start building.** Phase 1, Task 1.0: audit all 48 instruments against the JSON schema. Then begin writing definitions.

---

## 33. Reality Check — Build Priorities

### What to build first (vertical slice) — ✓ COMPLETE

Venus (Mood, emotion, awareness) was the first planet built because:
- PHQ-2 -> PHQ-9 expansion exercises the carry-forward pattern
- GAD-2 -> GAD-7 exercises a second carry-forward
- PAQ-S -> PAQ exercises a third carry-forward
- Safety protocol fires on PHQ-9 item 9
- Venus feeds the Distress Index composite
- Multiple deep dive instruments test the depth-tier architecture

**Vertical slice delivered:** JSON definitions for 10 Venus instruments (PHQ-2, PHQ-9, GAD-2, GAD-7, PAQ-S, PAQ, DERS-16, PSS-10, DTS, ERQ) -> GenericScorer + PAQ custom scorer -> SQLite schema -> FastAPI endpoints that accept responses, persist scores, route expansions, and enforce safety protocol. 169 tests passing. API runnable with `uvicorn helix.main:app --reload` from `backend/`. Frontend (basic HTML form / result display) deferred to Phase 5.

This proves the entire architecture works before investing in the remaining 38 instruments.

### What to de-risk early

**AI formulation quality:** As soon as scored JSON exists from the Venus vertical slice, start experimenting with formulation prompts. Use hardcoded test data in a notebook. Try different models. The formulation is the highest-risk component.

### Hard deadlines (suggested)

| Milestone | Target |
|---|---|
| Venus vertical slice (definitions + scoring + API + basic UI) | 3 weeks |
| All 48 instrument definitions written | 6 weeks |
| Full scoring engine with test coverage | 8 weeks |
| Database schema + API complete | 10 weeks |
| First AI formulation experiments | Week 4 (parallel with instrument definitions) |


---

## 34. Neptune / Uranus Swap (Applied)

**Decision: LOCKED.** Planet assignments for Uranus and Neptune have been swapped throughout the document.

| Planet | Previous Assignment | New Assignment | Rationale |
|---|---|---|---|
| Uranus | Deep patterns | **Neurodivergence** | Uranus's mythological association with the unconventional, the revolutionary, the different. "Your brain works differently" is Uranian. Avoids the "most distant = most alien" problem. |
| Neptune | Neurodivergence | **Deep patterns and hidden depths** | Neptune's association with the deep sea, the hidden, the unconscious. Schemas, perfectionism, worry, OCD, dissociation — hidden patterns operating below conscious awareness — are Neptunian. |

Uranus (Neurodivergence) remains LOCKED by default, conditional on intake intent, ASRS routing, or user opt-in.

### Complete Planet Order (final)

| # | Planet | Domain | Mythological Fit |
|---|---|---|---|
| -- | Sun | Red-thread question / central life theme | Centre, source of light, everything orbits around it |
| 1 | Mercury | Sleep, function, body, interoception, mindfulness | Closest to self: the physical substrate. Restlessness maps to sleep disruption. |
| 2 | Venus | Mood, emotion, awareness, stress, distress tolerance | Goddess of emotion, passion, feeling. Strongest mythological fit. |
| 3 | Earth | Core self, personality, strengths, self-esteem, ACEs | Home, ground, identity. Where you live. |
| 4 | Mars | Attention, drive, executive function, cognitive failures | God of action, drive, energy. ADHD as dysregulated drive. |
| -- | Asteroid belt | Safety / trauma (PC-PTSD-5, PCL-5) | Between action and purpose — trauma disrupts the connection. |
| 5 | Jupiter | Values, motivation, meaning, life satisfaction, flexibility | King of gods: purpose, big picture, what matters. Largest planet for largest questions. |
| 6 | Saturn | Social, relational, attachment, loneliness | Boundaries, structure, rings as relationship patterns. |
| 7 | Uranus | Neurodivergence (AQ-10, CAT-Q, RAADS-R) | The unconventional, the different, the revolutionary. Conditional/locked by default. |
| 8 | Neptune | Deep patterns (IUS-12, MSS-YSQ, OCI-R, PSWQ, CPQ, DSS-B) | Deep sea, hidden depths, what lies beneath conscious awareness. |
| -- | Kuiper belt | Cognitive tasks (Layer 5, jsPsych) | Outermost ring — furthest from subjective self-report core. |

---

## 35. Concept Enhancements (Phase 3)

These enhancements are Phase 3 concerns that build on top of the Phase 1-2 foundation. They require no architectural changes to the scoring engine, data layer, or instrument definitions.

### 35.1 Red-Thread Revisitation (User-Initiated)

The red-thread question should be revisitable by the user, not reframeable by the AI.

**Design:**
- After every 3-4 instruments completed, the system checks whether the user has explored domains significantly different from their original red-thread focus.
- If yes, a soft prompt appears: "You've explored several new areas since you started. Would you like to update your central question?"
- The user can update, keep the original, or dismiss.
- Red-thread history is stored: original question + any user-initiated updates with timestamps.
- The AI adapts narration to the current red-thread but never proposes a replacement.

**Boundary:** The AI does NOT suggest what the user's "real" question is. It does not reframe. Suggesting a reframe is dangerously close to clinical reformulation, which requires therapeutic rapport and professional judgment. The user retains full ownership of their question.

**Implementation:** Prompt task type added to Section 8.3. New fields: `red_thread_history: array` on User/Session model.

### 35.2 Cross-Planet Narrative Arcs

The most interesting clinical insights live between planets — in the interactions. The formulation engine should generate 2-3 cross-planet arc narratives alongside the 5-theme formulation.

**Design:**
- After formulation themes are generated, the FormulationEngine evaluates the interlinkage map (Section 18) against the user's actual scores.
- It identifies the 2-3 strongest cross-planet interlinkages where both instruments have been completed and the scores suggest a meaningful interaction.
- For each, it generates a short narrative arc connecting the two planets.

**Example output:**
"There's a pattern connecting Saturn and Venus in your data. Your attachment style shows avoidant tendencies — you tend to pull back when relationships get close. But your emotion regulation shows you actually feel things intensely. This combination — feeling deeply but withdrawing from connection — often begins as self-protection and becomes self-isolation over time."

**Boundary:** Arcs describe patterns, not causes. They connect data points with "this combination is often associated with..." language, not "this means you..." language. Same epistemic boundary as the main formulation.

**Implementation:** New FormulationEngine method: `generate_arcs(session_scores, interlinkage_map) -> list[ArcNarrative]`. AI prompt task type: "cross-planet arc" added to Section 8.3. Maximum 3 arcs per formulation to avoid overwhelming the user.

### 35.3 User Annotations on Formulation

Users can annotate the formulation — but the AI does NOT incorporate annotations into subsequent formulation generation.

**Design:**
- After reading a formulation theme or arc, the user can tap to annotate:
  - "This resonates" (quick reaction)
  - "This doesn't fit" (quick reaction)
  - Free-text response (optional)
- Annotations are stored per-theme, per-arc, linked to the formulation version.
- Annotations are visible to the user in their formulation history.
- Annotations appear in the clinician-facing report as "User reflections."

**Critical boundary:** The formulation engine always generates formulations purely from scored instrument data. User annotations are a parallel layer — the user's own meaning-making alongside the data-driven synthesis. If annotations were fed back into the AI, users with incorrect self-theories would steer the formulation toward confirming their beliefs, reinforcing potentially harmful narratives.

**Implementation:** New data model: `FormulationAnnotation(formulation_id, theme_id, reaction, free_text, timestamp)`. Frontend: annotation UI on formulation display (Phase 5).

### 35.4 "So What" Layer — Pattern Implications

An optional sixth layer in the formulation that bridges from pattern description to practical implication.

**Design:**
- After the 5 themes are generated, the FormulationEngine generates a brief "What this might mean in daily life" section.
- Uses descriptive language only: "People with this pattern often experience..." or "This combination frequently shows up as..."
- Never prescriptive: never "you should..." or "try doing..."
- Always ends with: "If any of this feels relevant, a conversation with a professional could help you explore it further."

**Boundary (LOCKED):** This layer describes how patterns typically manifest in daily life. It does not suggest interventions, treatments, or coping strategies. It does not predict outcomes or trajectory. The word "should" never appears in this layer.

**Implementation:** Additional prompt task type in Section 8.3. System prompt rule: "The 'so what' layer describes how patterns typically manifest. Use 'people with this combination often find that...' framing. Never prescribe. Never predict."

### 35.5 "Watch Yourself Change" — Longitudinal Positioning

The product's long-term value proposition is not "understand yourself once" but "watch yourself change over time."

**Current support:** PBAT repeat-administration, session-to-session score tracking, longitudinal data model (Section 23), state anchor deltas (Item 8).

**What this requires for v1:**
- Clear re-engagement prompt: "It's been [N weeks] since your last visit. Your map may have shifted. Want to check in?" (notification, email, or in-app)
- Change summary on return: "Since your last session, here's what's moved..." with per-planet direction indicators
- PBAT comparison: current item profile vs previous, highlighting areas of change

**What this does NOT require for v1:**
- Predictive trajectory ("your depression will worsen") — explicitly excluded (clinical prognosis)
- Automated intervention suggestions based on change patterns
- Complex time-series visualization (v2)

**Positioning note:** Frame Helix in all copy as an evolving map, not a snapshot. "Build your map. Return to see how it evolves." This is aspirational until the retention mechanism (re-engagement prompt) is built, but the data architecture supports it from day one.

---

## 36. Document Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | April 2026 | Initial implementation state document. 24 sections. |
| 2.0 | April 2026 | Adversarial review (14 items), validation report integration, battery freeze at 48 instruments, Neptune/Uranus swap, concept enhancements. 36 sections, ~2,000 lines. |


---

## 37. AASPIRE / REALS Research Integration (April 2026)

### 37.1 PHQ-9 Item 9 — Neurodivergent Non-Invariance (ARCHITECTURE CHANGE)

**Evidence:** PHQ-9 item 9 (suicidality) is non-invariant between autistic and non-autistic adults. Autistic adults endorse item 9 at different rates due to passive ideation, philosophical thinking about death, or literal interpretation — not acute risk. (Psychometric evaluation of the PHQ-9 and GAD-7 in autistic adults, *Autism*, 2024.)

**Previous behaviour:** Item 9 > 0 triggers SAFETY_PROTOCOL unconditionally (Section 1.1 locked decision).

**Updated behaviour (LOCKED):**

When a user has Uranus (Neurodivergence) status of AVAILABLE or higher (via intake intent, ASRS routing, or opt-in), AND PHQ-9 item 9 is endorsed (score > 0), a clarification screen appears:

> "You indicated you've had thoughts about being better off dead or hurting yourself. Sometimes people interpret this question in different ways. Are these thoughts something that feels urgent or frightening to you right now?"
> - **"Yes, this feels urgent"** -> full SAFETY_PROTOCOL fires as normal (pause, crisis resources, no resume until acknowledged)
> - **"No, these are passing or philosophical thoughts"** -> soft safety response: crisis resources displayed as information ("these are always available to you") but user may continue. `item9_clarified_passive: true` stored on AssessmentInstance. AI context receives flag.

**For all users without Uranus activation:** Item 9 > 0 continues to trigger full SAFETY_PROTOCOL unconditionally. Conservative default preserved.

**Safety rationale for soft response rather than full suppression:** A genuinely at-risk user who selects "passing thoughts" due to minimisation or alexithymia must still see crisis resources. The soft response ensures resources are always visible while removing the disruptive pause that causes autistic users to abandon the platform.

**Schema addition:** `item9_clarified_passive: bool | null` on AssessmentInstance (PHQ-9 instances only).

**AI system prompt addition:** "If `item9_clarified_passive` is true, acknowledge the user's responses with care but do not treat as an acute safety signal. Do not minimise. Do not escalate. Note that autistic adults often experience passive ideation differently. Frame as worth exploring with a professional."

**PHQ-9 scoring:** Unchanged. Raw score includes item 9 regardless of clarification response.

### 37.2 GAD-7 — No Change Required (CONFIRMED)

GAD-7 is fully measurement-invariant between autistic and non-autistic adults. No swap, no adaptation, no conditional variant needed. Same 2024 study confirms identical construct measurement across populations.

### 37.3 Accessible Instrument Presentation (LOCKED)

When a user's Uranus (Neurodivergence) status reaches SCANNED or higher, OR when the user selected "I think I might be neurodivergent" at intake, an accessibility-adapted display mode activates.

**What changes:**
- Framing text simplified (instructions around items, not item text)
- Scale labels clarified
- Idioms in instructions replaced with plain equivalents
- AI narration adjusts to plainer language throughout the session

**What does NOT change:**
- Validated item text (verbatim, locked per Section 14.5)
- Scoring rules, bands, thresholds
- Instrument JSON definitions
- Psychometric comparability with normative data

**Implementation:**
- Add `accessibility_mode: bool` to Session table (default: false)
- Set to `true` when: Uranus reaches SCANNED, OR intake intent = "I think I might be neurodivergent"
- Frontend reads flag and adjusts framing render
- AI context block receives `accessibility_mode: true`
- No new JSON definitions required

**Affected instruments (accessibility framing adjustments):** PHQ-9, GAD-7, LSAS-SR, and any other instruments where framing text uses idioms, ambiguous temporal language, or assumes neurotypical social reference points. Exact framing adaptations to be specified during Phase 5 frontend implementation.

### 37.4 V2 Candidate: AASPIRE Autistic Burnout Measure

| Field | Detail |
|---|---|
| Items | 27 |
| Scale | Sum scoring |
| Reliability | omega = 0.98 (n=379 autistic adults) |
| Measures | Autistic burnout: exhaustion and loss of functioning from cumulative masking/navigating non-autistic world |
| Licence | Free (AASPIRE open-access) |
| Planet | Uranus (Neurodivergence) -- deep dive, after CAT-Q |
| Routing | CAT-Q total > threshold OR user opt-in after CAT-Q narration |
| Custom scorer | No -- GenericScorer compatible |
| Gap filled | No current instrument measures autistic burnout. PHQ-9 + CAT-Q + RAADS-R can suggest it, but cannot confirm or quantify. |
| Priority | High |
| Reference | Bougoure et al. (2025), *Autism*. |

**Key interlinkage:** High burnout + high masking (CAT-Q) + high depression (PHQ-9) suggests autistic burnout as primary driver rather than primary depressive disorder. This distinction has significant treatment implications.

### 37.5 V2 Candidate: REALS Measures (University of Pittsburgh)

REALS (Relationships, Employment, Autonomy, and Life Satisfaction) is a PROMIS-methodology suite validated on 875 autistic adults and adults with developmental disabilities. It fills three gaps not covered by any v1 instrument:

1. Employment *satisfaction* (not impairment) -- WSAS measures how much work is impaired, REALS measures how satisfying work actually is
2. Community/social *participation* -- frequency + satisfaction, not just loneliness or anxiety
3. Functional *autonomy* -- self-care, home management, leisure, finances, mobility. WSAS covers impairment; REALS covers capacity.

| Scale | Items | Planet | Tier | Routing | Priority |
|---|---|---|---|---|---|
| REALS Work Satisfaction | ~5 | Jupiter | Deep dive | VLQ work domain importance >= 7 | High |
| REALS Social Activity | ~6 | Saturn | Deep dive | Alongside De Jong Gierveld | High |
| REALS Autonomy | ~11 | Mercury or Earth | Deep dive | User opt-in | Medium |
| REALS Life Satisfaction | ~5 | Jupiter | Deep dive | Complements SWLS | Medium |

All GenericScorer compatible. Licence: published open-access (*Autism Research*, Wiley, 2025). Confirm non-commercial licence with REAACT lab before v2 deployment.

Reference: REAACT lab, University of Pittsburgh. DOI: 10.1002/aur.70002.

### 37.6 V2 Interlinkage Additions

| Pair | Signal |
|---|---|
| CAT-Q x AASPIRE Burnout | Masking load predicts burnout severity |
| AASPIRE Burnout x PHQ-9 | Distinguish autistic burnout from primary depression |
| AASPIRE Burnout x WEMWBS | Burnout depletes wellbeing independently of mood |
| REALS Work Satisfaction x VLQ work domain | Values/reality gap quantified for employment |
| REALS Social Satisfaction x De Jong Gierveld | Activity satisfaction vs subjective loneliness |
| REALS Autonomy x WSAS | Functional capacity vs impairment -- different axes |
| REALS Life Satisfaction x SWLS | Domain-specific vs global satisfaction |

### 37.7 AASPIRE General Note

AASPIRE is a research evaluation toolkit for measuring service outcomes in autistic populations. It is not a competitor to Helix. The toolkit's primary contributions to Helix are: (1) methodological validation that most standard instruments work for autistic adults, (2) the PHQ-9 item 9 non-invariance finding, (3) accessible instrument design principles, and (4) the Autistic Burnout Measure as a v2 candidate.

AASPIRE domains Helix already covers: anxiety, depression, suicidality, emotional wellbeing, quality of life, activities of daily living, self-determination, social support.

AASPIRE domains outside Helix scope: healthcare service satisfaction, communication access, disability service satisfaction. These are system-level outcomes, not individual psychological processes.
