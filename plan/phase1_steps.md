# Phase 1 — Data & Graph Foundation: Step-by-Step

**Goal:** Clean baseline in Neo4j with DetectionRule nodes loaded and all six flaw scenarios injectable and detectable via Python scripts.

**Specs to have open:** `spec_01_ontology.md`, `spec_02_data.md`, `spec_03_scenarios.md`, `spec_05_architecture.md`

**Status tracking:** Update `[ ]` → `[x]` as each step completes.

---

## Pre-flight: Neo4j setup

### Step P1-0: Install and configure Neo4j Community 5.x on Windows

**Action:**
1. Download Neo4j Community 5.x (Windows ZIP) from neo4j.com
2. Extract to `C:\neo4j\`
3. Edit `C:\neo4j\conf\neo4j.conf`:
   ```
   server.memory.heap.max_size=4g
   server.memory.heap.initial_size=1g
   ```
4. Start: open cmd as administrator, run `C:\neo4j\bin\neo4j console`
5. Open `http://localhost:7474`, log in with `neo4j`/`neo4j`, set new password
6. Create `.env` file from `.env.example`:
   ```
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=<your new password>
   ```

**Validation:**
```bash
# From project root
python -c "
from dotenv import load_dotenv; load_dotenv()
import os
from neo4j import GraphDatabase
driver = GraphDatabase.driver(os.getenv('NEO4J_URI'), auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD')))
driver.verify_connectivity()
print('Neo4j connection: OK')
driver.close()
"
```
**Pass:** prints `Neo4j connection: OK`

- [ ] Step P1-0 complete

---

## Step P1-1: Python environment setup

**Action:** Create `requirements.txt` (content in `spec_05_architecture.md`) and install.

```bash
cd "C:/Users/kiri0/Claude2026/APP_xV Knowledge Graph DQ Demo"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Validation:**
```bash
python -c "import neo4j, streamlit, pyvis, pandas, numpy, faker, dotenv, yaml; print('All imports OK')"
```
**Pass:** prints `All imports OK`

- [ ] Step P1-1 complete

---

## Step P1-2: Reference data files

**Action:** Create `data/reference/cpt_codes.csv` and `data/reference/icd10_codes.csv`.

**`cpt_codes.csv` required columns:** `code`, `description`, `category`, `requires_auth`

Include at minimum:
- 20 E&M codes (99201–99499 range) — `requires_auth: false`
- 15 imaging codes (70000–79999) — `requires_auth: true` for MRI/CT
- 10 surgical codes — `requires_auth: true`
- 15 PT/behavioral health codes (97xxx, 90xxx) — `requires_auth: true`
- 5 home health codes (G0299, G0300, etc.) — `requires_auth: true`

**`icd10_codes.csv` required columns:** `code`, `description`, `category`

Include: common chronic (diabetes, hypertension, COPD), acute (fractures, UTI, pneumonia), behavioral health (F codes), and musculoskeletal (M codes for PT).

**Validation:**
```bash
python -c "
import pandas as pd
cpt = pd.read_csv('data/reference/cpt_codes.csv')
icd = pd.read_csv('data/reference/icd10_codes.csv')
print(f'CPT codes: {len(cpt)} total, {cpt.requires_auth.sum()} auth-required')
print(f'ICD-10 codes: {len(icd)} total')
assert len(cpt) >= 50, 'Need at least 50 CPT codes'
assert cpt.requires_auth.sum() >= 20, 'Need at least 20 auth-required CPT codes'
assert len(icd) >= 40, 'Need at least 40 ICD-10 codes'
print('Reference data: OK')
"
```

- [ ] Step P1-2 complete

---

## Step P1-3: `detection_rules.yaml`

**Action:** Create `data/reference/detection_rules.yaml` with all 6 `DetectionRule` definitions.

**Required fields per rule:** `rule_id`, `name`, `category`, `severity`, `risk_type`, `description`, `applies_to`, `version`, `active`, `cypher`

Rule IDs: `DR-S01` through `DR-S06`. See `spec_03_scenarios.md` for Cypher patterns and `spec_04_app.md` for category values.

**Validation:**
```bash
python -c "
import yaml
with open('data/reference/detection_rules.yaml') as f:
    rules = yaml.safe_load(f)['rules']
assert len(rules) == 6, f'Expected 6 rules, got {len(rules)}'
required = ['rule_id','name','category','severity','risk_type','description','applies_to','version','active','cypher']
for r in rules:
    missing = [k for k in required if k not in r]
    assert not missing, f'Rule {r.get(\"rule_id\")} missing: {missing}'
print(f'detection_rules.yaml: {len(rules)} rules, all fields present — OK')
"
```

- [ ] Step P1-3 complete

---

## Step P1-4: `src/generate/domains.py`

**Action:** Implement `domains.py` — loads reference CSVs, defines payer mix, CPT auth list, specialty mix.

**Required exports:**
```python
def get_cpt_codes() -> pd.DataFrame           # loads cpt_codes.csv
def get_icd10_codes() -> pd.DataFrame         # loads icd10_codes.csv
def get_auth_required_cpts() -> list[str]     # CPT codes with requires_auth=True
def get_payer_definitions() -> list[dict]     # 6-8 payers with type and plan types
def get_specialty_mix() -> dict               # specialty → proportion (must hit DR-05)
```

**Validation:**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from generate.domains import get_cpt_codes, get_auth_required_cpts, get_payer_definitions, get_specialty_mix
cpts = get_cpt_codes()
auth_cpts = get_auth_required_cpts()
payers = get_payer_definitions()
spec = get_specialty_mix()

assert len(cpts) >= 50
assert len(auth_cpts) >= 20
assert len(payers) >= 6
hmo_payers = [p for p in payers if any(pt == 'HMO' for pt in p.get('plan_types', []))]
assert len(hmo_payers) >= 2, 'Need at least 2 HMO payers for S-06'
pt_bh = sum(v for k,v in spec.items() if k in ['PT','behavioral_health','home_health'])
assert pt_bh >= 0.18, f'PT/BH mix must be ~20%, got {pt_bh:.0%}'
print('domains.py: OK')
"
```

- [ ] Step P1-4 complete

---

## Step P1-5: `src/generate/generator.py`

**Action:** Implement the synthetic data generator. Outputs System A–E CSVs to `data/generated/`.

**Generation order** (must follow dependencies — see `spec_02_data.md`):
1. Payers + PayerPolicies (System C payer_master, insurance_plan)
2. Providers with specialty mix (System E provider_master)
3. Provider-payer contracts + version pairs for S-03 (System E provider_payer_contract, fee_schedule)
4. Patients with payer distribution (System A pt_demographics)
5. Coverages (System C member_eligibility)
6. Encounters (System A encounter)
7. Charge lines (System A charge_line, encounter_dx)
8. Claims (System B claim_header, claim_service_line)
9. Authorizations — ~30% of auth-required claims (System D auth_request, auth_detail)
10. claim_auth_link — intentionally 88–92% complete (System D)
11. Referral orders for HMO visits (System E referral_order)

**Validation:**
```bash
python src/generate/generator.py  # should complete in < 60 seconds

python -c "
import pandas as pd

# Volume checks
pt = pd.read_csv('data/generated/system_a_emr/pt_demographics.csv')
claims = pd.read_csv('data/generated/system_b_claims/claim_header.csv')
plans = pd.read_csv('data/generated/system_c_payer/insurance_plan.csv')
elig = pd.read_csv('data/generated/system_c_payer/member_eligibility.csv')
auth = pd.read_csv('data/generated/system_d_auth/auth_request.csv')
contracts = pd.read_csv('data/generated/system_e_provider/provider_payer_contract.csv')

assert 900 <= len(pt) <= 1100, f'Patient count off: {len(pt)}'
assert 4500 <= len(claims) <= 7000, f'Claim count off: {len(claims)}'

# HMO enrollment (DR-06)
hmo_plans = plans[plans.plan_type=='HMO']['plan_id']
hmo_pct = elig[elig.plan_id.isin(hmo_plans)]['mrn'].nunique() / elig['mrn'].nunique()
assert 0.22 <= hmo_pct <= 0.35, f'HMO enrollment {hmo_pct:.1%} out of range'

# Contract versioning for S-03
versioned = contracts[contracts.version_num > 1]
assert len(versioned) >= 5, f'Need versioned contracts for S-03: got {len(versioned)}'

# Auth link completeness (leave gap for S-01)
link = pd.read_csv('data/generated/system_d_auth/claim_auth_link.csv')
auth_req_claims = claims[claims.auth_number.notna()]
link_pct = link['claim_id'].nunique() / len(auth_req_claims)
assert 0.85 <= link_pct <= 0.95, f'Auth link completeness {link_pct:.1%} — adjust for S-01'

print('generator.py output: ALL CHECKS PASSED')
"
```

- [ ] Step P1-5 complete

---

## Step P1-6: `src/graph/connection.py`

**Action:** Implement Neo4j driver singleton with health check.

**Required exports:**
```python
def get_driver() -> neo4j.Driver   # cached singleton
def check_connection(driver) -> bool
```

**Validation:**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv()
from graph.connection import get_driver, check_connection
driver = get_driver()
ok = check_connection(driver)
assert ok, 'Connection check failed'
print('connection.py: OK')
driver.close()
"
```

- [ ] Step P1-6 complete

---

## Step P1-7: `src/graph/loader.py`

**Action:** Implement schema setup + baseline loader + detection rule loader.

**Required exports:**
```python
def setup_schema(driver) -> None          # creates constraints + indexes
def load_baseline(driver, data_dir) -> dict  # loads all CSVs, returns node counts
def load_detection_rules(driver, rules_path) -> int  # returns number of rules loaded
```

Use `UNWIND` batch loading (not single-row loops). Load order:
1. `setup_schema` (constraints + indexes)
2. CPT_Code and ICD10_Code nodes (from reference CSVs)
3. Payer nodes
4. PayerPolicy nodes + `HAS_POLICY` edges
5. Provider nodes
6. Contract nodes + `CONTRACTED_WITH` + `CONTRACT_WITH_PAYER` edges
7. `SUPERSEDED_BY` / `POLICY_SUPERSEDED_BY` edges (from version_num ordering)
8. Patient nodes
9. Coverage nodes + `ENROLLED_IN` + `COVERED_BY` edges
10. Visit nodes + `HAD_VISIT` edges
11. Claim nodes + `GENERATED_CLAIM` + `SUBMITTED_TO` + `BILLED_BY` edges
12. `BILLED_PROCEDURE` + `CODED_DIAGNOSIS` + `COVERED_UNDER` edges
13. Authorization nodes + `HAS_AUTHORIZATION` + `AUTH_GRANTED_BY` + `AUTH_FOR_PROCEDURE` edges
14. ReferralOrder nodes + `HAS_REFERRAL` + `REFERRED_BY` edges
15. `DetectionRule` nodes from YAML (`MERGE` on `rule_id`)

**Validation:**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv()
from graph.connection import get_driver
from graph.loader import setup_schema, load_baseline, load_detection_rules

driver = get_driver()
setup_schema(driver)
print('Schema setup: OK')

counts = load_baseline(driver, 'data/generated')
print('Node counts:', counts)
assert counts['Patient'] >= 900
assert counts['Claim'] >= 4500
assert counts['Provider'] >= 25

n_rules = load_detection_rules(driver, 'data/reference/detection_rules.yaml')
assert n_rules == 6, f'Expected 6 rules, got {n_rules}'
print(f'Detection rules loaded: {n_rules}')

# Verify in Neo4j Browser manually:
# MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC
# MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS count ORDER BY count DESC
# MATCH (dr:DetectionRule) RETURN dr.rule_id, dr.name, dr.active

driver.close()
print('loader.py: ALL CHECKS PASSED')
"
```

- [ ] Step P1-7 complete

---

## Step P1-8: `src/graph/flaw_injector.py`

**Action:** Implement all 6 inject functions plus `clear_all_flaws()`.

**Required exports:**
```python
def inject_s01(driver) -> dict  # returns {claims_affected, changes_summary, inventory}
def inject_s02(driver) -> dict
def inject_s03(driver) -> dict
def inject_s04(driver) -> dict
def inject_s05(driver) -> dict
def inject_s06(driver) -> dict
def clear_all_flaws(driver, inventory_by_scenario: dict) -> None
```

**Critical implementation rules:**
1. Tag Claims BEFORE modifying relationships
2. Store deleted relationship inventory (from/to node IDs + properties) before deleting
3. Return inventory in result dict so Streamlit can store in `session_state`
4. `clear_all_flaws()` restores relationships from inventory, then removes flaw tags, then deletes Findings

**Validation:**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv()
from graph.connection import get_driver
from graph.flaw_injector import inject_s01, inject_s02, clear_all_flaws

driver = get_driver()

# Test S-01 injection
result = inject_s01(driver)
print(f'S-01: {result[\"claims_affected\"]} claims affected')
assert result['claims_affected'] > 0

# Verify flaw tags in graph
with driver.session() as s:
    n = s.run(\"MATCH (c:Claim {flaw_scenario:'S-01'}) RETURN count(c) AS n\").single()['n']
    assert n > 0, 'S-01 flaw tags not found in graph'
    print(f'S-01 tagged claims in graph: {n}')

# Test S-02 injection
result2 = inject_s02(driver)
print(f'S-02: {result2[\"claims_affected\"]} claims affected')

# Verify isolation — S-01 and S-02 claims are distinct
with driver.session() as s:
    overlap = s.run(\"\"\"
        MATCH (c:Claim) WHERE c.flaw_scenario='S-01' AND c.flaw_scenario='S-02'
        RETURN count(c) AS n
    \"\"\").single()['n']
    assert overlap == 0, 'S-01 and S-02 tagged the same claims!'
    print('Scenario isolation: OK')

# Test clear
inventory = {'S-01': result['inventory'], 'S-02': result2['inventory']}
clear_all_flaws(driver, inventory)

with driver.session() as s:
    flawed = s.run(\"MATCH (c:Claim) WHERE c.is_flawed=true RETURN count(c) AS n\").single()['n']
    assert flawed == 0, f'Flaw tags remain after clear: {flawed}'
    print('clear_all_flaws: OK')

driver.close()
print('flaw_injector.py: ALL CHECKS PASSED')
"
```

- [ ] Step P1-8 complete

---

## Step P1-9: `src/graph/detection.py`

**Action:** Implement the detection rule runner.

**Required exports:**
```python
def run_rule(rule_id: str, driver) -> int        # returns finding count
def run_all_rules(driver) -> dict                # {rule_id: finding_count}
def get_finding_count(driver, status='open') -> int
```

**Implementation:** `run_rule()` reads the Cypher from the `DetectionRule` node in the graph (not from the YAML file directly) — this is what makes it a production architecture.

```python
def run_rule(rule_id, driver):
    with driver.session() as session:
        # Get Cypher from the DetectionRule node in the graph
        result = session.run(
            "MATCH (r:DetectionRule {rule_id: $id, active: true}) RETURN r.cypher AS cypher",
            id=rule_id
        )
        record = result.single()
        if not record:
            return 0
        # Execute the detection Cypher
        result2 = session.run(record['cypher'])
        record2 = result2.single()
        return record2['findings_created'] if record2 else 0
```

**Validation:**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv()
from graph.connection import get_driver
from graph.flaw_injector import inject_s01, inject_s02, clear_all_flaws
from graph.detection import run_rule, get_finding_count

driver = get_driver()

# Inject S-01 and run detection
inj = inject_s01(driver)
count = run_rule('DR-S01', driver)
print(f'DR-S01 findings created: {count}')
assert count > 0, 'No findings created for S-01'

# Verify Finding nodes have correct edges
with driver.session() as s:
    check = s.run('''
        MATCH (c:Claim)-[:HAS_FINDING]->(f:Finding)-[:TRIGGERED_BY]->(r:DetectionRule)
        WHERE r.rule_id = \"DR-S01\"
        RETURN count(f) AS n
    ''').single()['n']
    assert check == count, f'Finding edge count mismatch: {check} vs {count}'
    print(f'Finding edges (HAS_FINDING + TRIGGERED_BY): OK ({check} findings)')

open_count = get_finding_count(driver)
print(f'Open findings: {open_count}')
assert open_count == count

# Also test S-02
inj2 = inject_s02(driver)
count2 = run_rule('DR-S02', driver)
print(f'DR-S02 findings: {count2}')

total = get_finding_count(driver)
assert total == count + count2, f'Total finding count mismatch: {total}'

# Clean up
clear_all_flaws(driver, {'S-01': inj['inventory'], 'S-02': inj2['inventory']})
assert get_finding_count(driver) == 0, 'Findings remain after clear'
print('detection.py: ALL CHECKS PASSED')

driver.close()
"
```

- [ ] Step P1-9 complete

---

## Step P1-10: `src/graph/findings.py`

**Action:** Implement Finding CRUD functions.

**Required exports:**
```python
def list_findings(driver, status=None) -> list[dict]
def acknowledge_finding(finding_id: str, driver) -> None
def resolve_finding(finding_id: str, driver) -> None
def get_finding_subgraph(finding_id: str, driver) -> dict  # returns {nodes, edges}
```

**Validation:**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv()
from graph.connection import get_driver
from graph.flaw_injector import inject_s01
from graph.detection import run_rule
from graph.findings import list_findings, acknowledge_finding, resolve_finding

driver = get_driver()
inj = inject_s01(driver)
run_rule('DR-S01', driver)

findings = list_findings(driver, status='open')
print(f'Open findings: {len(findings)}')
assert len(findings) > 0

fid = findings[0]['finding_id']
acknowledge_finding(fid, driver)
updated = list_findings(driver, status='acknowledged')
assert any(f['finding_id'] == fid for f in updated), 'Acknowledge did not write to graph'
print('Acknowledge: OK')

resolve_finding(fid, driver)
with driver.session() as s:
    f = s.run('MATCH (f:Finding {finding_id: \$id}) RETURN f.status, f.resolved_at', id=fid).single()
    assert f['f.status'] == 'resolved'
    assert f['f.resolved_at'] is not None
print('Resolve: OK')

driver.close()
print('findings.py: ALL CHECKS PASSED')
"
```

- [ ] Step P1-10 complete

---

## Phase 1 gate review

Before proceeding to Phase 2, verify all manually in Neo4j Browser (`http://localhost:7474`):

```cypher
// Node counts
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC;

// Relationship counts
MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS count ORDER BY count DESC;

// Verify DetectionRule nodes
MATCH (dr:DetectionRule) RETURN dr.rule_id, dr.name, dr.severity, dr.active;

// Test S-01 path manually
MATCH (c:Claim)-[:BILLED_PROCEDURE]->(cpt:CPT_Code {requires_auth:true})
WHERE NOT EXISTS {
  MATCH (c)-[:HAS_AUTHORIZATION]->(a:Authorization)-[:AUTH_FOR_PROCEDURE]->(cpt)
  WHERE a.expiry_date >= c.claim_date
}
RETURN count(c) AS unverifiable_claims;

// After injecting S-01:
// inject_s01() then run_rule('DR-S01') in Python, then verify:
MATCH (f:Finding)-[:TRIGGERED_BY]->(r:DetectionRule {rule_id:'DR-S01'})
RETURN f.finding_id, f.severity, f.status LIMIT 5;
```

**Gate pass criteria:**
- [ ] All expected node and relationship types present in Neo4j Browser
- [ ] 6 `DetectionRule` nodes exist, all `active: true`
- [ ] S-01 injection creates tagged Claims + Finding nodes with correct edges
- [ ] S-02 injection does not affect S-01 findings (isolation confirmed)
- [ ] `clear_all_flaws()` returns graph to clean baseline
- [ ] All Phase 1 Python validation scripts pass

**→ Approve to proceed to Phase 2**
