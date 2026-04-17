# KG Data Quality Demo — Requirements Document

**Project:** Healthcare RCM Knowledge Graph Demo Application  
**Audience:** Internal POC — xVector team  
**Stack:** Python · Neo4j · Streamlit  
**Status:** Draft v3 — Production detection architecture adopted  
**Date:** April 2026

---

## TL;DR

Build a three-phase desktop demo that showcases a production-grade detection architecture — not just a DQ query tool. Generate synthetic RCM data assembled from five realistic source system schemas and load it into a local Neo4j graph. Build a five-panel Streamlit app: Ontology Explorer, Rule Library, KG Foundation, Scenario Loader, and Findings Dashboard. A structured library of six detection rules runs automatically on data arrival, writes `Finding` nodes back into the graph, and surfaces anomalies before a single claim is worked. The demo narrative is continuous ontology-anchored monitoring — Beat 3 of the xVector cross-cutting pitch — made concrete and operational.

---

## §01 Purpose & Goals

### Primary goal

Produce a working, locally runnable demo that an xVector team member can walk through in 15–20 minutes to illustrate how ontology-anchored data quality monitoring works in the healthcare RCM context. The demo must be credible to an informed RCM audience (coding, denial management, RCM ops leadership).

### Secondary goals

- Establish a reusable foundation — synthetic data generator, graph loader, flaw injector, app shell — that can be adapted for client-facing demos without rebuilding from scratch.
- Validate feasibility of the full xVector KG-DQ capability on real data before a Synergen or similar engagement begins.

### Explicit non-goals

This application is **not** a production system, a live data pipeline, an LLM-driven component, or a client-facing deliverable. It does not need authentication, multi-user support, deployment infrastructure, or HIPAA compliance (all data is synthetic). Natural-language query over the graph is explicitly out of scope per the strategy doc.

---

## §02 Scope & Constraints

### In scope

| ID | Requirement | Priority |
|----|-------------|----------|
| SC-01 | Synthetic RCM dataset generator — produces a realistic clean "golden" baseline covering patients, visits, claims, CPT codes, ICD-10 codes, payers, payer policies, providers, contracts, and prior authorizations | **Must** |
| SC-02 | Neo4j graph loader — ingests datasets, creates ontology constraints and indexes, loads nodes and relationships in correct dependency order | **Must** |
| SC-03 | Flaw injection engine — takes the clean baseline and produces six distinct trial datasets, each with a different class of data quality anomaly | **Must** |
| SC-04 | Streamlit app with four panels: Ontology Explorer, KG Foundation, Trial Dataset Loader, DQ Anomaly Report | **Must** |
| SC-05 | Narrative annotations per scenario — each anomaly includes plain-English explanation of (a) what the flaw is, (b) why rule-based DQ misses it, (c) how the graph detects it | **Should** |
| SC-06 | Summary metrics dashboard — scorecard per trial dataset showing total claims, flagged count, and estimated denial risk | **Nice to have** |

### Out of scope

| ID | Item |
|----|------|
| OOS-01 | LLM / AI components of any kind — all detection logic is explicit Cypher queries |
| OOS-02 | Real or anonymized patient data — all data is fully synthetic |
| OOS-03 | Cloud deployment, multi-user support, or authentication |
| OOS-04 | Real-time or streaming data ingestion |
| OOS-05 | Export, reporting, HL7/FHIR integration, or external system connections |

### Desktop constraints (hard limits)

| ID | Constraint | Limit |
|----|-----------|-------|
| HC-01 | Neo4j heap ceiling | ≤ 4 GB (configured in `neo4j.conf`) |
| HC-02 | KG load time (any dataset) | ≤ 60 seconds |
| HC-03 | Anomaly detection query response | ≤ 5 seconds per query |
| HC-04 | Graph visualization node limit | ≤ 500 nodes rendered at once — always subgraphs, never full dataset |

---

## §03 Data Model & Ontology

The ontology defines the entities, relationships, and properties that constitute the knowledge graph. It is the "ontology of record" against which data quality drift is detected.

### Node types

| Node label | Key properties | Real-world analogue |
|------------|----------------|---------------------|
| `Patient` | `patient_id`, `dob`, `sex`, `zip` | The covered individual receiving care |
| `Visit` | `visit_id`, `visit_date`, `place_of_service`, `visit_type` | A single encounter or service event |
| `Claim` | `claim_id`, `claim_date`, `billed_amount`, `claim_status` | The billing record submitted to a payer |
| `CPT_Code` | `code`, `description`, `category`, `requires_auth` | Procedure / service code (CPT-4) |
| `ICD10_Code` | `code`, `description`, `category` | Diagnosis code (ICD-10-CM) |
| `Payer` | `payer_id`, `payer_name`, `payer_type` | Insurance company or government payer |
| `PayerPolicy` | `policy_id`, `effective_date`, `termination_date`, `plan_type`, `version` | Specific benefit plan with effective date range |
| `Coverage` | `coverage_id`, `start_date`, `end_date`, `member_id` | Patient enrollment in a specific policy |
| `Provider` | `provider_id`, `npi`, `name`, `specialty`, `provider_type` | Billing or rendering provider |
| `Contract` | `contract_id`, `effective_date`, `termination_date`, `fee_schedule`, `version_num` | Provider-payer reimbursement contract |
| `Authorization` | `auth_id`, `auth_date`, `approved_units`, `expiry_date`, `auth_status` | Prior authorization approval from payer |
| `ReferralOrder` | `referral_id`, `order_date`, `referring_provider_id` | Physician referral required for HMO specialist visits |
| `DetectionRule` | `rule_id`, `name`, `category`, `severity`, `risk_type`, `description`, `applies_to`, `version`, `active` | A named, versioned detection rule in the monitoring library |
| `Finding` | `finding_id`, `detected_at`, `severity`, `status`, `description`, `estimated_risk_amount`, `resolved_at` | A detected violation instance written to the graph by a detection rule |

### Relationship types

| Relationship | From → To | Key properties |
|-------------|-----------|----------------|
| `HAD_VISIT` | Patient → Visit | — |
| `GENERATED_CLAIM` | Visit → Claim | — |
| `BILLED_PROCEDURE` | Claim → CPT_Code | `units`, `modifier` |
| `CODED_DIAGNOSIS` | Claim → ICD10_Code | `dx_position` (primary / secondary) |
| `SUBMITTED_TO` | Claim → Payer | `submission_date` |
| `BILLED_BY` | Claim → Provider | `billing_role` (billing / rendering) |
| `COVERED_UNDER` | Claim → Coverage | — |
| `HAS_POLICY` | Payer → PayerPolicy | — |
| `COVERED_BY` | Coverage → PayerPolicy | — |
| `ENROLLED_IN` | Patient → Coverage | `enrollment_date` |
| `COVERS_PROCEDURE` | PayerPolicy → CPT_Code | `requires_auth`, `coverage_pct`, `effective_date` |
| `CONTRACTED_WITH` | Provider → Contract | — |
| `CONTRACT_WITH_PAYER` | Contract → Payer | `effective_date`, `termination_date` |
| `HAS_AUTHORIZATION` | Claim → Authorization | — |
| `AUTH_GRANTED_BY` | Authorization → Payer | — |
| `AUTH_FOR_PROCEDURE` | Authorization → CPT_Code | — |
| `HAS_REFERRAL` | Claim → ReferralOrder | — |
| `REFERRED_BY` | ReferralOrder → Provider | — |
| `SUPERSEDED_BY` | Contract → Contract | — *(links expired version to its replacement; enables version chain traversal)* |
| `POLICY_SUPERSEDED_BY` | PayerPolicy → PayerPolicy | — *(links expired policy version to replacement)* |
| `HAS_FINDING` | Claim → Finding | A detection rule produced a violation finding on this claim |
| `TRIGGERED_BY` | Finding → DetectionRule | The rule that produced this finding |

### Ontology constraints (enforced in Neo4j at load time)

```cypher
// Uniqueness constraints
CREATE CONSTRAINT ON (p:Patient)      ASSERT p.patient_id  IS UNIQUE;
CREATE CONSTRAINT ON (c:Claim)        ASSERT c.claim_id    IS UNIQUE;
CREATE CONSTRAINT ON (v:Visit)        ASSERT v.visit_id    IS UNIQUE;
CREATE CONSTRAINT ON (pr:Provider)    ASSERT pr.npi        IS UNIQUE;
CREATE CONSTRAINT ON (py:Payer)       ASSERT py.payer_id   IS UNIQUE;
CREATE CONSTRAINT ON (pp:PayerPolicy) ASSERT pp.policy_id  IS UNIQUE;
CREATE CONSTRAINT ON (cpt:CPT_Code)   ASSERT cpt.code      IS UNIQUE;
CREATE CONSTRAINT ON (dx:ICD10_Code)  ASSERT dx.code       IS UNIQUE;
CREATE CONSTRAINT ON (a:Authorization) ASSERT a.auth_id    IS UNIQUE;

// Uniqueness constraints — detection infrastructure
CREATE CONSTRAINT ON (dr:DetectionRule) ASSERT dr.rule_id    IS UNIQUE;
CREATE CONSTRAINT ON (f:Finding)        ASSERT f.finding_id  IS UNIQUE;

// Indexes for query performance
CREATE INDEX ON :Claim(claim_date);
CREATE INDEX ON :Claim(is_flawed, flaw_scenario);
CREATE INDEX ON :Coverage(start_date, end_date);
CREATE INDEX ON :Contract(effective_date, termination_date);
CREATE INDEX ON :PayerPolicy(effective_date, termination_date);
CREATE INDEX ON :Finding(status);
CREATE INDEX ON :Finding(detected_at);
```

---

## §04 Synthetic Data Specification

### Baseline ("golden") dataset volumes

| Entity type | Target count | Rationale |
|------------|-------------|-----------|
| Patient | 1,000 | Realistic patient mix across payers |
| Visit | 4,000–5,000 | ~4–5 visits per patient (chronic + acute mix) |
| Claim | 5,000–6,000 | Some visits generate multiple claims (split billing) |
| CPT_Code | 50–80 distinct | E&M, procedures, imaging subset |
| ICD10_Code | 40–60 distinct | Common chronic and acute diagnosis codes |
| Payer | 6–8 | Medicare, Medicaid, 4–6 commercial payers |
| PayerPolicy | 12–20 | 2–3 plan versions per payer (enables drift scenarios) |
| Provider | 30–40 | Mix of PCPs, specialists, facilities |
| Contract | 20–30 | Provider-payer pairings, some with historical versions |
| Authorization | ~800 | Attached to ~30% of claims with auth-required CPTs |
| ReferralOrder | ~400 | Attached to HMO-plan specialist visits |
| Coverage | ~1,200 | Some patients have coverage gaps or transitions |
| DetectionRule | 6 | One node per detection rule; loaded from `detection_rules.yaml` at startup |
| Finding | Created at runtime | Written to graph by detection engine on scenario injection; 0 on clean baseline |
| **Total nodes (est.)** | **~13,000–14,006** | Well within Neo4j Community desktop performance |
| **Total relationships (est.)** | **~35,000–40,000+** | Finding nodes add `HAS_FINDING` and `TRIGGERED_BY` edges at runtime |

### Data realism requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| DR-01 | CPT and ICD-10 codes must be drawn from real, valid code sets with correct descriptions | **Must** |
| DR-02 | CPT codes requiring prior authorization must reflect real-world payer behavior (e.g., MRI, surgical procedures) — hard-coded list, documented | **Must** |
| DR-03 | Patient demographics should reflect realistic age/sex/payer distributions: ~40% Medicare/Medicaid, ~35% commercial PPO, ~25% commercial HMO | **Should** |
| DR-04 | All names and identifiers must be fictional — Faker for names, synthetic NPIs that do not match real CMS NPI records | **Should** |
| DR-05 | Specialty mix must include PT/behavioral health/home health at ~20% of encounters to support S-04 (Auth Unit Exhaustion) | **Must** |
| DR-06 | HMO plan enrollment must represent ~25–30% of patients to give S-06 (Missing Referral) meaningful volume | **Must** |

---

### Source system schemas

The synthetic data is generated as flat relational tables that mimic the actual source systems feeding a real RCM operation. The graph is then assembled by ETL across all five systems — exactly as it would be in a live engagement. This is a key part of the demo story: the anomalies exist *because* these systems are maintained independently by different teams on different schedules, and the cross-system relationships are never jointly validated.

#### Source system overview

| System | Role in RCM | Typical vendors / formats | Tables produced |
|--------|------------|--------------------------|-----------------|
| **EMR / EHR** | Patient demographics, encounters, diagnoses, charge capture | Epic Clarity, Cerner CCL export, Meditech, Athenahealth | `pt_demographics`, `encounter`, `encounter_dx`, `charge_line` |
| **Practice Management / Claims** | Claim header and service line data, status tracking | Epic Resolute, Waystar, AdvancedMD, Kareo; EDI 837P/I-derived flat files | `claim_header`, `claim_service_line` |
| **Payer / Clearinghouse** | Insurance plans, member eligibility, remittance | Waystar, Availity, Change Healthcare; 270/271 eligibility, 835 ERA | `payer_master`, `insurance_plan`, `member_eligibility` |
| **Authorization Management** | Prior auth requests, approvals, unit limits | AIM Specialty Health, eviCore, payer portals, in-house tracking | `auth_request`, `auth_detail`, `claim_auth_link` |
| **Provider Credentialing & Contracts** | Provider enrollment, payer contracts, fee schedules, referrals | CAQH ProView, Symplr, in-house contract DB | `provider_master`, `provider_payer_contract`, `fee_schedule`, `referral_order` |

#### Detailed table schemas

**System A — EMR / EHR (Epic Clarity-style export)**

| Table | Key fields |
|-------|-----------|
| `pt_demographics` | `mrn`, `last_name`, `first_name`, `dob`, `sex`, `zip`, `ssn_last4`, `race`, `language`, `create_date` |
| `encounter` | `encounter_id`, `mrn`, `encounter_date`, `encounter_type`, `place_of_service`, `rendering_npi`, `facility_id`, `admit_date`, `discharge_date` |
| `encounter_dx` | `encounter_id`, `dx_code`, `dx_description`, `dx_position` (1=primary), `poa_flag` |
| `charge_line` | `charge_id`, `encounter_id`, `cpt_code`, `cpt_modifier`, `units`, `charge_date`, `charge_amount`, `revenue_code` |

**System B — Practice Management / Claims (CMS-1500 / 837P-derived)**

| Table | Key fields |
|-------|-----------|
| `claim_header` | `claim_id`, `mrn`, `member_id`, `billing_npi`, `rendering_npi`, `referring_npi`, `payer_id`, `plan_id`, `claim_date`, `total_billed`, `claim_type`, `claim_status`, `auth_number` *(free-text field — not a validated FK)* |
| `claim_service_line` | `line_id`, `claim_id`, `cpt_code`, `modifier`, `icd10_primary`, `icd10_secondary`, `units`, `line_billed`, `service_date` |

**System C — Payer / Clearinghouse**

| Table | Key fields |
|-------|-----------|
| `payer_master` | `payer_id`, `payer_name`, `payer_type` (commercial/Medicare/Medicaid/MCO), `clearinghouse_id` |
| `insurance_plan` | `plan_id`, `payer_id`, `plan_name`, `plan_type` (HMO/PPO/EPO/POS), `effective_date`, `term_date`, `version_num` |
| `member_eligibility` | `eligibility_id`, `mrn`, `member_id`, `plan_id`, `start_date`, `end_date`, `copay`, `deductible`, `group_number` |

**System D — Authorization Management**

| Table | Key fields |
|-------|-----------|
| `auth_request` | `auth_id`, `mrn`, `payer_id`, `requesting_npi`, `auth_date`, `expiry_date`, `status` (approved/denied/pending), `approved_units` |
| `auth_detail` | `auth_detail_id`, `auth_id`, `cpt_code`, `icd10_code`, `approved_units` |
| `claim_auth_link` | `claim_id`, `auth_id`, `linked_date` *(join table — frequently incomplete; the gap this creates is what S-01 detects)* |

**System E — Provider Credentialing & Contracts**

| Table | Key fields |
|-------|-----------|
| `provider_master` | `npi`, `last_name`, `first_name`, `specialty`, `provider_type` (physician/facility/mid-level), `tax_id`, `license_state`, `license_num`, `excluded_flag` |
| `provider_payer_contract` | `contract_id`, `npi`, `payer_id`, `contract_type` (par/non-par), `effective_date`, `term_date`, `fee_schedule_id`, `version_num` |
| `fee_schedule` | `fee_schedule_id`, `cpt_code`, `allowed_amount`, `effective_date` |
| `referral_order` | `referral_id`, `mrn`, `referring_npi`, `referred_to_npi`, `plan_id`, `referral_date`, `expiry_date`, `cpt_code` |

---

## §05 Anomaly Scenarios

Six scenarios. All six are common, recognized problems in day-to-day RCM operations — not edge cases invented to demonstrate graph value. The graph's advantage is that it detects them *systematically and at scale* by traversing cross-system relationships that no single source system and no column-level DQ tool can see jointly. Each scenario is rooted in a real denial or underpayment category that any RCM operations director will immediately recognize.

**Demo narrative principle:** Lead every scenario with the business pain the ops team already feels, then show that the graph detects it. The graph is the mechanism — not the story.

### Scenario credibility summary

| ID | Scenario | Business impact | Real-world frequency | Why standard tools miss it |
|----|----------|----------------|---------------------|---------------------------|
| S-01 | Prior Auth — Unverifiable Auth Chain | Top-3 denial reason; 44% growth in Medicare Advantage denials 2019–2022 (KFF) | Very high — all specialties with auth-required procedures | `auth_number` field appears populated on the claim; the cross-system auth-to-claim link table is incomplete and not systematically validated at submission |
| S-02 | Rendering Provider Not Credentialed with Billed Payer | Common denial category in large employed-physician groups, academic centers, locum tenens | High — especially during physician onboarding and mid-year credentialing changes | Credentialing systems validate prospectively; no standard claim scrubber checks the rendering NPI independently against the payer contract table at submission time |
| S-03 | Fee Schedule / Contract Version Still Active After Renewal | Underpayments accumulate silently over high claim volume; typically caught only at quarterly reconciliation | High — every contract renewal cycle introduces risk | New contract rows are added without deactivating old rows; both appear valid in the contracts table; no standard claim editor traverses the version chain |
| S-04 | Authorization Unit Exhaustion Across Multiple Claims | Direct denial and overpayment risk; most acute in PT, behavioral health, home health, radiation oncology | Very high in units-based specialties | Each individual claim looks valid; aggregate billed units across all claims linked to one auth is almost never computed at the point of submission |
| S-05 | Duplicate Patient Identity Across Source Systems | Claim splits, payment misapplication, care coordination failures; 8–12% duplicate MRN rate industry-wide (AHIMA) | Very high — universal in health systems receiving data from multiple source systems | Field-level deduplication fails on name/DOB variations; network-level signals (shared provider, payer, zip + overlapping dates) require cross-record graph traversal |
| S-06 | Invalid HMO Referral Chain | Top denial reason for HMO-heavy practices; requires retroactive correction and resubmission | High for practices with significant HMO enrollment (25–30% of payer mix) | `referral_id` may be populated but four simultaneous conditions — PCP specialty, active HMO contract, referral date before visit, correct plan type — are never jointly validated |

---

### S-01 — Prior Authorization: Unverifiable Auth Chain

**Business framing:** *"We have an auth number on the claim. The payer denied it anyway because they can't match the auth to this patient's procedure. We don't know if the auth was even for the right thing."*

**Risk type:** Denial  
**Source systems involved:** System B (claim_header has free-text `auth_number`) ↔ System D (auth_request, auth_detail, claim_auth_link)

**What the flaw is:** The claim has an `auth_number` value in `claim_header` — it looks fine in any column check. But `claim_auth_link` has no corresponding row linking that claim to a validated authorization record. Or the link exists, but the `auth_detail` row shows the auth was approved for a different CPT code than what was billed. The graph exposes both gaps as missing or broken path segments.

**Why standard tools miss it:** A column check confirms `auth_number IS NOT NULL`. A simple `claim_auth_link` JOIN confirms a row exists. Neither check validates that the auth covers the right patient, the right procedure, was granted by the correct payer, and has not expired — all of which require traversing the full 4-hop path in the graph.

**Cypher detection pattern:** Find Claims where `BILLED_PROCEDURE → CPT_Code[requires_auth=true]` and either (A) no `HAS_AUTHORIZATION` relationship exists, or (B) the Authorization reached has no `AUTH_FOR_PROCEDURE` edge to the matching CPT_Code, or (C) `Authorization.expiry_date < Claim.claim_date`.

**Flaw injection:** For 8–12% of auth-required claims: (A) remove `claim_auth_link` row entirely — auth_number still present as text, (B) leave the link but point `auth_detail` to a different CPT code, (C) set auth expiry before the service date.

---

### S-02 — Rendering Provider Not Credentialed with Billed Payer

**Business framing:** *"The claim went out under our group NPI, which is contracted. But the doctor who actually saw the patient isn't enrolled with this payer. We're getting CO-4 denials and don't know which claims are affected."*

**Risk type:** Denial (CO-4: Service not covered by this payer / provider not enrolled)  
**Source systems involved:** System B (claim_header has `billing_npi` and `rendering_npi` as separate fields) ↔ System E (provider_payer_contract)

**What the flaw is:** `claim_header.billing_npi` is contracted with the payer — that check passes. `claim_header.rendering_npi` is a different NPI (the physician who performed the service) and has no active row in `provider_payer_contract` for this payer. In the graph: the Claim has two `BILLED_BY` relationships — one with `billing_role = 'billing'`, one with `billing_role = 'rendering'`. The rendering Provider node has no `CONTRACTED_WITH → Contract → CONTRACT_WITH_PAYER → Payer` path to the claim's Payer. The path simply doesn't exist.

**Why standard tools miss it:** Standard claim scrubbers validate the billing NPI against the payer network. Checking the rendering NPI *independently* against the same payer's contract table requires knowing to join `provider_payer_contract` a second time on the rendering NPI — a separate join that most claim editing systems do not perform. The graph makes both provider nodes' contract paths visible from the same claim node simultaneously.

**Cypher detection pattern:** Find Claims where the Provider reached via `BILLED_BY[billing_role='rendering']` has no `CONTRACTED_WITH → Contract → CONTRACT_WITH_PAYER` path to the Payer reached via `SUBMITTED_TO`, with contract `effective_date ≤ claim_date ≤ term_date`.

**Flaw injection:** Add 5–8 provider nodes as rendering-only physicians with no `provider_payer_contract` rows for 1–2 specific payers. Assign them as rendering providers on 8–12% of claims submitted to those payers.

---

### S-03 — Fee Schedule / Contract Version Still Active After Renewal

**Business framing:** *"We renegotiated our BCBS contract in Q1. Our system still has the old fee schedule. We've been billing against 2022 rates for six months and only caught it in the quarterly reconciliation."*

**Risk type:** Underpayment  
**Source systems involved:** System E (provider_payer_contract has `version_num` and both old and new rows) ↔ System B (claims still reference the old `contract_id`)

**What the flaw is:** When a contract is renewed, a new row is inserted in `provider_payer_contract` with a new `contract_id`, new `version_num`, and new `effective_date`. The old row is not deactivated — it remains with a `term_date` that may not be set, or is set incorrectly. Claims generated after the renewal date still carry the old `contract_id` because the billing system was not updated. In the graph, the old Contract node has an outgoing `SUPERSEDED_BY` edge pointing to the new Contract node. Any Claim whose path resolves to a Contract with an outgoing `SUPERSEDED_BY` edge — regardless of date — is using a superseded version.

**Why standard tools miss it:** The old contract row still exists in the source table and may still have a technically valid date range if `term_date` was not set precisely. A date range query returns both rows as candidates; without version chain awareness, the system uses whichever row was loaded first or has the higher `contract_id`. The graph's `SUPERSEDED_BY` relationship makes version chain traversal a single pattern match.

**Cypher detection pattern:** Find Claims where the Contract reached via `BILLED_BY → Provider → CONTRACTED_WITH → Contract` has an outgoing `SUPERSEDED_BY` relationship — i.e., the claim is on an old version that has been replaced. Also detect claims where `PayerPolicy` reached via `COVERED_UNDER → Coverage → COVERED_BY → PayerPolicy` has an outgoing `POLICY_SUPERSEDED_BY` edge.

**Flaw injection:** Create new `version_num = 2` Contract and PayerPolicy nodes for 2–3 payers, connect old→new via `SUPERSEDED_BY` / `POLICY_SUPERSEDED_BY`. Leave 10–15% of post-renewal claims still pointing to the old (now superseded) Contract or PayerPolicy nodes.

---

### S-04 — Authorization Unit Exhaustion Across Multiple Claims

**Business framing:** *"The auth was approved for 12 PT visits. We billed 16. Each claim looked fine individually. The payer paid the first 12 and denied the last four — but we didn't catch it until the remittance came back."*

**Risk type:** Denial / Overpayment risk  
**Source systems involved:** System D (auth_request.approved_units, claim_auth_link) ↔ System B (claim_service_line.units)

**What the flaw is:** `auth_request.approved_units = 12` for a physical therapy authorization. Four separate claims are linked to this auth via `claim_auth_link`, each with 3–5 service line units. Summing `claim_service_line.units` across all four claims gives 16 total — exceeding the 12 approved. Each claim in isolation passes all edits. The excess is only visible by aggregating across the network of claims connected to one Authorization node.

**Why standard tools miss it:** Claim editing systems validate each claim independently at submission. Aggregating billed units across all claims linked to a single auth at submission time requires a GROUP BY query joining `claim_auth_link → claim_service_line`, filtered by auth_id — a query that is rarely implemented in real-time claim scrubbers because it requires holding state across multiple claim submissions. In the graph, this is a single traversal: Authorization → all connected Claims → sum of `BILLED_PROCEDURE.units`.

**Cypher detection pattern:** Find Authorization nodes where the sum of `units` across all `BILLED_PROCEDURE` relationships on Claims connected via `HAS_AUTHORIZATION` exceeds `Authorization.approved_units`.

**Flaw injection:** For 15–20 authorizations in PT/behavioral health/home health claims, set `approved_units` to a value that will be exceeded when all linked claim lines are summed. Link 3–5 claims per auth through `claim_auth_link`, with combined units 20–40% over the approved ceiling.

---

### S-05 — Duplicate Patient Identity Across Source Systems

**Business framing:** *"The patient registered at two different facilities. They have two MRNs. Half their claims are under one ID, half under the other. We're failing coordination of benefits checks and missing authorization limits because we can't see the full picture."*

**Risk type:** Entity integrity / Payment error  
**Source systems involved:** System A (pt_demographics — two rows for same patient with different MRNs and slight property variations)

**What the flaw is:** The same real-world patient was registered twice — "Robert Smith" with DOB 1962-03-14 at one facility (MRN-1001) and "Bob Smith" with DOB 1962-03-41 (transposed digits) at another (MRN-2847). Both records passed column-level uniqueness checks because no exact field matches. In the graph, the two Patient nodes share multiple relationship targets: same Payer, same rendering Provider, same zip code, overlapping Visit date ranges. That network overlap is the detection signal.

**Why standard tools miss it:** Fuzzy name matching (`SOUNDEX`, `Levenshtein`) catches some variations but generates high false-positive rates and is rarely run across the full patient table in real time. More importantly, it only compares demographic fields in isolation. The graph adds network-level signals — a pair of patients who share 3+ relationship targets (same provider, same payer, same zip, near-matching DOB) are far more likely to be duplicates than demographic similarity alone suggests.

**Cypher detection pattern:** Find pairs of Patient nodes where `dob` values are within 5 days of each other AND `zip` matches AND both nodes share at least two relationship targets (same Provider or same Payer in their claim networks) AND `patient_id` values are different.

**Flaw injection:** Duplicate 30–50 Patient nodes with Faker-generated name variations (nickname substitution, initial vs. full name) and a single-digit DOB transposition. Split each duplicated patient's Claims approximately 60/40 between the two identity nodes.

---

### S-06 — Invalid HMO Referral Chain

**Business framing:** *"We got a CO-96 denial — referral required. We have a referral ID on the claim. But it turns out the referring doctor isn't a PCP on this patient's HMO network, and the referral was dated two days after the visit."*

**Risk type:** Denial (CO-96: Non-covered charge / referral required)  
**Source systems involved:** System B (claim_header.referring_npi) ↔ System C (insurance_plan.plan_type = HMO) ↔ System E (referral_order, provider_payer_contract)

**What the flaw is:** Four conditions must all be true for a valid HMO referral: (1) the Coverage is an HMO plan type, (2) the rendering Provider is a specialist (not a PCP), (3) a ReferralOrder exists and its `order_date` is on or before the Visit date, (4) the referring Provider in the ReferralOrder is a PCP contracted with the same HMO. The flaw is that `claim_header.referring_npi` is populated — a column check passes — but one or more of these four conditions fails when the full relationship chain is traversed.

**Why standard tools miss it:** A column check confirms `referring_npi IS NOT NULL`. Validating all four conditions simultaneously requires joining `insurance_plan` (plan type), `provider_master` (specialty of rendering provider), `referral_order` (date), and `provider_payer_contract` (PCP contracted with HMO) — four tables, each with different cardinality, with a conditional logic chain that most claim editors do not implement in combination. The graph expresses all four as path existence conditions on the same claim node.

**Cypher detection pattern:** Find Claims where `COVERED_UNDER → Coverage → COVERED_BY → PayerPolicy[plan_type='HMO']` AND rendering `Provider[provider_type='specialist']` AND one of: (A) no `HAS_REFERRAL` relationship exists, (B) `ReferralOrder.order_date > Visit.visit_date`, (C) the referring Provider reached via `REFERRED_BY` has no `CONTRACTED_WITH → Contract → CONTRACT_WITH_PAYER` path to the same Payer AND `Provider[specialty != 'PCP']`.

**Flaw injection:** For 8–12% of HMO specialist claims, inject one of three sub-types: (A) remove `HAS_REFERRAL` entirely while leaving `referring_npi` in the source table, (B) set `referral_order.referral_date` 2–5 days after the encounter date, (C) assign a referring provider who is a specialist (not PCP) or not contracted with that HMO. Each sub-type is labeled in the trial dataset for the demo.

---

## §06 Application Requirements

The app has five panels. The demo flows linearly through them: Ontology → Rule Library → KG Foundation → Scenario Loader → Findings Dashboard. Each panel builds on the previous one in the narrative arc.

### Demo narrative arc (5 beats)

1. **Ontology Explorer** — *"Here is the semantic model of your revenue cycle — every entity and relationship that governs how a clean claim looks."*
2. **Rule Library** — *"Here are the detection rules configured for this context. Each one is a named, versioned graph traversal. Zero findings right now — the baseline is clean."*
3. **KG Foundation** — *"Here is what the live graph looks like. Every claim, every provider, every auth chain, traversable."*
4. **Scenario Loader** — *"We're introducing a data quality problem that happens in real operations. Watch the sidebar."* [inject → badge fires]
5. **Findings Dashboard** — *"The graph found these before a single claim was worked. Every finding is in the graph, trackable, assignable, auditable over time."*

---

### Global app requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| APP-01 | Left sidebar navigation between five panels. Sidebar shows: Neo4j connection status (green/red), open finding count badge (live query: `MATCH (f:Finding {status:'open'}) RETURN count(f)`) — grey `0` on clean baseline, red `N open findings` after injection. Badge updates automatically; no page refresh required | **Must** |
| APP-02 | Neo4j connection managed centrally via `.env` file. Clear error message with fix instructions if Neo4j is unreachable | **Must** |
| APP-03 | Custom CSS to match xVector visual identity (accent `#b84a1f`, background `#f7f5f0`). Node color palette consistent across all graph visualizations and panel UI | **Must** |
| APP-04 | All panels load within 3 seconds (excluding graph render). Findings queries use indexes on `Finding.status` and `Finding.detected_at` | **Should** |

---

### Panel 1 — Ontology Explorer

| ID | Requirement | Priority |
|----|-------------|----------|
| P1-01 | Ontology schema diagram (pyvis) showing all 14 node types and all relationship types including `DetectionRule`, `Finding`, `HAS_FINDING`, and `TRIGGERED_BY`. These are presented as first-class graph citizens, not UI metadata | **Must** |
| P1-02 | Node type inventory table: label, property count, live instance count from graph. Relationship type table: type name, live count. `Finding` count starts at 0 and updates as scenarios are injected | **Must** |
| P1-03 | Clicking a node type shows a detail pane: properties, sample values, connected relationship types. Clicking `DetectionRule` shows rule metadata; clicking `Finding` shows a sample finding node if any exist | **Should** |

---

### Panel 2 — Rule Library

*This panel is the production monitoring story made visible. All six detection rules are shown as a library — browsable, inspectable, live-updating as findings accumulate.*

| ID | Requirement | Priority |
|----|-------------|----------|
| P2-01 | Rule cards: one card per `DetectionRule` node, pulled from the graph. Each card shows: rule ID badge, name, category badge (color-coded by category), severity indicator (HIGH/MEDIUM/LOW), business description (plain English), and a live **finding count** (`MATCH (f:Finding)-[:TRIGGERED_BY]->(r:DetectionRule {rule_id:$id}) RETURN count(f)`) | **Must** |
| P2-02 | Finding count on each rule card starts at `0` on clean baseline and increments in real time as scenarios are injected — without requiring panel refresh. This is the most visceral signal that the system is monitoring continuously | **Must** |
| P2-03 | Expanding a rule card shows: the Cypher detection query (syntax-highlighted, collapsible), version number, last updated date, and applicable node types. Gives a technical audience full visibility into the detection mechanism | **Should** |
| P2-04 | Rule category filter: filter cards by `prior_authorization`, `credentialing`, `contract`, `authorization_units`, `entity_integrity`, `referral`. Useful when walking a specialist audience through their category of interest | **Should** |
| P2-05 | "What this would look like in production" note — a static callout on the panel explaining that in production this library grows with the client's payer mix and denial history, new rules are added without code changes, and rules are versioned as payer policies evolve | **Should** |

---

### Panel 3 — KG Foundation

| ID | Requirement | Priority |
|----|-------------|----------|
| P3-01 | Interactive subgraph visualization (pyvis) — default view is a sample Claim and its full 2-hop neighborhood (Patient, Visit, CPT, Payer, Provider, Coverage, Auth). Max 300 nodes. After scenario injection, `Finding` nodes appear connected to affected Claims | **Must** |
| P3-02 | Search by Claim ID or Patient ID — renders that entity's neighborhood. Selected node highlighted. If the claim has associated `Finding` nodes, they appear in the subgraph automatically | **Must** |
| P3-03 | Node type color coding with legend — consistent palette across all panels. `Finding` nodes rendered in red `#a02828`; `DetectionRule` nodes in a distinct purple. Anomalous (flawed) claim nodes rendered in amber `#e08c2a` | **Must** |
| P3-04 | Metrics bar: total nodes, total relationships, open finding count, active scenario name | **Should** |

---

### Panel 4 — Scenario Loader

*Injection model: flaws are overlaid on the clean baseline. Affected nodes tagged with `is_flawed: true` and `flaw_scenario: 'S-XX'`. Detection runs immediately post-injection and writes `Finding` nodes to the graph. "Clear All Flaws" removes injected tags and deletes Finding nodes — baseline restored without full reload.*

| ID | Requirement | Priority |
|----|-------------|----------|
| P4-01 | Scenario checklist: all six scenarios displayed simultaneously with status `pending / loaded / viewed` per row. Each row shows scenario ID, category badge, severity, one-sentence description, and finding count (live, `0` until injected). Supports linear walkthrough of all six in one session | **Must** |
| P4-02 | "Inject" button per scenario row. On click: (1) run injection Cypher — tags affected Claims and modifies relationships, (2) run detection Cypher — creates `Finding` nodes with `HAS_FINDING` and `TRIGGERED_BY` edges, (3) update sidebar badge, (4) flip row status to `loaded`. Progress indicator shown during steps 1–2 | **Must** |
| P4-03 | Post-injection summary card: claims affected, relationship changes made (e.g., *"12 `HAS_AUTHORIZATION` relationships removed"*), findings created, and the business framing quote for this scenario | **Must** |
| P4-04 | "Clear All Flaws" button: removes all `is_flawed` / `flaw_scenario` properties, deletes all `Finding` nodes and their relationships, resets sidebar badge to `0`, resets all scenario rows to `pending`. Executes as a single Cypher transaction | **Must** |

---

### Panel 5 — Findings Dashboard

*Findings are read from the graph — not from session state cache. Every interaction (acknowledge, resolve) writes back to Neo4j. This demonstrates that the graph is the system of record for the monitoring workflow, not just a detection mechanism.*

| ID | Requirement | Priority |
|----|-------------|----------|
| P5-01 | Summary scorecard at top: open findings count, acknowledged count, resolved count, total estimated denial risk (sum of `Finding.estimated_risk_amount`, labeled "illustrative"), breakdown by severity (HIGH/MEDIUM/LOW) | **Must** |
| P5-02 | Findings table (reads from `Finding` nodes in graph): Finding ID, Claim ID, Patient ID, Rule ID, Rule Name, Severity, Status, Detected At, plain-English description. Sortable and filterable by severity, status, and rule. Defaults to `status = 'open'` | **Must** |
| P5-03 | Row selection opens the split-pane subgraph view: LEFT pane — actual claim subgraph with anomalous nodes in amber, missing relationships as dashed red `MISSING` edges, `Finding` node visible and highlighted; RIGHT pane — expected path per ontology (all nodes present, solid green edges, `Finding` node absent). The Finding node appears only in the left pane — its absence from the right pane makes the detection story self-evident | **Must** |
| P5-04 | Finding lifecycle buttons on selected row: `Acknowledge` sets `Finding.status = 'acknowledged'`; `Resolve` sets `Finding.status = 'resolved'` and writes `Finding.resolved_at = datetime()`. Both write directly to Neo4j — sidebar badge decrements in real time. Demonstrates that the graph is the operational workflow layer, not just a report | **Must** |
| P5-05 | Scenario narrative card (collapsible): business framing quote, what the flaw is, why standard tools miss it, how the graph detected it, which `DetectionRule` node fired. Written in RCM ops language | **Must** |
| P5-06 | Full detection chain view: a mini graph showing the traversal `Claim → HAS_FINDING → Finding → TRIGGERED_BY → DetectionRule`. Click any node in the chain to expand its properties. Demonstrates the complete lineage from data to finding to rule | **Should** |
| P5-07 | Scenario progress tracker: mini checklist showing which of the 6 scenarios have been `viewed` this session. Marks a scenario `viewed` when its findings are first viewed in this panel | **Should** |

---

## §07 Technical Architecture & Stack

### Component stack

| Layer | Components |
|-------|-----------|
| Data Generation | Python 3.11+, Faker 24+, pandas, numpy. Outputs System A–E CSV bundles mimicking real source system schemas |
| Rule Library | `detection_rules.yaml` — defines all 6 `DetectionRule` records with metadata and Cypher. Loaded into graph at startup as `DetectionRule` nodes. Versioned: bump `version` field to update a rule without changing application code |
| Graph Storage | Neo4j Community 5.x, local desktop instance, heap ≤ 4 GB. Neo4j Browser at `localhost:7474` for development and Cypher inspection |
| Graph I/O | `neo4j` Python driver 5.x (official). Raw Cypher throughout — no ORM layer |
| Detection Engine | `detection.py` — rule runner with clean contract: `run_rule(rule_id, driver) → int`. Each rule's Cypher is a two-step transaction: (1) find violations scoped to tagged Claims, (2) `CREATE (f:Finding {...})-[:HAS_FINDING]-(c:Claim)` and `(f)-[:TRIGGERED_BY]->(r:DetectionRule)`. Returns finding count |
| Flaw Injection | `flaw_injector.py` — six injection functions plus a universal `clear_all_flaws()`. Each injection tags Claims, modifies relationships, then immediately calls `detection.run_rule()`. Persists deleted relationship inventory to session state before deletion to enable clean reversal |
| Visualization | `pyvis 0.3+` via `st.components.v1.html()`. Split-pane rendering for Findings Dashboard: actual subgraph (amber/dashed-red) vs. expected ontology path (solid green). `Finding` nodes rendered in `#a02828`; `DetectionRule` in `#4a3b7a` |
| Application UI | Streamlit 1.35+. Five-panel app with sidebar live-querying `Finding` count. Custom CSS via `st.markdown(unsafe_allow_html=True)` |
| Configuration | `python-dotenv`. Neo4j credentials in `.env`. Rule library in `data/reference/` — static, committed to version control |

### Repository structure

```
kg-dq-demo/
├── data/
│   ├── reference/
│   │   ├── cpt_codes.csv             # CPT code subset (static)
│   │   ├── icd10_codes.csv           # ICD-10 code subset (static)
│   │   └── detection_rules.yaml      # Rule library — all 6 DetectionRule definitions
│   └── generated/                    # Output of data generator (gitignored)
│       ├── system_a_emr/             # pt_demographics, encounter, encounter_dx, charge_line
│       ├── system_b_claims/          # claim_header, claim_service_line
│       ├── system_c_payer/           # payer_master, insurance_plan, member_eligibility
│       ├── system_d_auth/            # auth_request, auth_detail, claim_auth_link
│       └── system_e_provider/        # provider_master, provider_payer_contract, fee_schedule, referral_order
├── src/
│   ├── generate/
│   │   ├── generator.py              # Synthetic data generator — outputs System A–E CSVs
│   │   └── domains.py                # CPT/ICD-10 reference data loader and payer logic
│   ├── graph/
│   │   ├── loader.py                 # Creates schema, loads baseline, loads DetectionRule nodes from YAML
│   │   ├── flaw_injector.py          # Six injection functions + clear_all_flaws()
│   │   ├── detection.py              # Rule runner: run_rule(), run_all_rules(), get_finding_count()
│   │   ├── findings.py               # Finding CRUD: list_findings(), update_status(), get_finding_subgraph()
│   │   ├── viz.py                    # pyvis subgraph builders: actual and expected path renderers
│   │   └── connection.py             # Neo4j driver connection management
│   └── app/
│       ├── main.py                   # Streamlit entry point + sidebar with live finding badge
│       ├── panel_ontology.py         # Panel 1 — Ontology Explorer
│       ├── panel_rules.py            # Panel 2 — Rule Library
│       ├── panel_foundation.py       # Panel 3 — KG Foundation
│       ├── panel_loader.py           # Panel 4 — Scenario Loader
│       ├── panel_findings.py         # Panel 5 — Findings Dashboard
│       └── styles.py                 # Custom CSS injection
├── scripts/
│   └── setup.py                      # One-command setup: generate data + load baseline + load rules
├── .env.example
├── requirements.txt
└── README.md
```

---

## §08 Phased Delivery Plan

Each phase ends with a review gate before proceeding.

### Phase 1 — Data & Graph Foundation

**Deliverables:**
- Windows Neo4j Community 5.x installation guide (download, install as service, heap config, Browser verification)
- Reference data: `cpt_codes.csv`, `icd10_codes.csv`, `detection_rules.yaml` (all 6 rules with metadata and Cypher)
- `generator.py`: clean baseline at target volumes — outputs System A–E CSV bundles to `data/generated/`
- `loader.py`: creates all ontology constraints and indexes (including `DetectionRule` and `Finding`), loads clean baseline, loads `DetectionRule` nodes from `detection_rules.yaml`
- `flaw_injector.py`: six injection functions + `clear_all_flaws()` — tags Claims, modifies relationships, persists deleted relationship inventory to enable clean reversal
- `detection.py`: `run_rule()` and `run_all_rules()` — executes each rule's Cypher and writes `Finding` nodes with `HAS_FINDING` and `TRIGGERED_BY` edges. Tested against all six injected scenarios with expected finding counts documented
- Manual verification in Neo4j Browser: inject two scenarios, confirm `Finding` nodes appear with correct edges to Claims and `DetectionRule` nodes

**Gate:** Kiran reviews the loaded KG in Neo4j Browser — verifies that `DetectionRule` nodes exist, injects two scenarios, and confirms `Finding` nodes are created with the correct `HAS_FINDING → Claim` and `TRIGGERED_BY → DetectionRule` relationships. Approve to proceed to Phase 2.

---

### Phase 2 — Streamlit Application

**Deliverables:**
- App shell: sidebar with live `Finding` count badge (queries Neo4j directly — not session state), five-panel navigation
- Panel 1 (Ontology Explorer): schema diagram including `DetectionRule` and `Finding` node types
- Panel 2 (Rule Library): rule cards with live finding counts, expandable Cypher view
- Panel 3 (KG Foundation): interactive subgraph with `Finding` nodes visible post-injection
- Panel 4 (Scenario Loader): scenario checklist, inject button with post-injection summary, `clear_all_flaws()` wired to UI
- Panel 5 (Findings Dashboard): findings table from graph, split-pane subgraph visualization (actual vs. expected), `Acknowledge` / `Resolve` lifecycle buttons writing to Neo4j, detection chain view
- Custom CSS applied — xVector visual identity in place
- End-to-end demo narrative arc (5 beats) working for all six scenarios in one session

**Gate:** Full walkthrough of all five panels with at least three scenarios injected. Kiran approves the demo narrative arc and the finding lifecycle interaction before Phase 3.

---

### Phase 3 — Polish & Demo Readiness

**Deliverables:**
- All six scenarios tested end-to-end: injection → finding creation → lifecycle interaction all under 5 seconds combined
- Scenario narrative cards finalized (plain English, RCM ops language, business framing quotes confirmed)
- **Should** requirements implemented: P2-03 (Cypher view), P2-04 (category filter), P3-04 (KG metrics bar), P5-06 (detection chain view), P5-07 (session progress tracker)
- `setup.py` one-command install: generate data → load baseline → load rules → verify via Neo4j Browser
- README: Neo4j Windows setup, Python environment, demo walkthrough guide with 5-beat narrative script
- `detection_rules.yaml` reviewed — rule descriptions, business framing quotes, and Cypher queries all finalized

**Gate:** Dry run with a team member who hasn't seen the demo. All five panels flow without errors, finding lifecycle works correctly, narrative is clear to a non-technical observer. POC-complete.

---

## §09 Design Decisions (resolved)

All open questions are closed. Decisions recorded here for implementation reference.

| ID | Decision | Resolution |
|----|----------|------------|
| OQ-01 | **Neo4j installation** | Not pre-installed. Phase 1 scope includes a Windows installation guide for Neo4j Community 5.x — download, install as a service, configure heap, verify via Browser at `localhost:7474`. Setup script (`scripts/setup.py`) runs after Neo4j is running. |
| OQ-02 | **Dataset loading model** | **Overlay, not clear-and-reload.** Flawed records are injected into the live baseline graph as tagged additions (`is_flawed: true`, `flaw_scenario: 'S-XX'`). Baseline nodes remain intact. A "Clear All Flaws" operation removes injected properties without a full reload. Visual distinction: affected nodes render in amber, missing paths rendered as dashed red edges with `MISSING` label, a split-pane view shows actual vs. expected subgraph side-by-side. |
| OQ-03 | **Contract version source data** | Both contract versions generated as separate rows in System E CSVs (`version_num = 1` and `version_num = 2`). The graph loader builds the `SUPERSEDED_BY` / `POLICY_SUPERSEDED_BY` edges based on `version_num` ordering per `(npi, payer_id)` pair. Mirrors the real-world problem: both rows exist in the source table and the system used the wrong one. |
| OQ-04 | **Graph visualization library** | **pyvis** as primary. Richer physics simulation, hover tooltips, and edge label support. Rendered via `st.components.v1.html()` with explicit height parameter to avoid Windows iframe clipping. `streamlit-agraph` kept as fallback only. |
| OQ-05 | **Demo session flow** | **All six scenarios in one session.** Panel 3 uses a checklist layout (not a dropdown) — all six scenarios visible simultaneously with status indicators (`pending / loaded / viewed`). Presenter works through them in order. Panel 4 has a scenario progress tracker showing which have been covered. |

### Detection model decision

**Production detection architecture — not a query tool.**

The demo showcases how a production monitoring system operates:

- **`DetectionRule` nodes** live in the graph as first-class entities, loaded from `detection_rules.yaml` at startup. The rule library is browsable in Panel 2. Rules are versioned and togglable.
- **Detection runs automatically** on scenario injection — no manual trigger. `detection.run_rule()` fires immediately after `flaw_injector` completes, as part of the same button callback.
- **`Finding` nodes are written back into the graph** — not cached in session state. Every finding has `HAS_FINDING → Claim` and `TRIGGERED_BY → DetectionRule` edges. Findings are persistent, queryable, and auditable.
- **The sidebar badge queries the graph live** — `MATCH (f:Finding {status:'open'}) RETURN count(f)` — reflecting the true open finding count at all times.
- **Finding lifecycle is operational** — `Acknowledge` and `Resolve` write status changes directly to Neo4j. The graph is the system of record for the monitoring workflow.
- **Scenario isolation** is enforced by tagging: each injection tags affected Claims with `flaw_scenario: 'S-XX'`, and each detection rule scopes its query to that tag. Multiple scenarios can be overlaid without interference.
- **"Clear All Flaws"** deletes all `Finding` nodes, removes injected tags, and restores deleted relationships — executed as a single Cypher transaction. Sidebar badge resets to `0`.

---

## Assumptions & Notes

- All CPT and ICD-10 codes are from publicly available CMS code sets.
- The denial risk dollar estimate (P4-05) is arithmetic only, based on average billed amounts in the synthetic dataset. Must be labeled "illustrative" in the UI.
- Neo4j Community Edition is free and sufficient for this scope. Enterprise-only features (clustering, RBAC, full APOC) are not needed.
- `pyvis` renders as an HTML iframe inside Streamlit. Known height-clipping issue on Windows has a workaround (explicit iframe height parameter) — will be applied during implementation.
- The source system table schemas are modeled on real-world conventions (Epic Clarity, CAQH, 837P/I) but are simplified for synthetic data generation purposes. Vendor names are cited for client-facing credibility in the demo narrative — they are not integration targets.
- The specialty mix (PT/behavioral health at ~20% of encounters) and HMO enrollment (~25–30%) are prerequisites for S-04 and S-06 to have meaningful anomaly volume. These must be enforced in the data generator, not left to chance.
- Phase time estimates are intentionally not included. This document covers what, not when.
