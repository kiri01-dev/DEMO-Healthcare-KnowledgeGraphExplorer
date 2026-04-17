# RCM Knowledge Graph — Use Case Summary

16 scenarios encodable as versioned graph detection rules.  
**Impact rank** = directional estimate of (industry frequency × $ per occurrence). Not actuarial — order-of-magnitude only.

| Rank | ID | Scenario | Type | Severity | Risk category | Why graph-native |
|------|----|----------|------|----------|---------------|-----------------|
| 1 | S-09 | Underpayment Against Contracted Rate | Business optimization | HIGH | Underpayment | Requires 5-hop traversal: Claim → Provider → Contract → FeeSchedule → CPT, compared against remittance; no single system holds all legs |
| 2 | S-01 | Prior Auth — Unverifiable Auth Chain | Data quality | HIGH | Denial | Auth validity requires 4-hop cross-system path; `auth_number IS NOT NULL` passes in SQL but proves nothing |
| 3 | S-02 | Rendering Provider Not Credentialed | Data quality | HIGH | Denial (CO-4) | Billing NPI passes scrubber; rendering NPI credentialing requires separate contract traversal against the same payer |
| 4 | S-11 | OIG Excluded Provider (Direct or Referred-Through) | Data quality | HIGH | Compliance / FCA exposure | Exclusion check must cover billing, rendering, AND referring provider — three separate BILLED_BY / REFERRED_BY traversals |
| 5 | S-16 | 30-Day Same-Condition Readmission | Business optimization | HIGH | VBC penalty | Requires linking two Visit nodes for same patient, overlapping ICD-10, elapsed days, and VBC contract flag — four nodes minimum |
| 6 | S-14 | Diagnosis-Procedure Medical Necessity Mismatch | Data quality | HIGH | Denial | Requires CPT → SUPPORTED_BY → ICD10 reference graph checked against claim's coded diagnoses; no scrubber joins LCD policy to live claim |
| 7 | S-07 | Timely Filing Violation | Data quality | MEDIUM | Denial (CO-29) | Filing deadlines vary by payer and plan type; rule must traverse Claim → Payer {filing_limit_days} — deadline lives on the payer node |
| 8 | S-15 | COB Primary/Secondary Sequencing Error | Data quality | HIGH | Overpayment / refund liability | Requires knowing all active coverages for a patient simultaneously and their COB order — multi-Coverage traversal per patient |
| 9 | S-04 | Authorization Unit Exhaustion | Data quality | HIGH | Denial / overpayment | Units must be summed across all claims linked to one auth; each claim looks valid in isolation |
| 10 | S-12 | Unbundling / CCI Edit Violation | Data quality | MEDIUM | Denial / clawback | Requires CPT → BUNDLED_WITH → CPT reference graph; violation only detectable when two specific codes co-occur on the same claim |
| 11 | S-06 | Invalid HMO Referral Chain | Data quality | HIGH | Denial (CO-96) | Four simultaneous conditions across Coverage, Visit, ReferralOrder, and Provider nodes — no claim editor joins all four |
| 12 | S-08 | Stale Coverage at Date of Service | Data quality | MEDIUM | Denial | Coverage termination must be checked against visit date via Claim → Coverage — eligibility portal checks happen at scheduling, not claim time |
| 13 | S-13 | Place of Service Mismatch | Data quality | MEDIUM | Underpayment / refund | Valid POS lives on CPT_Code node; actual POS lives on Visit node — mismatch requires one cross-node comparison |
| 14 | S-10 | Global Surgery Period Post-Op Billing | Data quality | MEDIUM | Denial (bundling) | Requires temporal link between two claims for the same patient/provider — impossible without connecting claims through the patient node |
| 15 | S-03 | Superseded Fee Schedule / Contract | Data quality | MEDIUM | Underpayment | SUPERSEDED_BY chain makes stale contract reference a single pattern match; without version chain awareness both contract rows look valid |
| 16 | S-05 | Duplicate Patient Identity | Data quality | HIGH | Entity integrity / COB failure | Network-level signals (shared provider + payer + zip + near-DOB) are far stronger than demographic fuzzy match alone |

---

## Category breakdown

| Category | Count | Notes |
|----------|-------|-------|
| Data quality | 13 | Scenarios where a defect in source data or cross-system linkage causes a denial, clawback, or compliance exposure |
| Business optimization | 3 | S-09 (underpayment recovery), S-16 (VBC readmission penalty avoidance) — revenue or penalty at stake even when no data defect exists |

---

## New graph elements required (beyond the baseline 6 scenarios)

| Element | Type | Required by | Source |
|---------|------|-------------|--------|
| `Payer.filing_limit_days` | Property | S-07 | Payer contract / ops knowledge |
| `Provider.exclusion_date` | Property | S-11 | OIG LEIE (monthly download) |
| `CPT_Code.global_period_days` | Property | S-10 | CMS physician fee schedule |
| `CPT_Code.valid_pos` | Property | S-13 | CMS physician fee schedule |
| `PayerPolicy.cob_order` | Property | S-15 | Payer / eligibility feed |
| `PayerPolicy.contract_type` | Property | S-16 | Contract management system |
| `RemittanceAdvice` | Node | S-09 | 835 remittance feed |
| `FeeSchedule` | Node (promote from ID) | S-09 | System E fee_schedule.csv |
| `CPT_Code → BUNDLED_WITH → CPT_Code` | Relationship | S-12 | CMS CCI edits table (quarterly) |
| `CPT_Code → SUPPORTED_BY → ICD10_Code` | Relationship | S-14 | CMS LCD policy files (quarterly) |
| `Visit → READMISSION_OF → Visit` | Relationship | S-16 | Derived at load time |

---

## Impact rank methodology

Rank = directional estimate of **industry denial frequency × average $ per occurrence**.  
Sources informing order: MGMA denial benchmarks, CMS clawback data, OIG work plan, HFMA underpayment studies.  
Not actuarial. Use for prioritization conversations, not financial modeling.
