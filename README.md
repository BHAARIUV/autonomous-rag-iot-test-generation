# Autonomous RAG-Based IoT Test Generation and Fault Detection Framework

Final-year project. An AI-powered framework that:
takes an IoT device spec → extracts requirements → retrieves relevant
testing knowledge via RAG → generates structured test cases with an LLM →
validates and executes them against a simulated IoT device → injects
faults → measures coverage/fault-detection → finds testing gaps →
**autonomously generates and re-executes additional tests to close those
gaps** → shows the before/after improvement on a dashboard.

Initial target device: a simulated Temperature Sensor over MQTT.

> **Status: Phase 15 — React Frontend (COMPLETE).** The project is
> final and verified. Phase 15 adds a professional React/Vite presentation
> frontend (`frontend/`) that renders the real backend project data. Phase 13 wired Phases 5-12 into one
> spec, extracts requirements (Phase 5), retrieves testing knowledge via RAG (Phase 6),
> generates validated, traceable `TestCase` objects (Phase 7), executes them
> safely against the simulated sensor (Phase 8), measures coverage and
> fault-detection (Phase 9), binds the whole chain into one evidence-backed
> **final project report** with end-to-end traceability (Phase 10),
> **autonomously closes testing gaps** (Phase 11), presents the whole project in
> a **read-only dashboard** (Phase 12), and finally wires Phases 5-12 into one
> typed, deterministic **end-to-end orchestration** (Phase 13)
> (`python -m app.integration.demo`): Specification → ingestion → RAG →
> generation/validation → execution → fault analysis → refinement → reporting →
> dashboard, each stage recorded with a real status and everything traceable to
> real requirement / test-case / execution / fault / report IDs. The chain runs
> fully in MOCK mode with no API key; every value is derived from real artifacts
> and nothing is fabricated (execution `ERROR`/`SKIPPED` propagate verbatim,
> fault detection is evidence-backed, and broker availability is probed honestly).
> Execution never runs generated code — every generated prose step
> is mapped through a fixed interpreter to a closed, whitelisted action set, and
> each result is a typed PASS / FAIL / ERROR / SKIPPED `ExecutionResult` with
> per-step evidence, a real sampling clock, real fault injection, and honest MQTT
> semantics (no broker reachable → honest SKIPPED, never a fake pass). Fault
> detection is always evidence-backed (a fault is DETECTED only when a test that
> injected it ended FAIL — never inferred), and the report's test counts come from
> a real `pytest` run. The default `LLM_PROVIDER=mock` keeps the whole chain
> transfer, and the report's test counts come from
> a real `pytest` run. The default `LLM_PROVIDER=mock` keeps the whole chain
> offline with no API key and no network; a real OpenAI provider is available via
> configuration but untested-by-design to avoid API spend.
>
> **Phase 14 (final):** the project was inspected in full, the complete test suite
> passes (**668 passed, 0 failed, 0 skipped**, in ~39s), genuine defects found
> during the final pass were fixed (a missing-constant `NameError` in the health
> check, an unguarded fault-spec index, and a no-op MQTT assertion), the final
> report and dashboard were regenerated and verified (dashboard serves `/dashboard.html`
> with HTTP 200 and all sections A-I; the report JSON round-trips through the
> Pydantic model and records a real 668-test count), and the README was finalized.
>
> **Phase 15 (final presentation layer):** a professional **React/Vite frontend**
> under `frontend/` was added and **connected to the Python backend over HTTP**.
> The backend dashboard server now also exposes a read-only JSON API
> (`GET /api/dashboard`, `GET /api/health`) with allow-listed CORS for the React
> dev server (`http://localhost:5173`). The frontend (`src/api.js`, base URL
> `VITE_API_BASE_URL`, default `http://127.0.0.1:8877`) fetches the real
> `DashboardData` view model directly from the backend and renders all ten
> dashboard sections (overview, phases, requirements, RAG/knowledge, generation,
> execution, faults, refinement, traceability, final status) with real values
> (668 tests passed / 0 failed) and proper unavailable-vs-zero handling; a
> bundled artifact remains as a non-fake fallback. Run backend
> `python -m app.dashboard --port 8877` (from `backend/`), then `npm install`,
> `npm run dev` / `npm run build` (from `frontend/`). Backend business logic is
> unchanged — **677 tests pass** (incl. 9 new API/CORS tests).

---

## Prerequisites (Windows)

1. **Python 3.11+** — https://python.org (check "Add to PATH" during install)
2. **Git** — https://git-scm.com
3. **Mosquitto MQTT broker** — https://mosquitto.org/download — **required from Phase 3 onward** (see setup below)
4. An LLM API key (OpenAI/Anthropic/etc.) — optional. The project runs in **mock mode** by default and needs no key; cross-chain tests (Phase 7) run fully offline using the mock provider plus the deterministic `local` embedding provider and a local ChromaDB store. Set `LLM_PROVIDER=openai` and adjust `LLM_API_KEY` only when you intentionally want real LLM calls.

## Mosquitto setup (required for Phase 3 integration tests)

1. Install Mosquitto from https://mosquitto.org/download (Windows installer). By default it installs to `C:\Program Files\mosquitto`.
2. Start it with anonymous access allowed on port 1883 (fine for local development):

   ```powershell
   cd "C:\Program Files\mosquitto"
   mosquitto -v
   ```

   Leave this window open — it's your local broker. You should see `Opening ipv4 listen socket on port 1883.`
3. Alternatively, if Mosquitto was installed as a Windows service, it may already be running — check with:

   ```powershell
   netstat -an | findstr 1883
   ```

   If you see `LISTENING` on port 1883, the broker is already up and you can skip step 2.

**If Mosquitto is not running**, the Phase 3 integration tests (`tests/integration/test_mqtt_communication.py`) will be **automatically skipped** with a clear reason — they will not fail and will not fake success. The unit tests (`tests/unit/`) never require a broker.

## Repository layout

The Python **backend** lives under `backend/`. It is a self-contained workspace:

```
├── backend/
│   ├── app/            # the Python package (import as `app.*`)
│   ├── tests/          # pytest suite (unit/ , integration/ , generated/)
│   ├── data/           # SQLite DB location (`data/framework.db`)
│   ├── knowledge_base/ # RAG corpus (documents/ + chroma/)
│   ├── reports/        # generated reports + dashboard HTML
│   ├── examples/       # sample IoT specification files
│   ├── requirements.txt
│   ├── .env.example
│   └── pytest.ini      # pythonpath=.  testpaths=tests
├── frontend/           # Phase 15 React/Vite frontend (dashboard_data.json + src/)
├── docs/               # (documentation)
├── scripts/            # (helper scripts)
├── README.md
├── .gitignore
└── run.py              # launcher that puts backend/ on the path
```

**Where to run commands**

- All `python -m app.*`, `pytest`, `.env`, and `requirements.txt` commands below are run **from the `backend/` directory**.
- `python run.py` is run **from the repository root** (it adds `backend/` to the Python path itself).
- The virtual environment `venv/` stays at the repository root (not inside `backend/`).

```powershell
cd backend
```

## Setup

```powershell
# 1. Create and activate a virtual environment (at the repository root)
cd ..
python -m venv venv
venv\Scripts\activate

# 2. Install dependencies (run from backend/)
cd backend
pip install -r requirements.txt

# 3. Create your local .env file (run from backend/)
copy .env.example .env
# (leave LLM_PROVIDER=mock for now — no API key needed yet)
```

## Run

```powershell
# From the repository root:
python run.py
```

### Expected output

A series of log lines confirming the environment, LLM mode (should say
`MOCK`), MQTT broker target, database URL, and refinement targets, ending
with a line confirming the Phase 1 skeleton works. A `backend/logs/framework.log`
file will also be created.

## Test

Run the full suite from the **`backend/`** directory (so `pytest.ini` is found
and `app` / `tests` resolve):

```powershell
cd backend
pytest -v
```

### Expected output

- **With Mosquitto running and RAG corpus present:** 668 tests pass
  (278 baseline through Phase 6 + 93 new Phase 7 LLM tests + 120 new Phase 8
  execution tests + 47 new Phase 9 analysis tests + 39 new Phase 10 reporting
  tests + 23 new Phase 11 refinement tests + 29 new Phase 12 dashboard tests
  + 39 new Phase 13 e2e integration tests, all in mock mode).
- **Without Mosquitto running:** the broker-dependent MQTT integration tests
  are SKIPPED (not failed) with a message telling you to start the broker.
  The RAG and LLM tests need no broker, no API key, and no network.

Run only unit tests (never needs a broker):
```powershell
pytest tests/unit -v
```

Run RAG tests only (offline, no broker):
```powershell
pytest tests/unit/test_rag_*.py tests/integration/test_rag_retrieval.py -q
```

Run Phase 7 LLM tests only (offline MOCK mode, no broker, no API key):
```powershell
pytest tests/unit/test_llm_*.py tests/integration/test_llm_generation.py -q
```

Run Phase 8 execution tests only:
```powershell
pytest tests/unit/test_execution_*.py tests/integration/test_execution_full_chain.py -q
pytest tests/integration/test_execution_mqtt.py -q   # self-skips if Mosquitto is down
```

Run the Phase 8 interactive demo (10 labeled scenarios, real simulator/broker):
```powershell
python -m app.testing.demo
```

Run the Phase 9 coverage & fault-analysis demo (reports requirement/category/interface coverage + gaps):
```powershell
python -m app.analysis.demo
```

Generate the Phase 10 final project report (runs the real pipeline, then runs
`pytest` to record the REAL suite totals, and writes both reports):
```powershell
python -m app.reporting.demo
# writes:
#   reports/final_report.json   (machine-readable, valid JSON)
#   reports/final_report.md     (human-readable)
```

Run the Phase 11 autonomous-refinement demo (starts with only REQ-001 covered,
then closes the REQ-002/003/004 gaps automatically and prints measured
before/after coverage, per-iteration deltas and the stop reason):
```powershell
python -m app.refinement.demo
```

Run the Phase 12 dashboard (serve read-only HTML over `http.server`), then open
`http://127.0.0.1:8000/dashboard.html`:
```powershell
python -m app.dashboard
# or headless (writes reports/dashboard.html + console summary):
python -m app.dashboard.demo
```

Run the Phase 13 end-to-end integration chain (Specification → ingestion →
RAG → generation/validation → execution → fault analysis → refinement →
reporting → dashboard) in MOCK mode — no API key required:
```powershell
python -m app.integration.demo
```

## Phase 15 — React Frontend

Phase 15 adds a **React/Vite presentation frontend** under `frontend/`, connected
to the real Python backend over HTTP: `GET /api/dashboard` and `GET /api/health`.
It renders the same typed `DashboardData` view model the existing HTML dashboard
uses (sections A–I). The frontend is READ-ONLY — it never fabricates values and
does not expose secrets.

### How the frontend obtains project data

The backend dashboard server (`python -m app.dashboard`) is now both the HTML
dashboard and a small read-only JSON API:

| Endpoint            | Purpose                                                        |
| ------------------- | -------------------------------------------------------------- |
| `GET /api/health`   | Backend status, mode, phase, pytest totals (no secrets)        |
| `GET /api/dashboard`| Full `DashboardData` (sections A–I) as JSON                    |
| `GET /dashboard.html`| Legacy read-only HTML dashboard (unchanged)                   |
| `GET /`             | Endpoint listing                                               |

CORS is allow-listed per origin (default `http://localhost:5173`, configurable via
`DASHBOARD_CORS_ORIGINS`); `OPTIONS` preflight is supported. No `*` origin.

**Frontend data flow** (`src/api.js` + `src/App.jsx`):

1. Primary: `fetchDashboard()` / `fetchHealth()` against the API base URL
   `VITE_API_BASE_URL`, which defaults to `http://127.0.0.1:8877`.
2. On failure the app shows a visible error panel with the exact backend
   command; it never hides the API error.
3. `src/data.js` also keeps `fetchDashboardData()` (API first) with a non-fake
   fallback to the bundled real artifact `public/dashboard_data.json`, surfacing
   the API failure as a `warning` instead of hiding it.

Generate/refresh the optional bundled artifact from the **`backend/`** directory:
```powershell
python -m app.dashboard.dump
# writes backend/reports/dashboard_data.json
Copy-Item backend\reports\dashboard_data.json frontend\public\dashboard_data.json
```

### End-to-end run (two servers)

```powershell
# Terminal 1 — backend API + dashboard (from the repo `backend/` directory)
python -m app.dashboard --port 8877
#   -> GET http://127.0.0.1:8877/api/health
#   -> GET http://127.0.0.1:8877/api/dashboard

# Terminal 2 — React dev server (from the `frontend/` directory)
cd frontend
npm install          # install React + Vite (minimal dependencies)
npm run dev          # -> http://localhost:5173/
npm run build        # production build into frontend/dist/
npm run preview      # optionally serve the built site (use --port 4173)
```

`VITE_API_BASE_URL` is read from `frontend/.env`
(`frontend/.env.example` documents it). No API keys or secrets live in the
frontend.

### Frontend layout

```
frontend/
├── index.html                 # Vite entry (loads /src/main.jsx)
├── package.json / vite.config.js
├── .env.example               # VITE_API_BASE_URL (copy to .env to override)
├── public/dashboard_data.json # optional bundled real-data artifact (fallback)
└── src/
    ├── main.jsx               # React entry point (mounts <App/>)
    ├── App.jsx                # shell: sidebar nav + 10 sections, API fetch + states
    ├── api.js                 # centralized API client (VITE_API_BASE_URL, /api/*)
    ├── data.js                # helpers + unavailable-vs-zero handling + fallback loader
    ├── index.css              # Tailwind CSS
    └── components/
        ├── ui.jsx             # reusable primitives (Badge, Metric, Section, DataTable)
        └── Sections.jsx       # the ten dashboard section views
```

The ten sections map 1:1 to the backend dashboard: Project Overview, Phase 1–15
status, Requirements, RAG/Knowledge, Test Generation, Test Execution, Fault
Analysis, Refinement, Traceability, and Overall Project Status (including the
real **668 passed / 0 failed** pytest result reported by the backend).

## Verification checklist (Phase 3)

- [ ] `pip install -r requirements.txt` completes with no errors (now includes `paho-mqtt`)
- [ ] `.env` created from `.env.example`
- [ ] `python run.py` prints the startup banner and exits cleanly (no traceback)
- [ ] Mosquitto is running on `localhost:1883` (`mosquitto -v` in its own window)
- [ ] `pytest -v` shows all tests passing (broker-dependent MQTT tests auto-skip if Mosquitto is not running)
- [ ] Manually confirm pub/sub: in one terminal, `mosquitto_sub -t "iot/sensor/temperature" -v`; in another, run the interactive publisher snippet below — you should see JSON messages appear in the subscriber terminal

```powershell
python -c "
from app.iot.simulator import TemperatureSensorSimulator
from app.iot.mqtt_client import MqttConnection
from app.iot.mqtt_publisher import SensorMqttPublisher
conn = MqttConnection(client_id='manual-test-publisher')
conn.connect()
pub = SensorMqttPublisher(TemperatureSensorSimulator(), conn, sensor_id='temp-sensor-01')
pub.publish_n_readings(5)
conn.disconnect()
"
```

## Verification checklist (Phase 6)

- [ ] `pip install -r requirements.txt` completes with no errors (now includes `chromadb==1.5.9`)
- [ ] RAG retrieval runs fully offline — no API key, no network:
      `pytest tests/unit/test_rag_*.py tests/integration/test_rag_retrieval.py -q` → all pass
- [ ] `knowledge_base/documents/` ships with `manifest.json` + 12 `.md` topic documents,
      each carrying document_id, title, source, topic, version, document_type
- [ ] `python -c "from app.rag.service import index_knowledge_base; r = index_knowledge_base(); print(r)"`
      indexes the corpus into a local Chroma store under `knowledge_base/chroma/` and is idempotent on re-run
- [ ] `python -c "from app.ingestion.service import ingest_text; from app.rag.retriever import retrieve_for_requirement; reqs = ingest_text('Device: Temperature Sensor\nRange: -40 C to 125 C\n', source='x.txt').requirements; print([r.topic for r in retrieve_for_requirement(reqs[0], top_k=4)])"`
      prints relevant knowledge (`boundary_value_analysis`, `temperature_sensor_testing`, ...) for the range requirement

## Verification checklist (Phase 7)

- [ ] No new hard dependency — real LLM packages are NOT auto-installed; mock mode needs none
- [ ] Full chain runs offline in MOCK mode; `generation_mode == "mock"` asserted by tests
- [ ] Requirement → RAG → LLM → validated test cases, fully traceable:
      `pytest tests/unit/test_llm_*.py tests/integration/test_llm_generation.py -q` → all pass (93 tests)
- [ ] `python -c "from app.llm.service import generate_for_requirement; from app.ingestion.service import ingest_text; from app.rag.service import index_knowledge_base; p = index_knowledge_base(); r = next(x for x in ingest_text('Device: Temperature Sensor\nRange: -40 C to 125 C\n', source='x.txt').requirements if x.requirement_id == 'REQ-001'); s = generate_for_requirement(r, top_k=4); print(f\"generation_mode={s.generation_metadata.generation_mode}\"); [print(t.test_case_id, t.category.value, t.title, t.test_data.inputs) for t in s.test_cases]"`
      prints a mocked MOCK-mode suite (e.g. POSITIVE 42.5°C, BOUNDARY −40/125°C, NEGATIVE −40.1/125.1°C)
- [ ] Real LLM provider is wired but intentionally NOT exercised: switch with `LLM_PROVIDER=openai` + `LLM_API_KEY` in `.env` (documented, untested-by-design to avoid API spend)

## Verification checklist (Phase 8)

- [ ] `pytest tests/unit/test_execution_*.py -q` → all pass (111 tests)
- [ ] Full Phase 5 → 8 chain executes generated cases offline (no broker needed):
      `pytest tests/integration/test_execution_full_chain.py -q` → all pass; boundary −40/125 PASS,
      negative −40.1/125.1 PASS (device correctly rejects them), injected SENSOR_OUT_OF_RANGE → genuine FAIL
- [ ] Broker-gated MQTT execution: `pytest tests/integration/test_execution_mqtt.py -q`
      PASSes with Mosquitto up; SKIPPED (never faked) when the broker is down
- [ ] `python -m app.testing.demo` prints 10 labeled scenarios and an honest summary
      (8 passed / 1 failed / 1 error in the shipped seed)
- [ ] None of the executed actions ever runs generated code: every action is a
      typed member of the closed 13-action set (checked in tests)
- [ ] Honest MQTT semantics: with no reachable broker, MQTT test cases become
      SKIPPED by default (or ERROR with `on_mqtt_unavailable="error"`), never a fake PASS

## Verification checklist (Phase 10)

- [ ] `pytest tests/unit/test_reporting_*.py tests/integration/test_reporting_full_chain.py -q` → all pass (39 tests)
- [ ] `python -m app.reporting.demo` produces `reports/final_report.json` (valid JSON, `_schema = "autonomous-rag-iot-final-report/v1"`) and `reports/final_report.md`
- [ ] The report's final test totals match a real `pytest` run — never guessed
- [ ] Traceability links real ids end to end: requirement → test case → execution (execution_id) → fault (fault_type/fault_id) → coverage
- [ ] Fault detection is evidence-backed in the report: a fault is `DETECTED` only if a test that injected it ended FAIL; `MISSED`/`NOT_EXECUTED` otherwise — never inferred
- [ ] JSON report round-trips through the Pydantic model: `model_dump(mode="json")` is `json.dumps`-safe and reloadable

## Verification checklist (Phase 12)

- [ ] `pytest tests/unit/test_dashboard_models.py tests/unit/test_dashboard_service.py tests/integration/test_dashboard_smoke.py -q` → all pass (29 tests)
- [ ] `python -m app.dashboard.demo` writes `reports/dashboard.html` and prints a console summary with no fabricated numbers
- [ ] `python -m app.dashboard` serves the dashboard; opening `/dashboard.html` returns HTTP 200 with all sections A–I
- [ ] Dashboard values match real project data (report/report.json counts, coverage from the report, RAG manifest documents) — nothing hard-coded
- [ ] Missing data renders as "Not available" (never an invented number)
- [ ] Generation mode is always shown (MOCK vs REAL LLM), never hidden
- [ ] No API key/secret ever appears in the rendered output (only its presence, redacted)
- [ ] Fault detection is shown from evidence-backed states; no detection is inferred

## Verification checklist (Phase 13)

- [ ] `pytest tests/unit/test_integration_models.py tests/unit/test_integration_pipeline.py tests/integration/test_integration_e2e.py -q` → all pass (39 tests)
- [ ] `python -m app.integration.demo` runs the whole chain to completion in MOCK mode and prints per-stage status plus requirement traceability
- [ ] Every stage (ingestion, RAG, generation, validation, execution, fault analysis, refinement, reporting, dashboard) reports an explicit OK/FAIL status
- [ ] Requirement → RAG evidence → generated/validated tests → executed tests → fault(s) are all traceable to real IDs
- [ ] Execution `ERROR`/`SKIPPED` propagate verbatim (never promoted to PASS); totals are real
- [ ] Fault detection is evidence-backed: a declared fault is DETECTED only when a test that injected it ended FAIL
- [ ] Broker availability is probed honestly (unreachable broker ⇒ MQTT test SKIPPED, `broker_reachable=False`)
- [ ] MOCK vs REAL LLM provider mode is always explicit on the result
- [ ] The final report (Phase 10) and dashboard data (Phase 12) are available at the end of the chain
- [ ] Repeated MOCK runs are deterministic (same totals/coverage on re-run)

## Verification checklist (Phase 14 — final)

- [ ] `pytest -q` → **668 passed, 0 failed, 0 skipped** (final regression)
- [ ] All app modules import cleanly; `compileall app tests` has no errors
- [ ] Mosquitto broker reachable on `localhost:1883`; MQTT integration tests pass (no skips)
- [ ] Health check works: `python -m app.cli health` prints `MQTT reachable: True` (NameError fixed)
- [ ] `python -m app.integration.demo` runs the full MOCK chain to completion
      (INGESTION→RAG→GENERATION→VALIDATION→EXECUTION→FAULT_ANALYSIS→REFINEMENT→REPORTING→DASHBOARD) with traceable IDs & 100% evidence-backed fault detection
- [ ] `python -m app.reporting.demo` regenerates `reports/final_report.json` + `.md`
      with a real 668-test total; JSON round-trips through the Pydantic model
- [ ] `python -m app.dashboard.demo` regenerates `reports/dashboard.html`;
      `python -m app.dashboard --port 8877` serves `/dashboard.html` with HTTP 200 and all sections A–I
- [ ] Genuine defects found in the final pass were fixed with the smallest changes
      (no feature additions, no redesigns)
- [ ] Known limitations documented (stub `app/database`/`app/validation`, real-LLM path
      untested without an API key, Phase 10 report phase-status scopes to 10 dev phases)
- [ ] No temp/secret/junk files left in the repo; `requirements.txt` matches actual imports

## Verification checklist (Phase 15 — React frontend)

- [ ] Backend unchanged: `pytest -q` (from `backend/`) → **677 passed, 0 failed** (includes 9 new API/CORS tests, no regression)
- [ ] `python -m app.dashboard --port 8877` (from `backend/`) serves:
      `GET /api/health` → HTTP 200 (no secrets), `GET /api/dashboard` → HTTP 200
      (sections A–I), OPTIONS preflight with `Access-Control-Allow-Origin: http://localhost:5173`
- [ ] `python -m app.dashboard.dump` (from `backend/`) writes `reports/dashboard_data.json`
      that round-trips through the `DashboardData` Pydantic model (sections A–I, real values)
- [ ] The artifact is copied to `frontend/public/dashboard_data.json`
- [ ] `cd frontend && npm install` installs the minimal React/Vite deps only
- [ ] `npm run dev` starts the dev server; `http://localhost:5173/` loads the dashboard
      **from the real backend API** (`http://127.0.0.1:8877/api/dashboard` + `/api/health`),
      shows "Backend Online" / the connected API URL, and has no console or CORS errors
- [ ] `npm run build` produces `frontend/dist/`; `npm run preview` serves the built site
- [ ] All ten sections render (overview, phases, requirements, RAG/knowledge,
      generation, execution, faults, refinement, traceability, final status) incl. 668 passed / 0 failed
- [ ] README updated (status banner, Phase 15 section, phase list, structure tree, this checklist)

## Project structure

```
ai-test-automation-framework/
├── backend/
│   ├── app/
│   │   ├── main.py              # entry point (Phase 1: skeleton check only)
│   │   ├── config.py             # Settings loaded from .env
│   │   ├── logging_config.py      # shared loguru setup
│   │   ├── ingestion/             # IoT spec parsing + requirement extraction (Phase 5)
│   │   ├── rag/                   # RAG knowledge base: loader, chunker, embeddings, vector store, retriever (Phase 6)
│   │   ├── llm/                   # LLM test case generation: models, prompts, providers (mock + openai), parser, validation, service (Phase 7)
│   │   ├── validation/            # test case validation (Phase 7)
│   │   ├── iot/                   # sensor simulator + MQTT (Phase 2)
│   │   ├── faults/                # fault injection engine (Phase 3)
│   │   ├── testing/                # automated execution engine: actions, assertions, interpreter, executor, service, demo (Phase 8)
│   │   ├── analysis/                # coverage / fault detection / gaps (Phase 9)
│   │   ├── reporting/                # final project report + end-to-end traceability (Phase 10)
│   │   ├── refinement/                # autonomous test-refinement loop (Phase 11)
│   │   ├── database/                 # SQLite models + repository (unused; RAG uses its own Chroma store)
│   │   ├── dashboard/                 # read-only dashboard: models, provider, service, render, demo, server (Phase 12)
│   │   └── integration/               # e2e orchestration: models, pipeline, demo (Phase 13)
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── generated/                  # tests generated by the LLM land here
│   ├── knowledge_base/
│   │   ├── documents/                   # RAG knowledge corpus: manifest.json + 12 topic docs
│   │   └── chroma/                      # ChromaDB vector store (auto-created, git-ignored)
│   ├── data/                             # SQLite DB file lives here
│   ├── reports/                           # generated final reports
│   ├── examples/                           # sample IoT specification files
│   ├── logs/                               # rotating log files
│   ├── .env.example
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/                           # Phase 15 React/Vite frontend (src/, public/dashboard_data.json)
├── docs/                               # (documentation)
├── scripts/                            # (helper scripts)
├── README.md
├── .gitignore
└── run.py
```

## Phase 11 — Autonomous Refinement Loop

### Purpose
After Phases 5–9 have generated, executed and analysed the initial suite, gaps
remain (uncovered requirements, missing boundary/negative tests, generated-but-
unexecuted tests, etc.). Phase 11 **autonomously** closes those gaps: it feeds
the real Phase 9 analysis gaps back through RAG-aware generation, validation and
safe execution until a stop condition is reached, recording the measured
before/after coverage for every iteration.

### Algorithm (`app/refinement/service.py`, `RefinementService.run`)
```
working = initial tests + results
loop (max iterations):
    analysis = Phase 9 analyse(working)                 # real gaps + coverage
    gaps     = rank(analysis gaps + uncovered-requirements)
    if no gaps:                      stop NO_GAPS
    if coverage >= target:           stop TARGET_REACHED
    pick gap[0]; map to action:
        REGENERATE        -> generate/validate/execute NEW tests (requirement-aware RAG)
        EXECUTE_EXISTING  -> run a generated-but-unexecuted test
        NOT_ADDRESSABLE / SKIP_ENVIRONMENT -> record no-op (fault/MQTT gaps)
    re-analyse working; measure real improvement
    if 2 consecutive no-progress passes: stop NO_IMPROVEMENT
stop MAX_ITERATIONS otherwise
```

### Stop conditions (explicit, recorded on `RefinementResult.stop_reason`)
- `TARGET_REACHED` — requirement coverage >= `target_requirement_coverage`
- `MAX_ITERATIONS` — hit `max_refinement_iterations`
- `NO_IMPROVEMENT` — 2 consecutive passes with no improvement and no new work
- `NO_GAPS` — no remaining analysis gaps to act on
- (`VALIDATION_FAILURE` / `EXECUTION_ERROR` are reserved defensive stops)

### Honesty & safety
- Every selected gap, generated test id, executed result id and before/after
  coverage number comes from the real Phase 5–9 artifacts — nothing is fabricated.
- Only Phase 7-validated `TestCase` objects ever reach execution; execution reuses
  the safe Phase 8 closed action set (no `eval`/`exec`, no running generated code).
- Tests with identical content are de-duplicated (never added twice).

### Config (`.env` / `Settings`)
| Setting | Default | Meaning |
|---|---|---|
| `MAX_REFINEMENT_ITERATIONS` | `3` | max loop passes |
| `TARGET_REQUIREMENT_COVERAGE` | `90` | percentage target to stop at |
| `RAG_TOP_K` | `4` | RAG chunks used per regeneration |

### Commands
```powershell
python -m app.refinement.demo                 # interactive loop demo
pytest tests/unit/test_refinement_models.py tests/unit/test_refinement_service.py -q
pytest tests/integration/test_refinement_full_chain.py -q
```

### Limitations
- Fault-injection gaps (`FAULT_NO_TEST` / `FAULT_NOT_DETECTED`) are honestly marked
  `NOT_ADDRESSABLE` by the loop — it will not auto-generate a fault test (that
  would sit outside the safe action set). Such gaps are reported but not closed
  by regeneration.
- MQTT / interface runtime gaps are `SKIP_ENVIRONMENT` — they only close when a
  real runtime is present.
- Requirement coverage improvements are limited by what the RAG + mock LLM can
  meaningfully generate for each uncovered requirement.

## Dashboard

### Purpose
`app/dashboard/` is a **read-only** visualization and reporting layer. It makes
the whole project understandable at a glance:

```
Requirements → RAG → Test Generation → Validation → Execution
→ Fault Injection → Coverage → Refinement → Final Results
```

It consumes **real project data** — the Phase 10 final report
(`reports/final_report.json`), the RAG corpus manifest, real pytest counts, and
a real Phase 11 refinement result — and never fabricates numbers. Anything
unavailable is shown as **"Not available"**.

### Architecture
A small, dependency-free stack (stdlib + existing `pydantic` only — no browser
framework, no extra packages):

| File | Purpose |
|---|---|
| `app/dashboard/models.py` | typed view models for sections A–I (real-data-derived) |
| `app/dashboard/provider.py` | read-only data access: loads the report, reads the RAG corpus manifest, computes the Phase 11 refinement result in MOCK mode |
| `app/dashboard/service.py` | `DashboardService` folds provider data into the views |
| `app/dashboard/render.py` | stdlib HTML + plain-text renderers (pure functions) |
| `app/dashboard/demo.py` | writes `reports/dashboard.html` + prints a console summary |
| `app/dashboard/__main__.py` | serves the HTML over `http.server` |

**Read-only safety:** the dashboard never executes generated/arbitrary code,
never modifies requirements, test cases, execution results, fault results, or
the RAG database (it only reuses them). Refinement is only ever **computed on
demand in MOCK mode** for display — never persisted, and not triggered by
viewing other sections. API keys are never exposed: `RedactedConfig` reports
only *whether* a key exists.

### Installation
No new dependencies. The existing installed packages (pydantic, loguru, mqtt,
chromadb, pytest) are sufficient. Start Mosquitto so the live execution /
refinement sections reflect real broker behavior (see Mosquitto setup above).
If `reports/final_report.json` is absent, the dashboard builds one in-memory
from the mock pipeline automatically (nothing is written).

### Startup command
Serve the dashboard (builds on startup, then serves read-only):
```powershell
python -m app.dashboard
# -> http://127.0.0.1:8000/dashboard.html   (use --port 9000 to change the port)
```
Headless (write `reports/dashboard.html` + print a summary, no browser):
```powershell
python -m app.dashboard.demo
```

### Available sections
- **A. Project Overview** — status, current phase, completed phases, total
  requirements/tests, executed/passed/failed/errors/skipped, generation mode.
- **B. Requirements** — id, category, description, validation status, test
  count, and coverage status: **COVERED / PARTIALLY COVERED / UNCOVERED**.
- **C. RAG / Knowledge** — corpus documents, retrieved topics, and the real
  requirement → retrieved-knowledge mapping with retrieval counts (no invented
  semantic-quality metrics).
- **D. Test Generation** — every generated test with category, requirement,
  generation mode and validation status. **MOCK vs REAL LLM** is always shown.
- **E. Test Execution** — executed total, PASS/FAIL/ERROR/SKIPPED, execution
  coverage, and execution history.
- **F. Fault Analysis** — total/detected/missed faults, detection rate, fault
  type, related tests and evidence-backed detection (never inferred).
- **G. Refinement (Phase 11)** — iterations, gaps before/after, coverage
  before/after, improvement, tests per iteration, and the stop reason
  (computed on load in MOCK mode).
- **H. Traceability** — requirement → RAG evidence → test → validation →
  execution → faults → coverage using real ids.
- **I. Final Project Status** — Phase 1–13 status (all COMPLETE; Phase 14 is the
  final testing/documentation phase and completes the project),
  final test result, requirement/execution coverage, fault detection, remaining
  gaps, and known limitations.

### Mock vs real LLM behavior
- The dashboard runs entirely in **MOCK mode** by default (`LLM_PROVIDER=mock`):
  no API key, no network. It builds/reads all data offline.
- If a real provider is configured, the dashboard **labels** the generation mode
  as **REAL LLM** in every relevant section (it is never hidden). It still never
  surfaces the API key value — only its presence.

### Limitations
- Refinement/final-report data shown for the live dashboard is recomputed from
  the existing services (MOCK mode) rather than loaded from a saved snapshot,
  so those sections reflect the current mock loop on each load.
- The RAG knowledge view reports retrieval counts, not semantic quality metrics
  (those are not computed anywhere in the project).
- Fault "missed" counts are derived only from evidence-backed detection states;
  a fault never injected is shown as NOT_EXECUTED, never guessed as missed.

### Troubleshooting
- **Port already in use:** pass a free port, `python -m app.dashboard --port 9000`.
- **Refinement section shows "Not available":** the mock compute failed — check
  that Mosquitto is running (execution/sample tests need the broker) and that
  `knowledge_base/` is intact.
- **Dash is blank / "Not available" everywhere:** `reports/final_report.json`
  is missing or corrupt; the dashboard will fall back to a mock build, but
  regenerate it with `python -m app.reporting.demo` for the full traceability
  report.

## Phase 13 - End-to-End Integration

`app/integration/` wires the already-built Phase 5-12 services into one
deterministic, typed orchestration (`E2EPipeline.run`) that never duplicates
their business logic — it only drives them and records every stage. It is the
single entry point for the whole framework:

```
Specification
  └─► INGESTION      (Phase 5) requirements from a real spec text
  └─► RAG            (Phase 6) relevant knowledge chunks, read-only
  └─► GENERATION     (Phase 7) validated test cases via the mock/real LLM
  └─► VALIDATION     (Phase 7) embedded in generation; 0 rejected is real
  └─► EXECUTION      (Phase 8) safe executor + honest fault & MQTT evidence
  └─► FAULT_ANALYSIS (Phase 9) evidence-backed coverage / detection / gaps
  └─► REFINEMENT     (Phase 11) autonomously closes addressable gaps
  └─► REPORTING      (Phase 10) final project report + traceability
  └─► DASHBOARD      (Phase 12) confirm data availability (read-only)
```

Each stage returns an explicit `StageResult` (SUCCESS / SKIPPED / FAILED), so a
validation concern is always distinguishable from an execution concern, and the
whole run returns one `E2EResult` with per-requirement traceability (real
requirement → RAG-evidence → generated/validated → executed → fault IDs).

Honesty guarantees:
- Execution `ERROR`/`SKIPPED` propagate verbatim — never promoted to PASS.
- Faults are DETECTED only when a test that injected them ended FAIL.
- Broker availability is probed honestly (`broker_reachable`); unreachable
  broker ⇒ MQTT test SKIPPED, never faked.
- MOCK vs REAL LLM is always explicit; every number is derived from real
  artifacts, nothing fabricated; repeated MOCK runs are deterministic.

Files:

| File | Purpose |
|------|---------|
| `app/integration/models.py` | typed `E2EResult`, `StageResult`, `RequirementChainTrace`, `RefinementChainSummary`, enums |
| `app/integration/pipeline.py` | `E2EPipeline` — the deterministic orchestration of Phases 5-12 |
| `app/integration/demo.py` | `python -m app.integration.demo` — runs the full chain in MOCK mode and prints status + traceability |
| `app/integration/__init__.py` | public exports |

```powershell
python -m app.integration.demo
pytest tests/unit/test_integration_models.py tests/unit/test_integration_pipeline.py tests/integration/test_integration_e2e.py -q
```

**Known limitations:** the end-to-end chain uses the deterministic MOCK LLM and
the local embedding provider (no paid API key required); the REAL LLM/MQTT paths
are exercised only in MOCK/offline mode here and would need credentials and a
reachable broker to be verified for real.

## Phase 14 — Final Testing, Debugging & Documentation

Phase 14 focused on final verification, debugging, integration testing, and project documentation before completing the framework.

### Final Backend Verification

The complete backend test suite was executed to verify the functionality developed across Phases 1-14.

```text
668 tests passed


### Then immediately add Phase 15

```markdown
## Phase 15 — React Frontend

Phase 15 is the final presentation layer of the project. A professional React + Vite + Tailwind CSS frontend was developed to visualize the complete Autonomous RAG-Based IoT Test Generation & Fault Detection Framework.

### Frontend Architecture

```text
React + Vite + Tailwind CSS
            │
            │ REST API
            ▼
Python Backend
            │
            ├── /api/health
            └── /api/dashboard

## Development phases

This project is built incrementally. Current status:

- [x] Phase 1 — Project setup & skeleton
- [x] Phase 2 — IoT temperature sensor simulator
- [x] Phase 3 — MQTT communication layer
- [x] Phase 4 — Fault injection engine
- [x] Phase 5 — Requirement extraction
- [x] Phase 6 — RAG knowledge base & retrieval
- [x] Phase 7 — LLM test generation + validation
- [x] Phase 8 — Automated test execution
- [x] Phase 9 — Coverage & fault analysis
- [x] Phase 10 — Final reporting & traceability
- [x] Phase 11 — Autonomous refinement loop
- [x] Phase 12 — Dashboard
- [x] Phase 13 — End-to-end integration
- [x] Phase 14 — Final testing, debugging & documentation  (complete)
- [x] Phase 15 — React frontend  (**final phase, complete**)

Phase 15 is the **final** phase of the project and is complete: the backend is
unchanged (**668 tests pass**) and the React/Vite frontend renders the real
project data. See the **Phase 15 — React Frontend** section above for setup,
build, and data-flow details.
