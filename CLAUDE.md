# CLAUDE.md — KG Data Quality Demo

**Project:** Healthcare RCM Knowledge Graph Demo (xVector internal POC)  
**Stack:** Python 3.11 · Neo4j Community 5.x · Streamlit · pyvis  
**Working directory:** `C:/Users/kiri0/Claude2026/APP_xV Knowledge Graph DQ Demo`

---

## Read this before doing anything

1. Check which phase/step is currently in progress (see **Phase Status** below)
2. Read the relevant spec file(s) for that step (see **Spec Index** below)
3. Implement only what the current step requires — no skipping ahead
4. Run the step's validation before marking it complete
5. Mark the step checkbox in the plan file

---

## Spec index

| File | When to read |
|------|-------------|
| [specs/spec_01_ontology.md](specs/spec_01_ontology.md) | Before ANY Cypher query, before `loader.py`, `connection.py` |
| [specs/spec_02_data.md](specs/spec_02_data.md) | Before `generator.py`, `domains.py` |
| [specs/spec_03_scenarios.md](specs/spec_03_scenarios.md) | Before `flaw_injector.py`, `detection.py`, `detection_rules.yaml` |
| [specs/spec_04_app.md](specs/spec_04_app.md) | Before any `panel_*.py`, `main.py`, `styles.py` |
| [specs/spec_05_architecture.md](specs/spec_05_architecture.md) | Before any `src/` module, `requirements.txt`, `scripts/setup.py` |

## Plan index

| File | Content |
|------|---------|
| [plan/phase1_steps.md](plan/phase1_steps.md) | Data & graph foundation — 10 steps with validation scripts |
| [plan/phase2_steps.md](plan/phase2_steps.md) | Streamlit app — 10 steps with validation |
| [plan/phase3_steps.md](plan/phase3_steps.md) | Polish & demo readiness |
| [plan/smoke_test.md](plan/smoke_test.md) | 67-check end-to-end smoke test |

---

## Phase status

| Phase | Status | Gate |
|-------|--------|------|
| **Phase 1** — Data & Graph Foundation | **Implementation complete — gate pending** | Kiran approves in Neo4j Browser |
| **Phase 2** — Streamlit Application | **Implementation complete — gate pending** | Kiran walks 3-scenario demo |
| **Phase 3** — Polish & Demo Readiness | **In progress** (setup.py + README done; timing + should-priority features TBD) | Dry run passes smoke test |

**Current step:** `plan/phase3_steps.md` → Step P3-1 (timing validation, all 6 scenarios)

---

## Implementation rules (do not deviate)

1. **Read the spec before implementing.** Never implement a module from memory — always open the relevant spec file first.
2. **Implement one step at a time.** Do not combine steps or implement ahead of the current step.
3. **Run validation after every step.** Each step in the plan files has a validation script. Run it before marking the step complete.
4. **Never skip ahead to a later step** because it seems simpler. Dependencies exist for a reason.
5. **Batch load in Neo4j** — always use `UNWIND $rows AS row` pattern. Never create nodes one at a time in a Python loop.
6. **Use `IF NOT EXISTS`** on all Cypher constraints and indexes so `loader.py` is idempotent.
7. **Store deleted relationship inventory** in `flaw_injector.py` before any deletion — this is required for `clear_all_flaws()`.
8. **Detection Cypher must scope by `flaw_scenario` tag** — never run a full-graph detection query.
9. **pyvis renders via `st.components.v1.html(html, height=N)`** — always set explicit height. Do not write temp HTML files.
10. **No session state caching of graph data** — findings, rule counts, and badge values must query Neo4j directly.

---

## Critical technical constraints

| Constraint | Value | Enforced by |
|-----------|-------|-------------|
| Neo4j heap | ≤ 4 GB | `neo4j.conf` |
| Inject + detect time | ≤ 5s per scenario | Detection queries scoped by `flaw_scenario` index |
| Graph viz nodes | ≤ 500 | All vizzes use subgraphs, never full dataset |
| pyvis height | Set explicitly | Windows iframe clipping workaround |
| Neo4j syntax | 5.x (`FOR ... REQUIRE`, not `ON (x) ASSERT`) | See `spec_01_ontology.md` |

---

## Key technical decisions (immutable)

- **Overlay model:** Flaws injected as tags on baseline nodes — never clear-and-reload
- **DetectionRule nodes in graph:** Rules stored as `DetectionRule` nodes, Cypher loaded from graph at runtime
- **Findings written to graph:** `Finding` nodes created by detection, not cached in session state
- **Auto-detection:** Detection runs synchronously in same callback as injection (inject → detect → rerun)
- **Scenario isolation:** All detection Cypher scopes to `{flaw_scenario: 'S-XX'}` tag on Claims
- **split-pane viz:** `build_actual_subgraph()` vs `build_expected_subgraph()` — amber/dashed-red vs solid-green
- **pyvis only:** No `streamlit-agraph`. pyvis via `st.components.v1.html()`.

---

## Repository structure (target state)

```
kg-dq-demo/
├── CLAUDE.md                    ← you are here
├── requirements.md              ← full requirements (source of truth)
├── specs/                       ← split spec files (read before implementing)
├── plan/                        ← step-by-step implementation plans
├── data/
│   ├── reference/               ← cpt_codes.csv, icd10_codes.csv, detection_rules.yaml
│   └── generated/               ← gitignored; generator output
├── src/
│   ├── generate/                ← generator.py, domains.py
│   ├── graph/                   ← connection.py, loader.py, flaw_injector.py,
│   │                                detection.py, findings.py, viz.py
│   └── app/                     ← main.py, panel_*.py, styles.py
├── scripts/
│   └── setup.py                 ← one-command setup
├── .env                         ← gitignored
├── .env.example
├── .gitignore
└── requirements.txt
```

---

## Neo4j connection

```
URI:  bolt://localhost:7687
Browser: http://localhost:7474
Credentials: in .env (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
```

## Running the app

```bash
cd "C:/Users/kiri0/Claude2026/APP_xV Knowledge Graph DQ Demo"
.venv\Scripts\activate
streamlit run src/app/main.py
```

---

## Node color palette (quick reference)

| Node | Color |
|------|-------|
| Finding | `#a02828` |
| DetectionRule | `#4a3b7a` |
| Claim (flawed) | `#e08c2a` |
| Patient | `#4a90d9` |
| Provider | `#9b59b6` |
| Payer | `#2eacb0` |
| Authorization | `#f39c12` |

Full palette in `specs/spec_01_ontology.md`.

## xVector brand colors

| Use | Color |
|-----|-------|
| Accent / buttons | `#b84a1f` |
| Background | `#f7f5f0` |
| Sidebar | `#1a1a2e` |
| Finding badge | `#a02828` |
