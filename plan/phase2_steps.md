# Phase 2 — Streamlit Application: Step-by-Step

**Prerequisite:** Phase 1 gate approved. Neo4j running with clean baseline + 6 DetectionRule nodes.

**Specs to have open:** `spec_04_app.md`, `spec_01_ontology.md`, `spec_05_architecture.md`

**Run app during development:**
```bash
cd "C:/Users/kiri0/Claude2026/APP_xV Knowledge Graph DQ Demo"
.venv\Scripts\activate
streamlit run src/app/main.py
```

---

## Step P2-1: Project scaffolding + `styles.py`

**Action:** Create directory structure, `.env.example`, `.gitignore`, and `styles.py`.

**`styles.py`** must export:
```python
def inject_css() -> None  # calls st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
```

CSS variables:
- Background: `#f7f5f0`
- Accent (buttons, badges): `#b84a1f`
- Sidebar background: `#1a1a2e`
- Finding badge red: `#a02828`
- Font: system default (no external fonts)

**Validation:**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from app.styles import inject_css
print('styles.py: import OK')
"
```

- [ ] Step P2-1 complete

---

## Step P2-2: `src/app/main.py` — app shell + sidebar

**Action:** Implement the Streamlit entry point with sidebar and five-panel navigation.

**Sidebar must contain (in order):**
1. xVector logo text / project title
2. Neo4j connection status: green dot "Connected" or red dot "Disconnected"
3. Open finding count badge (live query, updates on rerun)
4. Navigation radio: `["Ontology Explorer", "Rule Library", "KG Foundation", "Scenario Loader", "Findings Dashboard"]`

**Panel routing:**
```python
panel = st.sidebar.radio("Navigate", PANELS)
if panel == "Ontology Explorer":
    panel_ontology.render(driver)
elif panel == "Rule Library":
    panel_rules.render(driver)
# etc.
```

**Validation:**
```bash
# Manual: run app and confirm:
# 1. Sidebar shows connection status
# 2. Finding count shows "0" on clean baseline
# 3. All 5 panels navigate without error (even if content is stub)
streamlit run src/app/main.py
```

- [ ] Step P2-2 complete

---

## Step P2-3: `src/graph/viz.py` — ontology diagram

**Action:** Implement `build_ontology_diagram()` for Panel 1. This is the static schema diagram showing all 14 node types and 21 relationship types.

**Node colors:** from `spec_01_ontology.md` color palette.

```python
def build_ontology_diagram() -> str:
    """Returns HTML string for pyvis ontology schema visualization."""
    from pyvis.network import Network
    net = Network(height="500px", width="100%", directed=True)
    net.set_options(PYVIS_OPTIONS)  # forceAtlas2Based
    
    # Add all 14 node types as schema nodes (not data nodes)
    # Add representative edges for each relationship type
    # Return net.generate_html()
```

**Validation:**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from graph.viz import build_ontology_diagram
html = build_ontology_diagram()
assert '<html>' in html.lower() or 'pyvis' in html.lower()
assert len(html) > 5000  # should be a substantial HTML blob
print('build_ontology_diagram: OK')
"
```

- [ ] Step P2-3 complete

---

## Step P2-4: `src/app/panel_ontology.py` — Panel 1

**Action:** Implement the Ontology Explorer panel.

**Must render:**
- pyvis schema diagram (from `viz.build_ontology_diagram()`) via `st.components.v1.html(html, height=500)`
- Node type table: label | property count | live instance count (query Neo4j)
- Relationship type table: type | live count (query Neo4j)

**Validation (manual):**
- Navigate to Ontology Explorer
- Schema diagram renders with all node types visible and colored correctly
- Instance counts update after injection (Finding count goes from 0 to N)

- [ ] Step P2-4 complete

---

## Step P2-5: `src/app/panel_rules.py` — Panel 2

**Action:** Implement the Rule Library panel.

**Each rule card must show:** rule ID badge, name, category badge (colored per `spec_04_app.md`), severity, description, live finding count.

**Category badge colors** (from `spec_04_app.md`):
```python
CATEGORY_COLORS = {
    'prior_authorization': '#e74c3c',
    'credentialing':       '#9b59b6',
    'contract':            '#f39c12',
    'authorization_units': '#e67e22',
    'entity_integrity':    '#3498db',
    'referral':            '#1abc9c',
}
```

**Finding count query per card:**
```python
def get_rule_finding_count(rule_id, driver) -> int:
    with driver.session() as s:
        return s.run(
            "MATCH (f:Finding)-[:TRIGGERED_BY]->(r:DetectionRule {rule_id:$id}) RETURN count(f) AS n",
            id=rule_id
        ).single()['n']
```

**Validation (manual):**
- All 6 rule cards render
- Finding counts all show `0` on clean baseline
- After injecting S-01 (from Panel 4), navigate back to Rule Library — DR-S01 count updates

- [ ] Step P2-5 complete

---

## Step P2-6: `src/graph/viz.py` — claim neighborhood subgraph

**Action:** Implement `build_claim_neighborhood(claim_id, driver, max_nodes=300) -> str`.

Node colors must match `spec_01_ontology.md`. Flawed claims (`is_flawed=True`) render in amber `#e08c2a`. Finding nodes render in `#a02828`.

**Validation:**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv()
from graph.connection import get_driver
from graph.viz import build_claim_neighborhood

driver = get_driver()
with driver.session() as s:
    cid = s.run('MATCH (c:Claim) RETURN c.claim_id LIMIT 1').single()['c.claim_id']
html = build_claim_neighborhood(cid, driver)
assert len(html) > 1000, 'HTML too short — likely empty graph'
print(f'build_claim_neighborhood({cid!r}): OK')
driver.close()
"
```

- [ ] Step P2-6 complete

---

## Step P2-7: `src/app/panel_foundation.py` — Panel 3

**Action:** Implement the KG Foundation panel.

**Must include:**
- Search input (Claim ID or Patient ID)
- pyvis subgraph rendered via `st.components.v1.html(html, height=600)`
- Legend showing node color → type mapping
- Metrics bar: total nodes, total relationships, open findings, active scenario

**Validation (manual):**
- Default view renders a claim neighborhood
- Search by Claim ID renders that claim's subgraph
- After S-01 injection, searching an affected claim shows Finding node in red

- [ ] Step P2-7 complete

---

## Step P2-8: `src/app/panel_loader.py` — Panel 4

**Action:** Implement the Scenario Loader panel. This is the most complex panel — implement carefully.

**Scenario status** stored in `st.session_state`:
```python
# Initialize on first run
if 'scenario_status' not in st.session_state:
    st.session_state.scenario_status = {f'S-0{i}': 'pending' for i in range(1, 7)}
if 'scenario_inventory' not in st.session_state:
    st.session_state.scenario_inventory = {}
```

**Inject button callback** (per `spec_04_app.md` Panel 4 spec):
```python
with st.spinner(f"Injecting {scenario_id}..."):
    inventory = flaw_injector.get_deletion_inventory(scenario_id, driver)
    st.session_state.scenario_inventory[scenario_id] = inventory
    result = flaw_injector.inject(scenario_id, driver)
    finding_count = detection.run_rule(f'DR-{scenario_id}', driver)
    st.session_state.scenario_status[scenario_id] = 'loaded'
st.rerun()
```

**Validation (manual):**
- All 6 scenario rows visible with `pending` status
- Clicking "Inject" on S-01: spinner appears, row flips to `loaded`, sidebar badge updates
- Post-injection card shows claims affected, changes, findings created, business quote
- "Clear All Flaws" resets all rows to `pending`, sidebar badge to 0

- [ ] Step P2-8 complete

---

## Step P2-9: `src/graph/viz.py` — split-pane subgraph builders

**Action:** Implement `build_actual_subgraph(claim_id, driver) -> str` and `build_expected_subgraph(scenario_id, driver) -> str`.

**Actual subgraph:**
- Affected nodes: amber `#e08c2a`
- Missing relationships: dashed red edges labeled `MISSING`
- Finding node: `#a02828`, visible and connected

**Expected subgraph:**
- All nodes: normal color palette
- All edges: solid green `#27ae60`
- No Finding node
- Labels indicate "Expected path"

```python
def build_actual_subgraph(claim_id: str, driver) -> str:
    """Left pane: what actually exists in the graph, including flaws."""

def build_expected_subgraph(scenario_id: str, driver) -> str:
    """Right pane: what the ontology says should exist (clean path)."""
```

**Validation:**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv()
from graph.connection import get_driver
from graph.flaw_injector import inject_s01
from graph.detection import run_rule
from graph.viz import build_actual_subgraph, build_expected_subgraph

driver = get_driver()
inj = inject_s01(driver)
run_rule('DR-S01', driver)

# Get an affected claim ID
with driver.session() as s:
    cid = s.run(\"MATCH (c:Claim {flaw_scenario:'S-01'}) RETURN c.claim_id LIMIT 1\").single()['c.claim_id']

actual_html = build_actual_subgraph(cid, driver)
expected_html = build_expected_subgraph('S-01', driver)

assert 'MISSING' in actual_html or len(actual_html) > 1000
assert len(expected_html) > 1000
print('build_actual_subgraph: OK')
print('build_expected_subgraph: OK')
driver.close()
"
```

- [ ] Step P2-9 complete

---

## Step P2-10: `src/app/panel_findings.py` — Panel 5

**Action:** Implement the Findings Dashboard.

**Must implement:**
- P5-01: Summary scorecard (open/ack/resolved counts + total risk)
- P5-02: Findings table with status filter (default: `open`)
- P5-03: Row selection → split-pane subgraph (side-by-side columns)
- P5-04: Acknowledge + Resolve buttons (write to Neo4j, sidebar updates)
- P5-05: Scenario narrative card (collapsible)

**Split-pane implementation:**
```python
col1, col2 = st.columns(2)
with col1:
    st.caption("Actual graph (with flaw)")
    html_actual = viz.build_actual_subgraph(selected_claim_id, driver)
    st.components.v1.html(html_actual, height=400)
with col2:
    st.caption("Expected path (clean ontology)")
    html_expected = viz.build_expected_subgraph(selected_scenario, driver)
    st.components.v1.html(html_expected, height=400)
```

**Validation (manual):**
- Navigate after injecting 2+ scenarios
- Findings table shows open findings with correct metadata
- Click a row → split pane renders (both sides)
- Click Acknowledge → finding moves to acknowledged filter, sidebar badge decrements
- Click Resolve → finding resolved_at timestamp set, count decrements
- Scenario narrative card collapses/expands correctly

- [ ] Step P2-10 complete

---

## Phase 2 gate review

Full narrative walkthrough with at least 3 scenarios injected:

**Checklist:**
- [ ] Beat 1: Ontology Explorer renders all 14 node types, instance counts live
- [ ] Beat 2: Rule Library shows all 6 rules with `0` findings on baseline
- [ ] Beat 3: KG Foundation search works, 2-hop neighborhood renders
- [ ] Beat 4: Inject S-01 → sidebar badge updates, row flips to `loaded`
- [ ] Beat 4 (cont): Inject S-02, S-03 — all three active simultaneously, no interference
- [ ] Beat 5: Findings Dashboard shows open findings, split pane renders, lifecycle buttons work
- [ ] "Clear All Flaws" resets everything cleanly
- [ ] Custom CSS applied (xVector colors visible, `#b84a1f` accent)
- [ ] No unhandled Python exceptions in terminal
- [ ] Neo4j Browser confirms Finding node structure after injection

**→ Approve to proceed to Phase 3**
