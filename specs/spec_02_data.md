# Spec 02 — Synthetic Data Specification

**Read this file before implementing:** `generator.py`, `domains.py`

---

## Baseline dataset volumes

| Entity | Target count | Notes |
|--------|-------------|-------|
| Patient | 1,000 | Realistic mix across payers |
| Visit | 4,000–5,000 | ~4–5 per patient |
| Claim | 5,000–6,000 | Some visits → multiple claims |
| CPT_Code | 50–80 distinct | E&M + procedures + imaging |
| ICD10_Code | 40–60 distinct | Common chronic + acute |
| Payer | 6–8 | Medicare, Medicaid, 4–6 commercial |
| PayerPolicy | 12–20 | 2–3 plan versions per payer |
| Provider | 30–40 | PCPs, specialists, facilities |
| Contract | 20–30 | Provider-payer pairings, some versioned |
| Authorization | ~800 | ~30% of claims with auth-required CPTs |
| ReferralOrder | ~400 | HMO specialist visits |
| Coverage | ~1,200 | Some patients with coverage transitions |
| DetectionRule | 6 | Loaded from `detection_rules.yaml` at startup |
| Finding | 0 baseline | Written at runtime by detection engine |
| **Total nodes** | **~13,000–14,006** | Well within Neo4j Community desktop limits |
| **Total relationships** | **~35,000–40,000+** | Findings add edges at runtime |

---

## Data realism requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| DR-01 | CPT and ICD-10 codes drawn from real, valid CMS code sets with correct descriptions | **Must** |
| DR-02 | CPT codes requiring prior authorization reflect real-world payer behavior (MRI, surgical procedures) — hard-coded list in `domains.py` | **Must** |
| DR-03 | Demographics: ~40% Medicare/Medicaid, ~35% commercial PPO, ~25% commercial HMO | **Should** |
| DR-04 | All names fictional (Faker); synthetic NPIs that do not match real CMS NPI records | **Should** |
| DR-05 | Specialty mix includes PT/behavioral health/home health at ~20% of encounters (prerequisite for S-04) | **Must** |
| DR-06 | HMO plan enrollment ~25–30% of patients (prerequisite for S-06) | **Must** |

---

## Payer mix

| Payer type | % of patients | Plan types |
|-----------|--------------|------------|
| Medicare | ~20% | FFS + Medicare Advantage (PPO) |
| Medicaid | ~20% | MCO / managed Medicaid |
| Commercial PPO | ~35% | PPO — BCBS, Aetna, UHC, Cigna |
| Commercial HMO | ~25–30% | HMO — requires referrals |

---

## CPT codes requiring prior authorization (DR-02)

Hard-code these categories in `domains.py`. These are the auth-required CPT codes that drive S-01 and S-04:

| Category | Example CPT range / codes |
|---------|--------------------------|
| MRI imaging | 70553, 71552, 72148, 73223 |
| CT imaging | 70470, 71270, 72131 |
| Outpatient surgery | 27447, 29827, 43239 |
| Physical therapy (units-based) | 97110, 97530, 97140 |
| Behavioral health | 90837, 90847, 90853 |
| Home health | G0299, G0300 |
| Radiation oncology | 77373, 77385 |

---

## Source system schemas

### System A — EMR / EHR (Epic Clarity-style)

**Output files:** `data/generated/system_a_emr/`

| Table | Key fields |
|-------|-----------|
| `pt_demographics.csv` | `mrn`, `last_name`, `first_name`, `dob`, `sex`, `zip`, `ssn_last4`, `race`, `language`, `create_date` |
| `encounter.csv` | `encounter_id`, `mrn`, `encounter_date`, `encounter_type`, `place_of_service`, `rendering_npi`, `facility_id`, `admit_date`, `discharge_date` |
| `encounter_dx.csv` | `encounter_id`, `dx_code`, `dx_description`, `dx_position` (1=primary), `poa_flag` |
| `charge_line.csv` | `charge_id`, `encounter_id`, `cpt_code`, `cpt_modifier`, `units`, `charge_date`, `charge_amount`, `revenue_code` |

### System B — Practice Management / Claims (CMS-1500 / 837P-derived)

**Output files:** `data/generated/system_b_claims/`

| Table | Key fields |
|-------|-----------|
| `claim_header.csv` | `claim_id`, `mrn`, `member_id`, `billing_npi`, `rendering_npi`, `referring_npi`, `payer_id`, `plan_id`, `claim_date`, `total_billed`, `claim_type`, `claim_status`, `auth_number` *(free-text — not a validated FK)* |
| `claim_service_line.csv` | `line_id`, `claim_id`, `cpt_code`, `modifier`, `icd10_primary`, `icd10_secondary`, `units`, `line_billed`, `service_date` |

> **Critical:** `auth_number` in `claim_header` is a free-text field, NOT a foreign key constraint. This is intentional — the gap between this field and a validated `claim_auth_link` row is what S-01 detects.

### System C — Payer / Clearinghouse

**Output files:** `data/generated/system_c_payer/`

| Table | Key fields |
|-------|-----------|
| `payer_master.csv` | `payer_id`, `payer_name`, `payer_type` (commercial/Medicare/Medicaid/MCO), `clearinghouse_id` |
| `insurance_plan.csv` | `plan_id`, `payer_id`, `plan_name`, `plan_type` (HMO/PPO/EPO/POS), `effective_date`, `term_date`, `version_num` |
| `member_eligibility.csv` | `eligibility_id`, `mrn`, `member_id`, `plan_id`, `start_date`, `end_date`, `copay`, `deductible`, `group_number` |

### System D — Authorization Management

**Output files:** `data/generated/system_d_auth/`

| Table | Key fields |
|-------|-----------|
| `auth_request.csv` | `auth_id`, `mrn`, `payer_id`, `requesting_npi`, `auth_date`, `expiry_date`, `status` (approved/denied/pending), `approved_units` |
| `auth_detail.csv` | `auth_detail_id`, `auth_id`, `cpt_code`, `icd10_code`, `approved_units` |
| `claim_auth_link.csv` | `claim_id`, `auth_id`, `linked_date` *(join table — intentionally incomplete for S-01)* |

### System E — Provider Credentialing & Contracts

**Output files:** `data/generated/system_e_provider/`

| Table | Key fields |
|-------|-----------|
| `provider_master.csv` | `npi`, `last_name`, `first_name`, `specialty`, `provider_type` (physician/facility/mid-level), `tax_id`, `license_state`, `license_num`, `excluded_flag` |
| `provider_payer_contract.csv` | `contract_id`, `npi`, `payer_id`, `contract_type` (par/non-par), `effective_date`, `term_date`, `fee_schedule_id`, `version_num` |
| `fee_schedule.csv` | `fee_schedule_id`, `cpt_code`, `allowed_amount`, `effective_date` |
| `referral_order.csv` | `referral_id`, `mrn`, `referring_npi`, `referred_to_npi`, `plan_id`, `referral_date`, `expiry_date`, `cpt_code` |

---

## Generator module structure (`generator.py`)

Generate in this dependency order — later systems reference IDs from earlier ones:

1. Reference data (CPT, ICD-10) — from `domains.py`
2. Payers and PayerPolicies — from `domains.py` payer definitions
3. Providers — with specialty mix enforced (DR-05)
4. Provider-payer contracts — with version pairs for S-03
5. Patients — with payer distribution enforced (DR-03, DR-06)
6. Coverages — link patients to policies
7. Encounters — with rendering NPI assignment
8. Charge lines — CPT codes assigned per encounter
9. Claims — from encounters + charge lines
10. Authorizations — ~30% of auth-required claims
11. `claim_auth_link` — intentionally incomplete (leave 8–12% unlinked for S-01)
12. Referral orders — for HMO specialist visits

---

## S-03 contract versioning setup in generator

For 2–3 payers, generate two contract rows per provider-payer pair:
- `version_num = 1`: `effective_date` = 18 months ago, `term_date` = 6 months ago
- `version_num = 2`: `effective_date` = 6 months ago, `term_date` = null

The `loader.py` reads both rows and creates a `SUPERSEDED_BY` edge from version 1 → version 2.
Claims post-renewal that still reference `version_num=1` contracts are the S-03 flaws.

---

## Generator validation checks

After running `generator.py`, verify:
```bash
# Row counts
wc -l data/generated/system_a_emr/pt_demographics.csv    # ~1000
wc -l data/generated/system_b_claims/claim_header.csv    # ~5000-6000
wc -l data/generated/system_d_auth/claim_auth_link.csv   # should be ~88-92% of auth-required claims

# HMO enrollment check
python -c "
import pandas as pd
plans = pd.read_csv('data/generated/system_c_payer/insurance_plan.csv')
elig  = pd.read_csv('data/generated/system_c_payer/member_eligibility.csv')
hmo_plans = plans[plans.plan_type=='HMO']['plan_id']
hmo_pct = elig[elig.plan_id.isin(hmo_plans)]['mrn'].nunique() / elig['mrn'].nunique()
print(f'HMO enrollment: {hmo_pct:.1%}')  # target 25-30%
"
```
