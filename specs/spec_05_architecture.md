# Spec 05 — Technical Architecture & Design Decisions

**Read this file before implementing:** anything in `src/`, `scripts/`, `requirements.txt`

---

## Tech stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Python | CPython | 3.11+ |
| Graph DB | Neo4j Community Edition | 5.x |
| Graph driver | `neo4j` (official Python driver) | 5.x |
| Data generation | `faker`, `pandas`, `numpy` | Faker 24+ |
| App framework | `streamlit` | 1.35+ |
| Graph visualization | `pyvis` | 0.3+ |
| Config | `python-dotenv` | any recent |
| Rule library | `PyYAML` | any recent |

**No ORM layer.** All graph I/O uses raw Cypher via the official Neo4j Python driver.

---

## Repository structure

```
kg-dq-demo/
├── CLAUDE.md                         ← primary instruction file (read first)
├── requirements.md                   ← full requirements (source of truth)
├── specs/
│   ├── spec_01_ontology.md           ← nodes, relationships, Cypher constraints
│   ├── spec_02_data.md               ← synthetic data spec, source schemas
│   ├── spec_03_scenarios.md          ← all 6 anomaly scenarios, injection + detection
│   ├── spec_04_app.md                ← 5-panel app requirements
│   └── spec_05_architecture.md       ← this file
├── plan/
│   ├── phase1_steps.md               ← Phase 1 step-by-step with validation
│   ├── phase2_steps.md               ← Phase 2 step-by-step with validation
│   ├── phase3_steps.md               ← Phase 3 polish steps
│   └── smoke_test.md                 ← end-to-end smoke test checklist
├── data/
│   ├── reference/
│   │   ├── cpt_codes.csv             ← CPT code subset (static, committed)
│   │   ├── icd10_codes.csv           ← ICD-10 subset (static, committed)
│   │   └── detection_rules.yaml      ← Rule library (all 6 rules, committed)
│   └── generated/                    ← gitignored; output of generator.py
│       ├── system_a_emr/
│       ├── system_b_claims/
│       ├── system_c_payer/
│       ├── system_d_auth/
│       └── system_e_provider/
├── src/
│   ├── generate/
│   │   ├── generator.py              ← Outputs System A–E CSVs
│   │   └── domains.py                ← Reference data loader, payer/CPT logic
│   ├── graph/
│   │   ├── connection.py             ← Neo4j driver singleton + health check
│   │   ├── loader.py                 ← Schema setup + baseline load + DetectionRule load
│   │   ├── flaw_injector.py          ← 6 inject_* functions + clear_all_flaws()
│   │   ├── detection.py              ← run_rule(), run_all_rules(), get_finding_count()
│   │   ├── findings.py               ← list_findings(), update_status(), get_finding_subgraph()
│   │   └── viz.py                    ← pyvis builders: build_actual_subgraph(), build_expected_subgraph()
│   └── app/
│       ├── main.py                   ← Streamlit entry point + sidebar
│       ├── panel_ontology.py         ← Panel 1
│       ├── panel_rules.py            ← Panel 2
│       ├── panel_foundation.py       ← Panel 3
│       ├── panel_loader.py           ← Panel 4
│       ├── panel_findings.py         ← Panel 5
│       └── styles.py                 ← Custom CSS
├── scripts/
│   └── setup.py                      ← One-command: generate + load + verify
├── .env                              ← gitignored
├── .env.example                      ← committed
├── .gitignore
└── requirements.txt
```

---

## Module responsibilities and boundaries

### `connection.py`
- Single `get_driver()` function returning a cached `neo4j.GraphDatabase.driver` instance
- `check_connection(driver)` → `bool` — pings Neo4j, used by sidebar status indicator
- All other modules import from `connection.py`; no module creates its own driver

### `loader.py`
- `setup_schema(driver)` — creates all constraints and indexes (idempotent, uses `IF NOT EXISTS`)
- `load_baseline(driver, data_dir)` — loads all System A–E CSVs in dependency order
- `load_detection_rules(driver, rules_path)` — reads `detection_rules.yaml`, creates/merges `DetectionRule` nodes
- `clear_database(driver)` — drops all nodes and relationships (dev use only)

### `flaw_injector.py`
- `inject_s01(driver) → dict` — injects S-01 flaws, returns `{claims_affected, changes, inventory}`
- `inject_s02(driver) → dict` — similarly for S-02 through S-06
- `get_deletion_inventory(scenario_id, driver) → list` — returns relationships to be deleted (call BEFORE deletion)
- `clear_all_flaws(driver, inventory_by_scenario) → None` — restores all deleted relationships from inventory, removes flaw tags, deletes Finding nodes
- **Critical:** Each inject function stores deleted relationships in the returned `inventory` dict. The Streamlit layer saves this to `st.session_state`.

### `detection.py`
- `run_rule(rule_id, driver) → int` — executes rule Cypher from graph `DetectionRule` node, returns finding count
- `run_all_rules(driver) → dict` — runs all active rules, returns `{rule_id: finding_count}`
- `get_finding_count(driver) → int` — `MATCH (f:Finding {status:'open'}) RETURN count(f)`

### `findings.py`
- `list_findings(driver, status=None, scenario=None) → list[dict]`
- `acknowledge_finding(finding_id, driver) → None`
- `resolve_finding(finding_id, driver) → None`
- `get_finding_subgraph(finding_id, driver) → dict` — returns nodes + edges for split-pane viz

### `viz.py`
- `build_actual_subgraph(claim_id, driver) → str` — returns HTML string for pyvis left pane
- `build_expected_subgraph(scenario_id, driver) → str` — returns HTML string for pyvis right pane
- `build_ontology_diagram() → str` — static schema diagram for Panel 1 (no driver needed)
- `build_claim_neighborhood(claim_id, driver, max_nodes=300) → str` — Panel 3 subgraph

---

## Design decisions (all resolved)

| ID | Decision | Resolution |
|----|----------|------------|
| OQ-01 | Neo4j installation | Not pre-installed. Phase 1 includes Windows installation guide. Setup script runs after Neo4j is running. |
| OQ-02 | Dataset loading model | **Overlay, not clear-and-reload.** Flaw tags injected on baseline nodes. `clear_all_flaws()` removes without full reload. |
| OQ-03 | Contract version source data | Both `version_num=1` and `version_num=2` generated in System E CSVs. Loader builds `SUPERSEDED_BY` edges from version ordering. |
| OQ-04 | Graph visualization library | **pyvis** primary. Rendered via `st.components.v1.html()` with explicit height. `streamlit-agraph` not used. |
| OQ-05 | Demo session flow | **All six scenarios in one session.** Panel 4 checklist layout — all six visible simultaneously with status indicators. |

### Production detection architecture (key decisions)

- `DetectionRule` nodes live in the graph as first-class entities, loaded from `detection_rules.yaml` at startup
- Detection runs **automatically** on scenario injection — no manual trigger. `detection.run_rule()` fires immediately after injection, in the same Streamlit button callback
- `Finding` nodes are **written back into the graph**, not cached in session state. Every finding has `HAS_FINDING → Claim` and `TRIGGERED_BY → DetectionRule` edges
- Sidebar badge queries the graph live — `MATCH (f:Finding {status:'open'}) RETURN count(f)`
- Finding lifecycle (`Acknowledge`, `Resolve`) writes status changes directly to Neo4j
- Scenario isolation enforced by `flaw_scenario` tag — detection queries scope to this tag

---

## Desktop performance constraints

| Constraint | Limit | Enforcement |
|-----------|-------|-------------|
| Neo4j heap | ≤ 4 GB | Set in `neo4j.conf`: `server.memory.heap.max_size=4g` |
| KG load time | ≤ 60 seconds | Use `UNWIND` batch loading, not single-row Cypher |
| Detection query response | ≤ 5 seconds | Scope all queries by `flaw_scenario` tag; indexes on `Claim(is_flawed, flaw_scenario)` |
| Graph viz node limit | ≤ 500 nodes | Always render subgraphs, never full dataset |

### Batch loading pattern (required in `loader.py`)
```python
# Correct — batch UNWIND
def load_patients(driver, patients_df):
    records = patients_df.to_dict('records')
    with driver.session() as session:
        session.run("""
            UNWIND $rows AS row
            MERGE (p:Patient {patient_id: row.patient_id})
            SET p += row
        """, rows=records)

# Wrong — do NOT use single-row CREATE in a loop
```

---

## `requirements.txt`

```
neo4j>=5.0,<6.0
streamlit>=1.35
pyvis>=0.3
pandas>=2.0
numpy>=1.26
faker>=24.0
python-dotenv>=1.0
pyyaml>=6.0
```

---

## Neo4j Windows setup reference

1. Download Neo4j Community 5.x from neo4j.com/download-center (Windows ZIP or installer)
2. Install to `C:\neo4j\`
3. Edit `conf/neo4j.conf`:
   ```
   server.memory.heap.max_size=4g
   server.memory.heap.initial_size=1g
   ```
4. Start: `bin\neo4j console` or install as Windows service: `bin\neo4j install-service`
5. Open Neo4j Browser: `http://localhost:7474`
6. Default credentials: `neo4j` / `neo4j` — set new password on first login
7. Update `.env` with new password

---

## `.gitignore` entries required

```
.env
data/generated/
__pycache__/
*.pyc
.streamlit/
```
