# Smoke Test — Full Application

**Run after Phase 3 is complete. This is the final POC-readiness verification.**

**Setup:**
```bash
# 1. Drop and reload from scratch
# In Neo4j Browser: MATCH (n) DETACH DELETE n;

# 2. One-command setup
python scripts/setup.py

# 3. Start app
streamlit run src/app/main.py
```

---

## Block 1: Baseline state

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| 1.1 | App loads at localhost:8501 | No error, sidebar visible | [ ] |
| 1.2 | Sidebar connection status | Green dot "Connected" | [ ] |
| 1.3 | Sidebar open findings badge | "0" (grey) | [ ] |
| 1.4 | Panel 1 — Ontology Explorer loads | Schema diagram renders | [ ] |
| 1.5 | Ontology diagram shows 14 node types | Count visible in legend or diagram | [ ] |
| 1.6 | Node instance table: Finding count = 0 | `Finding: 0` in table | [ ] |
| 1.7 | Panel 2 — Rule Library loads | 6 rule cards visible | [ ] |
| 1.8 | All 6 rule finding counts = 0 | Each card shows `0 findings` | [ ] |
| 1.9 | Panel 3 — KG Foundation loads | Default subgraph renders | [ ] |
| 1.10 | Claim search returns subgraph | Enter a Claim ID, graph updates | [ ] |
| 1.11 | Panel 4 — Scenario Loader loads | 6 rows, all `pending` | [ ] |
| 1.12 | Panel 5 — Findings Dashboard loads | Empty table, scoreboard at 0 | [ ] |

---

## Block 2: Single scenario injection — S-01

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| 2.1 | Inject S-01 button click | Spinner appears | [ ] |
| 2.2 | Injection completes | Spinner disappears, no error | [ ] |
| 2.3 | S-01 row status | Flips to `loaded` | [ ] |
| 2.4 | Sidebar badge | Red "N open findings" (N > 0) | [ ] |
| 2.5 | Post-injection summary card | Shows claims affected + findings created | [ ] |
| 2.6 | Navigate to Panel 2 (Rule Library) | DR-S01 card shows N > 0 findings | [ ] |
| 2.7 | Other 5 rule cards | Still show 0 findings | [ ] |
| 2.8 | Navigate to Panel 3 (KG Foundation) | Search an S-01 claim: Finding node visible in red | [ ] |
| 2.9 | Navigate to Panel 5 (Findings Dashboard) | Open findings table populated | [ ] |
| 2.10 | Findings table columns correct | ID, Claim ID, Patient ID, Rule, Severity, Status, Detected At | [ ] |
| 2.11 | Select a finding row | Split-pane subgraph renders (both sides) | [ ] |
| 2.12 | Left pane (actual) | Amber node + dashed red MISSING edge visible | [ ] |
| 2.13 | Right pane (expected) | Clean green edges, no Finding node | [ ] |
| 2.14 | Scenario narrative card | Collapses/expands, RCM language readable | [ ] |
| 2.15 | Time: inject + detect (re-check) | < 5 seconds total | [ ] |

---

## Block 3: Finding lifecycle

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| 3.1 | Select open finding, click "Acknowledge" | No error | [ ] |
| 3.2 | Sidebar badge | Decrements by 1 | [ ] |
| 3.3 | Switch to "Acknowledged" filter | Acknowledged finding appears | [ ] |
| 3.4 | Select acknowledged finding, click "Resolve" | No error | [ ] |
| 3.5 | Switch to "Resolved" filter | Resolved finding appears | [ ] |
| 3.6 | Neo4j Browser verification | `MATCH (f:Finding) RETURN f.status, f.resolved_at LIMIT 5` — resolved finding has timestamp | [ ] |
| 3.7 | Scoreboard totals | Open/Ack/Resolved counts match findings table | [ ] |

---

## Block 4: Multi-scenario operation

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| 4.1 | Inject S-02 (while S-01 active) | Completes without error | [ ] |
| 4.2 | Sidebar badge | Increases by S-02 finding count | [ ] |
| 4.3 | Rule Library | DR-S01 count unchanged, DR-S02 shows new count | [ ] |
| 4.4 | Panel 5 filter by rule | Can filter to only S-01 or only S-02 findings | [ ] |
| 4.5 | Inject S-03 | Completes, badge increases | [ ] |
| 4.6 | Inject S-04 | Completes, badge increases | [ ] |
| 4.7 | Inject S-05 | Completes, badge increases | [ ] |
| 4.8 | Inject S-06 | Completes, badge increases | [ ] |
| 4.9 | All 6 injected simultaneously | No Python exceptions in terminal | [ ] |
| 4.10 | Total finding count | Matches sum of individual rule counts | [ ] |

---

## Block 5: Clear and reset

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| 5.1 | Click "Clear All Flaws" | Completes without error | [ ] |
| 5.2 | Sidebar badge | Resets to "0" | [ ] |
| 5.3 | All 6 scenario rows | Reset to `pending` | [ ] |
| 5.4 | Panel 5 Findings table | Empty (no open findings) | [ ] |
| 5.5 | Panel 2 Rule Library | All rule counts back to 0 | [ ] |
| 5.6 | Neo4j Browser verification | `MATCH (f:Finding) RETURN count(f)` → 0 | [ ] |
| 5.7 | Neo4j Browser verification | `MATCH (c:Claim) WHERE c.is_flawed=true RETURN count(c)` → 0 | [ ] |
| 5.8 | Inject S-01 again after clear | Works correctly (injection is idempotent on clean baseline) | [ ] |

---

## Block 6: Performance

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| 6.1 | Time `scripts/setup.py` full run | < 90 seconds | [ ] |
| 6.2 | Time S-01 inject + detect | < 5 seconds | [ ] |
| 6.3 | Time S-04 inject + detect (aggregation heavy) | < 5 seconds | [ ] |
| 6.4 | Time S-05 inject + detect (node similarity) | < 10 seconds (relaxed — pattern is cross-product) | [ ] |
| 6.5 | Panel load times (1–5) | Each < 3 seconds | [ ] |
| 6.6 | Neo4j heap utilization | Neo4j Browser → `:sysinfo` → heap < 4 GB | [ ] |

---

## Block 7: UI polish

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| 7.1 | Background color | `#f7f5f0` (off-white) | [ ] |
| 7.2 | Accent color on buttons/badges | `#b84a1f` (xVector rust) | [ ] |
| 7.3 | No default Streamlit orange visible | Custom CSS overrides applied | [ ] |
| 7.4 | Node colors consistent across panels | Same palette in Panel 1, 3, 5 split pane | [ ] |
| 7.5 | No broken pyvis iframe clipping | All graphs fully visible, no vertical cutoff | [ ] |
| 7.6 | Text readable at 1080p | No font too small, no text overflow | [ ] |

---

## Block 8: Error handling

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| 8.1 | Stop Neo4j, reload app | "Neo4j Disconnected" message with instructions, no crash | [ ] |
| 8.2 | Search for non-existent Claim ID | Graceful "not found" message, no exception | [ ] |
| 8.3 | Click "Inject" twice on same scenario | Second click either no-ops or shows "already injected" | [ ] |

---

## Smoke test result

| Block | Checks | Pass | Fail | Notes |
|-------|--------|------|------|-------|
| 1: Baseline | 12 | | | |
| 2: S-01 injection | 15 | | | |
| 3: Lifecycle | 7 | | | |
| 4: Multi-scenario | 10 | | | |
| 5: Clear & reset | 8 | | | |
| 6: Performance | 6 | | | |
| 7: UI polish | 6 | | | |
| 8: Error handling | 3 | | | |
| **TOTAL** | **67** | | | |

**POC-ready threshold:** 60/67 checks passing (no Block 1, 2, 3, or 5 failures allowed).

---

## Known issues / deferred items

*(Fill in during smoke test)*

| Issue | Severity | Deferred to |
|-------|---------|-------------|
| | | |
