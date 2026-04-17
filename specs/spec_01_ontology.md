# Spec 01 — Data Model & Ontology

**Read this file before implementing:** `loader.py`, `connection.py`, any Cypher query

---

## Node types (14 total)

| Node label | Key properties | Real-world analogue |
|------------|----------------|---------------------|
| `Patient` | `patient_id`, `dob`, `sex`, `zip` | Covered individual |
| `Visit` | `visit_id`, `visit_date`, `place_of_service`, `visit_type` | Single encounter |
| `Claim` | `claim_id`, `claim_date`, `billed_amount`, `claim_status`, `is_flawed` (bool), `flaw_scenario` (str) | Billing record |
| `CPT_Code` | `code`, `description`, `category`, `requires_auth` (bool) | CPT-4 procedure code |
| `ICD10_Code` | `code`, `description`, `category` | ICD-10-CM diagnosis code |
| `Payer` | `payer_id`, `payer_name`, `payer_type` | Insurance company |
| `PayerPolicy` | `policy_id`, `effective_date`, `termination_date`, `plan_type`, `version` | Benefit plan |
| `Coverage` | `coverage_id`, `start_date`, `end_date`, `member_id` | Patient enrollment |
| `Provider` | `provider_id`, `npi`, `name`, `specialty`, `provider_type` | Billing or rendering provider |
| `Contract` | `contract_id`, `effective_date`, `termination_date`, `fee_schedule_id`, `version_num` | Provider-payer contract |
| `Authorization` | `auth_id`, `auth_date`, `approved_units`, `expiry_date`, `status` | Prior auth approval |
| `ReferralOrder` | `referral_id`, `order_date`, `referring_provider_id` | Physician referral |
| `DetectionRule` | `rule_id`, `name`, `category`, `severity`, `risk_type`, `description`, `applies_to`, `version`, `active` | Named detection rule |
| `Finding` | `finding_id`, `detected_at`, `severity`, `status`, `description`, `estimated_risk_amount`, `resolved_at`, `resolution_note` | Detected violation instance |

### Finding.status values
- `open` — newly created by detection engine
- `acknowledged` — reviewed by user in UI
- `resolved` — closed; `resolved_at` timestamp set

### Claim flaw-tagging properties
Set by `flaw_injector.py` at injection time; removed by `clear_all_flaws()`:
- `is_flawed: true` (boolean)
- `flaw_scenario: 'S-01'` through `'S-06'`

---

## Relationship types (21 total)

| Relationship | From → To | Key properties |
|-------------|-----------|----------------|
| `HAD_VISIT` | Patient → Visit | — |
| `GENERATED_CLAIM` | Visit → Claim | — |
| `BILLED_PROCEDURE` | Claim → CPT_Code | `units` (int), `modifier` (str) |
| `CODED_DIAGNOSIS` | Claim → ICD10_Code | `dx_position` (`primary` / `secondary`) |
| `SUBMITTED_TO` | Claim → Payer | `submission_date` |
| `BILLED_BY` | Claim → Provider | `billing_role` (`billing` / `rendering`) |
| `COVERED_UNDER` | Claim → Coverage | — |
| `HAS_POLICY` | Payer → PayerPolicy | — |
| `COVERED_BY` | Coverage → PayerPolicy | — |
| `ENROLLED_IN` | Patient → Coverage | `enrollment_date` |
| `COVERS_PROCEDURE` | PayerPolicy → CPT_Code | `requires_auth` (bool), `coverage_pct`, `effective_date` |
| `CONTRACTED_WITH` | Provider → Contract | — |
| `CONTRACT_WITH_PAYER` | Contract → Payer | `effective_date`, `termination_date` |
| `HAS_AUTHORIZATION` | Claim → Authorization | — |
| `AUTH_GRANTED_BY` | Authorization → Payer | — |
| `AUTH_FOR_PROCEDURE` | Authorization → CPT_Code | — |
| `HAS_REFERRAL` | Claim → ReferralOrder | — |
| `REFERRED_BY` | ReferralOrder → Provider | — |
| `SUPERSEDED_BY` | Contract → Contract | links expired → replacement |
| `POLICY_SUPERSEDED_BY` | PayerPolicy → PayerPolicy | links expired → replacement |
| `HAS_FINDING` | Claim → Finding | — |
| `TRIGGERED_BY` | Finding → DetectionRule | — |

---

## Cypher constraints and indexes

Run exactly in this order during `loader.py` setup. Neo4j 5.x syntax.

```cypher
// Uniqueness constraints
CREATE CONSTRAINT patient_id_unique IF NOT EXISTS FOR (p:Patient) REQUIRE p.patient_id IS UNIQUE;
CREATE CONSTRAINT claim_id_unique    IF NOT EXISTS FOR (c:Claim)   REQUIRE c.claim_id   IS UNIQUE;
CREATE CONSTRAINT visit_id_unique    IF NOT EXISTS FOR (v:Visit)   REQUIRE v.visit_id   IS UNIQUE;
CREATE CONSTRAINT provider_npi_unique IF NOT EXISTS FOR (pr:Provider) REQUIRE pr.npi    IS UNIQUE;
CREATE CONSTRAINT payer_id_unique    IF NOT EXISTS FOR (py:Payer)  REQUIRE py.payer_id  IS UNIQUE;
CREATE CONSTRAINT policy_id_unique   IF NOT EXISTS FOR (pp:PayerPolicy) REQUIRE pp.policy_id IS UNIQUE;
CREATE CONSTRAINT cpt_code_unique    IF NOT EXISTS FOR (c:CPT_Code) REQUIRE c.code      IS UNIQUE;
CREATE CONSTRAINT icd10_code_unique  IF NOT EXISTS FOR (d:ICD10_Code) REQUIRE d.code    IS UNIQUE;
CREATE CONSTRAINT auth_id_unique     IF NOT EXISTS FOR (a:Authorization) REQUIRE a.auth_id IS UNIQUE;
CREATE CONSTRAINT rule_id_unique     IF NOT EXISTS FOR (r:DetectionRule) REQUIRE r.rule_id IS UNIQUE;
CREATE CONSTRAINT finding_id_unique  IF NOT EXISTS FOR (f:Finding) REQUIRE f.finding_id IS UNIQUE;

// Performance indexes
CREATE INDEX claim_date_idx         IF NOT EXISTS FOR (c:Claim) ON (c.claim_date);
CREATE INDEX claim_flaw_idx         IF NOT EXISTS FOR (c:Claim) ON (c.is_flawed, c.flaw_scenario);
CREATE INDEX coverage_dates_idx     IF NOT EXISTS FOR (c:Coverage) ON (c.start_date, c.end_date);
CREATE INDEX contract_dates_idx     IF NOT EXISTS FOR (c:Contract) ON (c.effective_date, c.termination_date);
CREATE INDEX policy_dates_idx       IF NOT EXISTS FOR (p:PayerPolicy) ON (p.effective_date, p.termination_date);
CREATE INDEX finding_status_idx     IF NOT EXISTS FOR (f:Finding) ON (f.status);
CREATE INDEX finding_detected_idx   IF NOT EXISTS FOR (f:Finding) ON (f.detected_at);
```

> **Note:** Neo4j 5.x uses `FOR ... REQUIRE` syntax, not the deprecated `ON (x) ASSERT`. Use `IF NOT EXISTS` so loader is idempotent (safe to run twice).

---

## Node color palette (used across all panels)

| Node type | Hex color | Label |
|-----------|-----------|-------|
| Patient | `#4a90d9` | blue |
| Visit | `#5ba55b` | green |
| Claim | `#e08c2a` | amber (flawed) / `#888` (clean) |
| Provider | `#9b59b6` | purple |
| Payer | `#2eacb0` | teal |
| PayerPolicy | `#17849c` | dark teal |
| Coverage | `#aed6f1` | light blue |
| Authorization | `#f39c12` | orange |
| ReferralOrder | `#e74c3c` | red |
| CPT_Code | `#95a5a6` | grey |
| ICD10_Code | `#bdc3c7` | light grey |
| Contract | `#7f8c8d` | dark grey |
| DetectionRule | `#4a3b7a` | dark purple |
| Finding | `#a02828` | deep red |

---

## Key path patterns for detection queries

```
// Auth chain (S-01)
(c:Claim)-[:BILLED_PROCEDURE]->(cpt:CPT_Code {requires_auth:true})
(c)-[:HAS_AUTHORIZATION]->(a:Authorization)-[:AUTH_FOR_PROCEDURE]->(cpt)

// Rendering provider credentialing (S-02)
(c:Claim)-[:BILLED_BY {billing_role:'rendering'}]->(rp:Provider)
(rp)-[:CONTRACTED_WITH]->(con:Contract)-[:CONTRACT_WITH_PAYER]->(py:Payer)
(c)-[:SUBMITTED_TO]->(py)

// Contract version chain (S-03)
(c:Claim) ... (con:Contract)-[:SUPERSEDED_BY]->(newer:Contract)

// Auth unit exhaustion (S-04) — per-claim, 1:1 claim-to-auth
(c:Claim {flaw_scenario:'S-04'})-[:HAS_AUTHORIZATION]->(a:Authorization)
(c)-[r:BILLED_PROCEDURE]->(:CPT_Code)
WITH c, a, sum(r.units) AS total_units WHERE total_units > a.approved_units

// Duplicate identity (S-05)
(p1:Patient) & (p2:Patient) share Provider + Payer, near-matching dob + same zip

// HMO referral chain (S-06)
(c:Claim)-[:COVERED_UNDER]->(cov)-[:COVERED_BY]->(pp:PayerPolicy {plan_type:'HMO'})
(c)-[:HAS_REFERRAL]->(ro:ReferralOrder)-[:REFERRED_BY]->(pcp:Provider)
```
