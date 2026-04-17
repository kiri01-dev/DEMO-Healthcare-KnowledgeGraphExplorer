# Spec 04 — Application Requirements

**Read this file before implementing:** any `panel_*.py`, `main.py`, `styles.py`

---

## Demo narrative arc (5 beats)

The app flows linearly through five panels. Each panel builds on the previous one.

1. **Ontology Explorer** — *"Here is the semantic model of your revenue cycle — every entity and relationship that governs how a clean claim looks."*
2. **Rule Library** — *"Here are the detection rules configured for this context. Each one is a named, versioned graph traversal. Zero findings right now — the baseline is clean."*
3. **KG Foundation** — *"Here is what the live graph looks like. Every claim, every provider, every auth chain, traversable."*
4. **Scenario Loader** — *"We're introducing a data quality problem that happens in real operations. Watch the sidebar."* [inject → badge fires]
5. **Findings Dashboard** — *"The graph found these before a single claim was worked. Every finding is in the graph, trackable, assignable, auditable over time."*

---

## Global requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| APP-01 | Left sidebar navigation. Shows: Neo4j connection status (green/red dot), open finding count badge (live query: `MATCH (f:Finding {status:'open'}) RETURN count(f)`). Badge: grey `0` on clean baseline, red `N open findings` after injection. Updates without page refresh | **Must** |
| APP-02 | Neo4j connection via `.env` file. Clear error message with fix instructions if unreachable | **Must** |
| APP-03 | Custom CSS: accent `#b84a1f`, background `#f7f5f0`. Node color palette in `spec_01_ontology.md` applied consistently across all pyvis visualizations | **Must** |
| APP-04 | All panels load within 3 seconds (excluding graph render). Finding queries use indexes on `Finding.status` and `Finding.detected_at` | **Should** |

### `.env` file format
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

---

## Panel 1 — Ontology Explorer (`panel_ontology.py`)

| ID | Requirement | Priority |
|----|-------------|----------|
| P1-01 | pyvis schema diagram showing all 14 node types and all relationship types. `DetectionRule` and `Finding` are first-class graph citizens — not metadata. Node colors from `spec_01_ontology.md` color palette | **Must** |
| P1-02 | Node type inventory table: label, property count, live instance count from graph. Relationship type table: type name, live count. `Finding` count starts at 0 and updates as scenarios are injected | **Must** |
| P1-03 | Click a node type → detail pane: properties, sample values, connected relationship types. Clicking `DetectionRule` shows rule metadata; clicking `Finding` shows a sample finding node if any exist | **Should** |

---

## Panel 2 — Rule Library (`panel_rules.py`)

*The production monitoring story made visible.*

| ID | Requirement | Priority |
|----|-------------|----------|
| P2-01 | Rule cards: one card per `DetectionRule` node pulled from the graph. Each card shows: rule ID badge, name, category badge (color-coded), severity (HIGH/MEDIUM/LOW), business description, and live finding count: `MATCH (f:Finding)-[:TRIGGERED_BY]->(r:DetectionRule {rule_id:$id}) RETURN count(f)` | **Must** |
| P2-02 | Finding count on each rule card starts at `0` on clean baseline; increments as scenarios are injected — without panel refresh. This is the most visceral signal that the system is monitoring continuously | **Must** |
| P2-03 | Expanding a rule card shows: the Cypher detection query (syntax-highlighted, collapsible), version number, last updated date, applicable node types | **Should** |
| P2-04 | Rule category filter: `prior_authorization`, `credentialing`, `contract`, `authorization_units`, `entity_integrity`, `referral` | **Should** |
| P2-05 | Static callout: "In production, this library grows with the client's payer mix and denial history. New rules are added without code changes. Rules are versioned as payer policies evolve." | **Should** |

### Rule category color coding
| Category | Color |
|---------|-------|
| prior_authorization | `#e74c3c` (red) |
| credentialing | `#9b59b6` (purple) |
| contract | `#f39c12` (orange) |
| authorization_units | `#e67e22` (dark orange) |
| entity_integrity | `#3498db` (blue) |
| referral | `#1abc9c` (teal) |

---

## Panel 3 — KG Foundation (`panel_foundation.py`)

| ID | Requirement | Priority |
|----|-------------|----------|
| P3-01 | pyvis subgraph: default view is a sample Claim and its full 2-hop neighborhood (Patient, Visit, CPT, Payer, Provider, Coverage, Auth). Max 300 nodes. After injection, `Finding` nodes appear connected to affected Claims | **Must** |
| P3-02 | Search by Claim ID or Patient ID → renders that entity's neighborhood. Selected node highlighted. If claim has `Finding` nodes, they appear automatically | **Must** |
| P3-03 | Node color coding with legend — consistent with `spec_01_ontology.md` palette. `Finding` = `#a02828`; `DetectionRule` = `#4a3b7a`; flawed Claim = `#e08c2a` (amber) | **Must** |
| P3-04 | Metrics bar: total nodes, total relationships, open finding count, active scenario name | **Should** |

---

## Panel 4 — Scenario Loader (`panel_loader.py`)

**Injection model:** Flaws overlaid on clean baseline. Affected Claims tagged with `is_flawed: true`, `flaw_scenario: 'S-XX'`. Detection runs immediately post-injection. "Clear All Flaws" fully restores baseline.

| ID | Requirement | Priority |
|----|-------------|----------|
| P4-01 | Scenario checklist: all six scenarios displayed simultaneously with status `pending / loaded / viewed` per row. Each row: scenario ID, category badge, severity, one-sentence description, live finding count. Supports linear walkthrough of all six | **Must** |
| P4-02 | "Inject" button per scenario. On click: (1) run injection Cypher — tags Claims, modifies relationships, (2) run detection Cypher — creates `Finding` nodes with `HAS_FINDING` and `TRIGGERED_BY` edges, (3) update sidebar badge, (4) flip row to `loaded`. Progress indicator during steps 1–2 | **Must** |
| P4-03 | Post-injection summary card: claims affected, relationship changes made (e.g., *"12 `HAS_AUTHORIZATION` relationships removed"*), findings created, business framing quote | **Must** |
| P4-04 | "Clear All Flaws" button: removes all `is_flawed`/`flaw_scenario` properties, deletes all `Finding` nodes and relationships, resets sidebar badge to `0`, resets all rows to `pending`. Single Cypher transaction | **Must** |

### Inject button callback sequence
```python
def inject_scenario(scenario_id, driver, session_state):
    # 1. Store inventory of relationships to be deleted (for restoration)
    inventory = flaw_injector.get_deletion_inventory(scenario_id, driver)
    session_state[f'inventory_{scenario_id}'] = inventory
    
    # 2. Run injection
    affected_claims, changes = flaw_injector.inject(scenario_id, driver)
    
    # 3. Run detection immediately — same callback
    finding_count = detection.run_rule(f'DR-{scenario_id}', driver)
    
    # 4. Update scenario status
    session_state[f'status_{scenario_id}'] = 'loaded'
    
    # 5. Return summary for post-injection card
    return affected_claims, changes, finding_count
```

---

## Panel 5 — Findings Dashboard (`panel_findings.py`)

*Findings read from graph — not session state cache. Every lifecycle action writes back to Neo4j. The graph is the system of record.*

| ID | Requirement | Priority |
|----|-------------|----------|
| P5-01 | Summary scorecard: open findings count, acknowledged count, resolved count, total estimated denial risk (sum of `Finding.estimated_risk_amount`, labeled "illustrative"), breakdown by severity (HIGH/MEDIUM/LOW) | **Must** |
| P5-02 | Findings table (from `Finding` nodes in graph): Finding ID, Claim ID, Patient ID, Rule ID, Rule Name, Severity, Status, Detected At, description. Sortable/filterable by severity, status, rule. Default: `status = 'open'` | **Must** |
| P5-03 | Row selection → split-pane subgraph view: LEFT pane — actual claim subgraph (anomalous nodes amber, missing relationships as dashed red `MISSING` edges, Finding node visible); RIGHT pane — expected path per ontology (all nodes present, solid green edges, Finding node absent). Finding appears only in left pane | **Must** |
| P5-04 | Finding lifecycle buttons on selected row: `Acknowledge` → `Finding.status = 'acknowledged'`; `Resolve` → `Finding.status = 'resolved'` + `Finding.resolved_at = datetime()`. Both write directly to Neo4j. Sidebar badge decrements in real time | **Must** |
| P5-05 | Scenario narrative card (collapsible): business framing quote, what the flaw is, why standard tools miss it, how the graph detected it, which `DetectionRule` fired | **Must** |
| P5-06 | Detection chain view: mini graph showing `Claim → HAS_FINDING → Finding → TRIGGERED_BY → DetectionRule`. Click node to expand properties | **Should** *(deferred — not implemented)* |
| P5-07 | Scenario progress tracker: mini checklist of 6 scenarios, marks `viewed` when findings first viewed. Session-level tracking | **Should** *(deferred — not implemented)* |

### Split-pane visualization spec
The split pane is the most complex UI element. Implement via two side-by-side `st.columns(2)`:
- Left column: pyvis `actual` graph — calls `viz.build_actual_subgraph(claim_id, driver)`
- Right column: pyvis `expected` graph — calls `viz.build_expected_subgraph(scenario_id, driver)`

In the actual subgraph:
- Flawed/affected nodes: amber `#e08c2a`
- Missing relationships: dashed red edges labeled `MISSING`
- Finding node: deep red `#a02828`

In the expected subgraph:
- All nodes: normal colors from palette
- All edges: solid green `#27ae60`
- No Finding node present

---

## pyvis rendering notes (Windows-specific)

- Render via `st.components.v1.html(html_content, height=600)` — explicit height required to avoid iframe clipping on Windows
- Generate the HTML string via `net.generate_html()` (do not write temp files to disk)
- Physics: use `forceAtlas2Based` layout for cleaner subgraph rendering
- Set `net.set_options()` with `"nodes": {"font": {"size": 14}}` for readability at 1080p

---

## Sidebar live badge implementation

```python
# In main.py sidebar
def get_open_finding_count(driver):
    with driver.session() as session:
        result = session.run("MATCH (f:Finding {status:'open'}) RETURN count(f) AS n")
        return result.single()["n"]

# Render
count = get_open_finding_count(driver)
if count == 0:
    st.sidebar.metric("Open Findings", "0")
else:
    st.sidebar.markdown(f'<span style="color:#a02828; font-weight:bold">{count} open findings</span>',
                        unsafe_allow_html=True)
```
