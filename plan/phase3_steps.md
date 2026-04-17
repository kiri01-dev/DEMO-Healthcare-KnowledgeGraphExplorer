# Phase 3 — Polish & Demo Readiness: Step-by-Step

**Prerequisite:** Phase 2 gate approved. All five panels functional for at least 3 scenarios.

**Goal:** All 6 scenarios working end-to-end under 5 seconds combined. Should-priority requirements implemented. Demo narrative finalized. One-command setup verified.

---

## Step P3-1: Complete all six scenarios end-to-end

**Action:** Test every scenario through the full inject → detect → lifecycle → clear cycle.

**For each scenario S-01 through S-06:**
```bash
python -c "
import sys, time; sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv()
from graph.connection import get_driver
from graph.flaw_injector import inject_s01  # replace per scenario
from graph.detection import run_rule, get_finding_count
from graph.findings import list_findings, acknowledge_finding, resolve_finding

driver = get_driver()

t0 = time.time()
inj = inject_s01(driver)      # replace with inject_s0X
count = run_rule('DR-S01', driver)  # replace with DR-S0X
t1 = time.time()

print(f'Inject + detect time: {t1-t0:.2f}s')
assert t1 - t0 < 5.0, f'PERFORMANCE FAILURE: {t1-t0:.2f}s > 5s'
assert count > 0, 'No findings created'
print(f'Findings: {count}')

# Lifecycle test
findings = list_findings(driver)
if findings:
    fid = findings[0]['finding_id']
    acknowledge_finding(fid, driver)
    resolve_finding(fid, driver)
    print('Lifecycle: OK')

driver.close()
print(f'S-01: PASS')
"
```

**Pass criteria per scenario:**
- [ ] S-01: inject + detect < 5s, findings > 30
- [ ] S-02: inject + detect < 5s, findings > 30
- [ ] S-03: inject + detect < 5s, findings > 40
- [ ] S-04: inject + detect < 5s, findings > 10
- [ ] S-05: inject + detect < 5s, duplicate pairs > 20
- [ ] S-06: inject + detect < 5s, findings > 30
- [ ] All 6 simultaneously loaded: no interference, no duplicate findings

---

## Step P3-2: Implement should-priority features

**P2-03 — Expandable rule Cypher view:**
- In `panel_rules.py`: wrap rule card detail in `st.expander()`
- Show Cypher with `st.code(rule['cypher'], language='cypher')`
- Show version, last updated, applies_to

**P2-04 — Rule category filter:**
- Add `st.multiselect("Filter by category", CATEGORIES)` at top of panel
- Filter rule cards by selected categories

**P3-04 — KG metrics bar:**
- In `panel_foundation.py`: add `st.columns(4)` bar showing: total nodes, total relationships, open findings, active scenarios

**P5-06 — Detection chain mini-graph:**
- In `panel_findings.py`: when a finding is selected, show mini graph: `Claim → HAS_FINDING → Finding → TRIGGERED_BY → DetectionRule`
- Use `viz.build_detection_chain(finding_id, driver) -> str`

**P5-07 — Scenario progress tracker:**
- Track viewed scenarios in `st.session_state.scenarios_viewed`
- Mark scenario `viewed` when its findings are first displayed in Panel 5
- Show mini checklist in Panel 5 sidebar or panel header

- [ ] P2-03 complete
- [ ] P2-04 complete
- [ ] P3-04 complete
- [ ] P5-06 complete
- [ ] P5-07 complete

---

## Step P3-3: Scenario narrative cards — final text review

**Action:** Review all business framing quotes and narrative text in Panel 5 (P5-05 collapsible cards).

Each card must include (from `spec_03_scenarios.md`):
1. Business framing quote (in quotes, from RCM ops perspective)
2. What the flaw is (plain English, 2–3 sentences)
3. Why standard tools miss it (1–2 sentences, no jargon)
4. How the graph detected it (graph traversal described as traversal, not code)
5. Which `DetectionRule` fired (badge linking to Panel 2)

**Review checklist:**
- [ ] S-01 narrative approved
- [ ] S-02 narrative approved
- [ ] S-03 narrative approved
- [ ] S-04 narrative approved
- [ ] S-05 narrative approved
- [ ] S-06 narrative approved

---

## Step P3-4: `scripts/setup.py` — one-command setup

**Action:** Implement the one-command setup script.

```bash
python scripts/setup.py
```

**Script sequence:**
1. Check Neo4j is reachable (fail fast with setup instructions if not)
2. Check `data/reference/` files exist (`cpt_codes.csv`, `icd10_codes.csv`, `detection_rules.yaml`)
3. Run data generator → `data/generated/`
4. Run `loader.setup_schema()`
5. Run `loader.load_baseline()`
6. Run `loader.load_detection_rules()`
7. Print summary: node counts, relationship counts, rule count
8. Print: "Setup complete. Run: streamlit run src/app/main.py"

**Validation:**
```bash
# Fresh run (drop database first in Neo4j Browser: MATCH (n) DETACH DELETE n)
python scripts/setup.py

# Expected output:
# Checking Neo4j connection... OK
# Generating synthetic data...
# Loading baseline to graph...
# Patients: 1000, Claims: 5432, ...
# Detection rules loaded: 6
# Setup complete. Run: streamlit run src/app/main.py
```

- [ ] Step P3-4 complete

---

## Step P3-5: `README.md` and demo walkthrough guide

**Action:** Create `README.md` with:
1. Prerequisites (Python 3.11+, Neo4j Community 5.x)
2. Neo4j Windows setup (from `spec_05_architecture.md`)
3. Python environment setup
4. One-command setup
5. Running the app
6. Demo walkthrough guide (5-beat narrative script)
7. Troubleshooting common issues

**Demo walkthrough script (5 beats):**
- Beat 1: "Here is the semantic model..." — Ontology Explorer, point out 14 node types
- Beat 2: "Here are the detection rules..." — Rule Library, show zero findings
- Beat 3: "Here is the live graph..." — KG Foundation, search a claim
- Beat 4: "Introducing a real problem..." — Scenario Loader, inject S-01, watch badge
- Beat 5: "Found before a single claim was worked..." — Findings Dashboard, lifecycle demo

- [ ] README.md complete

---

## Phase 3 gate — dry run

**Pre-dry-run reset:**
```bash
# In Neo4j Browser:
MATCH (n) DETACH DELETE n;

# Then:
python scripts/setup.py
streamlit run src/app/main.py
```

**Dry run checklist (simulate a real demo):**
- [ ] App loads, sidebar shows "Connected" and "0 open findings"
- [ ] Beat 1: Ontology Explorer — schema diagram visible, all 14 types, instance counts correct
- [ ] Beat 2: Rule Library — 6 rule cards, all showing 0 findings, category badges colored
- [ ] Beat 3: KG Foundation — search a claim, neighborhood renders, legend visible
- [ ] Beat 4: Inject S-01 — spinner, badge fires, row flips to loaded, summary card appears
- [ ] Beat 4 (cont): Inject S-04 — both S-01 and S-04 active simultaneously, no errors
- [ ] Beat 5: Findings Dashboard — open findings table, row selection, split pane renders
- [ ] Beat 5 (cont): Acknowledge a finding — badge decrements
- [ ] Beat 5 (cont): Resolve a finding — resolved_at set
- [ ] Navigate back to Rule Library — DR-S01 and DR-S04 show finding counts
- [ ] Clear All Flaws — everything resets, badge back to 0
- [ ] Walk all 6 scenarios in sequence — no errors, all findings created
- [ ] Total demo time: < 20 minutes

**POC-complete criteria:**
- [ ] All 5 panels flow without Python exceptions
- [ ] Finding lifecycle works correctly end-to-end
- [ ] Narrative is clear to a non-technical observer
- [ ] Performance: inject + detect < 5s per scenario
- [ ] xVector visual identity applied (colors, no default Streamlit styling)
