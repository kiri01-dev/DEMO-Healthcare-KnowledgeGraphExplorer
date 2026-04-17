"""
generator.py — Synthetic RCM data generator.

Outputs System A–E CSV bundles to data/generated/.
Run directly: python src/generate/generator.py

Generation order (strict dependency chain):
  1. Payers + PayerPolicies  (System C)
  2. Providers               (System E)
  3. Contracts               (System E) — v1 and v2 for S-03 payers
  4. Fee schedules           (System E)
  5. Patients                (System A)
  6. Member eligibility      (System C)
  7. Encounters              (System A)
  8. Encounter diagnoses     (System A)
  9. Charge lines            (System A)
 10. Claims                  (System B)
 11. Claim service lines     (System B)
 12. Authorizations          (System D)
 13. Auth details            (System D)
 14. claim_auth_link         (System D) — intentionally ~90% complete
 15. Referral orders         (System E)
"""

import os
import sys
import random
import string
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.generate.domains import (
    get_cpt_codes,
    get_icd10_codes,
    get_auth_required_cpts,
    get_payer_definitions,
    get_hmo_payer_ids,
    get_specialty_mix,
    CPT_CATEGORY_BY_SPECIALTY,
    S03_RENEWAL_PAYER_IDS,
    S02_TARGET_PAYER_IDS,
)

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
fake.seed_instance(SEED)

TODAY = date.today()
TWO_YEARS_AGO = TODAY - timedelta(days=730)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(_THIS_DIR, "..", "..", "data", "generated")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def _synthetic_npi() -> str:
    """10-digit NPI starting with 9 (real NPIs start with 1 or 2)."""
    return "9" + "".join([str(random.randint(0, 9)) for _ in range(9)])


def _save(df: pd.DataFrame, system_dir: str, filename: str):
    path = os.path.join(OUT_DIR, system_dir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
    print(f"  saved {len(df):>6} rows -> {system_dir}/{filename}")


# ---------------------------------------------------------------------------
# Step 1 — Payers and PayerPolicies (System C)
# ---------------------------------------------------------------------------

def generate_payers() -> tuple[pd.DataFrame, pd.DataFrame]:
    payer_defs = get_payer_definitions()
    payers = []
    policies = []

    renewal_6mo_ago = TODAY - timedelta(days=180)
    renewal_18mo_ago = TODAY - timedelta(days=540)

    for p in payer_defs:
        payers.append({
            "payer_id": p["payer_id"],
            "payer_name": p["payer_name"],
            "payer_type": p["payer_type"],
            "clearinghouse_id": f"CH{p['payer_id'][-3:]}",
        })

        for pt in p["plan_types"]:
            plan_id = f"PLN{p['payer_id'][-3:]}{pt[:3]}"

            if p["payer_id"] in S03_RENEWAL_PAYER_IDS:
                # v1: expired 6 months ago
                policies.append({
                    "plan_id": f"{plan_id}_V1",
                    "payer_id": p["payer_id"],
                    "plan_name": f"{p['payer_name']} {pt} Plan 2022",
                    "plan_type": pt,
                    "effective_date": str(renewal_18mo_ago),
                    "term_date": str(renewal_6mo_ago),
                    "version_num": 1,
                })
                # v2: active
                policies.append({
                    "plan_id": f"{plan_id}_V2",
                    "payer_id": p["payer_id"],
                    "plan_name": f"{p['payer_name']} {pt} Plan 2024",
                    "plan_type": pt,
                    "effective_date": str(renewal_6mo_ago),
                    "term_date": None,
                    "version_num": 2,
                })
            else:
                policies.append({
                    "plan_id": plan_id,
                    "payer_id": p["payer_id"],
                    "plan_name": f"{p['payer_name']} {pt} Plan",
                    "plan_type": pt,
                    "effective_date": str(TWO_YEARS_AGO),
                    "term_date": None,
                    "version_num": 1,
                })

    payers_df = pd.DataFrame(payers)
    policies_df = pd.DataFrame(policies)
    return payers_df, policies_df


# ---------------------------------------------------------------------------
# Step 2 — Providers (System E)
# ---------------------------------------------------------------------------

def generate_providers(n: int = 38) -> pd.DataFrame:
    specialty_mix = get_specialty_mix()
    specialties = list(specialty_mix.keys())
    weights = list(specialty_mix.values())

    providers = []
    pcp_npis = []

    for i in range(n):
        specialty = np.random.choice(specialties, p=weights)
        npi = _synthetic_npi()
        if specialty == "PCP":
            pcp_npis.append(npi)

        if specialty in ("PT", "Home Health"):
            ptype = "mid-level"
        elif specialty in ("Radiology", "Emergency Medicine"):
            ptype = "facility"
        else:
            ptype = "physician"

        providers.append({
            "npi": npi,
            "last_name": fake.last_name(),
            "first_name": fake.first_name(),
            "specialty": specialty,
            "provider_type": ptype,
            "tax_id": f"{''.join([str(random.randint(0,9)) for _ in range(9)])}",
            "license_state": fake.state_abbr(),
            "license_num": f"L{random.randint(100000, 999999)}",
            "excluded_flag": False,
        })

    def _add_provider(specialty, ptype):
        npi = _synthetic_npi()
        providers.append({
            "npi": npi,
            "last_name": fake.last_name(),
            "first_name": fake.first_name(),
            "specialty": specialty,
            "provider_type": ptype,
            "tax_id": "".join([str(random.randint(0, 9)) for _ in range(9)]),
            "license_state": fake.state_abbr(),
            "license_num": f"L{random.randint(100000, 999999)}",
            "excluded_flag": False,
        })
        return npi

    # Ensure at least 6 PCPs
    while sum(1 for p in providers if p["specialty"] == "PCP") < 6:
        npi = _add_provider("PCP", "physician")
        pcp_npis.append(npi)

    # Enforce PT/BH/HH floor: at least 20% of total regular providers (DR-05)
    min_pt_bh = max(8, int(n * 0.20))
    current_pt_bh = sum(1 for p in providers
                        if p["specialty"] in ("PT", "Behavioral Health", "Home Health"))
    for _ in range(min_pt_bh - current_pt_bh):
        spec = random.choice(["PT", "PT", "Behavioral Health", "Home Health"])
        _add_provider(spec, "mid-level")

    # Add 6 "rendering-only" uncredentialed providers for S-02
    for i in range(6):
        npi = _synthetic_npi()
        providers.append({
            "npi": npi,
            "last_name": fake.last_name(),
            "first_name": fake.first_name(),
            "specialty": "Orthopedics",
            "provider_type": "physician",
            "tax_id": f"{''.join([str(random.randint(0,9)) for _ in range(9)])}",
            "license_state": fake.state_abbr(),
            "license_num": f"L{random.randint(100000, 999999)}",
            "excluded_flag": False,
            "s02_uncredentialed": True,  # marker for injector
        })

    return pd.DataFrame(providers)


# ---------------------------------------------------------------------------
# Step 3 — Contracts (System E)
# ---------------------------------------------------------------------------

def generate_contracts(providers_df: pd.DataFrame, payers_df: pd.DataFrame) -> pd.DataFrame:
    contracts = []
    payer_ids = payers_df["payer_id"].tolist()
    renewal_6mo_ago = TODAY - timedelta(days=180)
    renewal_18mo_ago = TODAY - timedelta(days=540)

    # Regular providers get contracts with most payers (except uncredentialed S-02 providers)
    regular = providers_df[providers_df.get("s02_uncredentialed", False) != True].copy()

    for _, prov in regular.iterrows():
        # Assign contracts with ~5 payers per provider
        assigned_payers = random.sample(payer_ids, min(5, len(payer_ids)))
        for pid in assigned_payers:
            cid_base = f"CON{prov['npi'][-4:]}{pid[-3:]}"

            if pid in S03_RENEWAL_PAYER_IDS:
                # v1 (expired 6 months ago)
                contracts.append({
                    "contract_id": f"{cid_base}_V1",
                    "npi": prov["npi"],
                    "payer_id": pid,
                    "contract_type": "par",
                    "effective_date": str(renewal_18mo_ago),
                    "term_date": str(renewal_6mo_ago),
                    "fee_schedule_id": f"FS{pid[-3:]}V1",
                    "version_num": 1,
                })
                # v2 (active)
                contracts.append({
                    "contract_id": f"{cid_base}_V2",
                    "npi": prov["npi"],
                    "payer_id": pid,
                    "contract_type": "par",
                    "effective_date": str(renewal_6mo_ago),
                    "term_date": None,
                    "fee_schedule_id": f"FS{pid[-3:]}V2",
                    "version_num": 2,
                })
            else:
                contracts.append({
                    "contract_id": f"{cid_base}",
                    "npi": prov["npi"],
                    "payer_id": pid,
                    "contract_type": "par",
                    "effective_date": str(TWO_YEARS_AGO),
                    "term_date": None,
                    "fee_schedule_id": f"FS{pid[-3:]}",
                    "version_num": 1,
                })

    # Uncredentialed providers (S-02): NO contracts with S02_TARGET_PAYER_IDS
    uncred = providers_df[providers_df.get("s02_uncredentialed", False) == True] if "s02_uncredentialed" in providers_df.columns else pd.DataFrame()
    if len(uncred) > 0:
        for _, prov in uncred.iterrows():
            other_payers = [p for p in payer_ids if p not in S02_TARGET_PAYER_IDS]
            for pid in random.sample(other_payers, min(3, len(other_payers))):
                cid_base = f"CON{prov['npi'][-4:]}{pid[-3:]}"
                contracts.append({
                    "contract_id": cid_base,
                    "npi": prov["npi"],
                    "payer_id": pid,
                    "contract_type": "par",
                    "effective_date": str(TWO_YEARS_AGO),
                    "term_date": None,
                    "fee_schedule_id": f"FS{pid[-3:]}",
                    "version_num": 1,
                })

    return pd.DataFrame(contracts)


# ---------------------------------------------------------------------------
# Step 4 — Fee schedules (System E)
# ---------------------------------------------------------------------------

def generate_fee_schedules(contracts_df: pd.DataFrame) -> pd.DataFrame:
    cpt_df = get_cpt_codes()
    fee_schedule_ids = contracts_df["fee_schedule_id"].unique().tolist()
    rows = []

    base_rates = {
        "E&M": (80, 350),
        "Lab": (20, 90),
        "Imaging": (150, 1800),
        "Surgery": (800, 6000),
        "PT": (60, 180),
        "Behavioral Health": (80, 250),
        "Home Health": (90, 300),
        "Cardiology": (200, 900),
        "Preventive": (40, 200),
    }

    for fs_id in fee_schedule_ids:
        eff_date = TODAY - timedelta(days=random.randint(180, 720))
        for _, cpt_row in cpt_df.iterrows():
            lo, hi = base_rates.get(cpt_row["category"], (50, 500))
            rows.append({
                "fee_schedule_id": fs_id,
                "cpt_code": cpt_row["code"],
                "allowed_amount": round(random.uniform(lo, hi), 2),
                "effective_date": str(eff_date),
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 5 — Patients (System A)
# ---------------------------------------------------------------------------

def generate_patients(n: int = 1000) -> pd.DataFrame:
    payer_defs = get_payer_definitions()
    payer_ids = [p["payer_id"] for p in payer_defs]
    weights = np.array([p["weight"] for p in payer_defs], dtype=float)
    weights = weights / weights.sum()  # normalize — guards against floating-point sum != 1.0

    patients = []
    for i in range(n):
        dob = _rand_date(date(1940, 1, 1), date(2005, 12, 31))
        payer_id = np.random.choice(payer_ids, p=weights)
        patients.append({
            "mrn": f"MRN{i+1:05d}",
            "last_name": fake.last_name(),
            "first_name": fake.first_name(),
            "dob": str(dob),
            "sex": random.choice(["M", "F"]),
            "zip": fake.zipcode(),
            "ssn_last4": f"{random.randint(1000, 9999)}",
            "race": random.choice(["White", "Black", "Hispanic", "Asian", "Other"]),
            "language": random.choice(["English", "Spanish", "English", "English", "Other"]),
            "create_date": str(_rand_date(TWO_YEARS_AGO, TODAY - timedelta(days=30))),
            "primary_payer_id": payer_id,  # used for eligibility generation
        })

    return pd.DataFrame(patients)


# ---------------------------------------------------------------------------
# Step 6 — Member eligibility (System C)
# ---------------------------------------------------------------------------

def generate_eligibility(patients_df: pd.DataFrame, policies_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    elig_id = 1

    # Build payer_id → active plan_id map
    active_plans = policies_df[policies_df["version_num"] == policies_df.groupby("payer_id")["version_num"].transform("max")]
    payer_to_plan = dict(zip(active_plans["payer_id"], active_plans["plan_id"]))

    for _, pt in patients_df.iterrows():
        pid = pt["primary_payer_id"]
        plan_id = payer_to_plan.get(pid)
        if plan_id is None:
            continue

        start = _rand_date(TWO_YEARS_AGO, TODAY - timedelta(days=365))
        rows.append({
            "eligibility_id": f"ELG{elig_id:06d}",
            "mrn": pt["mrn"],
            "member_id": f"MBR{elig_id:07d}",
            "plan_id": plan_id,
            "start_date": str(start),
            "end_date": None,
            "copay": random.choice([0, 20, 30, 40, 50]),
            "deductible": random.choice([0, 500, 1000, 1500, 2000, 3000]),
            "group_number": f"GRP{random.randint(10000, 99999)}",
        })
        elig_id += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 7 — Encounters (System A)
# ---------------------------------------------------------------------------

def generate_encounters(patients_df: pd.DataFrame, providers_df: pd.DataFrame) -> pd.DataFrame:
    regular_providers = providers_df[
        providers_df.get("s02_uncredentialed", False) != True
    ] if "s02_uncredentialed" in providers_df.columns else providers_df

    encounters = []
    enc_id = 1

    pos_map = {
        "PCP": "11", "Cardiology": "11", "Orthopedics": "11",
        "Gastroenterology": "22", "Neurology": "11", "Oncology": "22",
        "Ophthalmology": "11", "General Surgery": "22",
        "PT": "11", "Behavioral Health": "11",
        "Home Health": "12", "Radiology": "22",
        "Emergency Medicine": "23",
    }

    for _, pt in patients_df.iterrows():
        n_visits = random.randint(3, 6)
        for _ in range(n_visits):
            enc_date = _rand_date(TWO_YEARS_AGO, TODAY - timedelta(days=7))
            prov = regular_providers.sample(1).iloc[0]
            specialty = prov["specialty"]
            pos = pos_map.get(specialty, "11")

            encounters.append({
                "encounter_id": f"ENC{enc_id:07d}",
                "mrn": pt["mrn"],
                "encounter_date": str(enc_date),
                "encounter_type": "outpatient" if pos in ("11", "12") else "inpatient",
                "place_of_service": pos,
                "rendering_npi": prov["npi"],
                "facility_id": f"FAC{random.randint(100, 199)}",
                "admit_date": str(enc_date) if pos == "22" else None,
                "discharge_date": str(enc_date + timedelta(days=random.randint(1, 4))) if pos == "22" else None,
            })
            enc_id += 1

    return pd.DataFrame(encounters)


# ---------------------------------------------------------------------------
# Step 8 — Encounter diagnoses (System A)
# ---------------------------------------------------------------------------

def generate_encounter_diagnoses(encounters_df: pd.DataFrame) -> pd.DataFrame:
    icd_df = get_icd10_codes()
    icd_codes = icd_df["code"].tolist()
    rows = []

    for _, enc in encounters_df.iterrows():
        primary = random.choice(icd_codes)
        rows.append({
            "encounter_id": enc["encounter_id"],
            "dx_code": primary,
            "dx_description": icd_df[icd_df["code"] == primary]["description"].values[0],
            "dx_position": 1,
            "poa_flag": "Y",
        })
        if random.random() < 0.6:
            secondary = random.choice([c for c in icd_codes if c != primary])
            rows.append({
                "encounter_id": enc["encounter_id"],
                "dx_code": secondary,
                "dx_description": icd_df[icd_df["code"] == secondary]["description"].values[0],
                "dx_position": 2,
                "poa_flag": random.choice(["Y", "N"]),
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 9 — Charge lines (System A)
# ---------------------------------------------------------------------------

def generate_charge_lines(encounters_df: pd.DataFrame, providers_df: pd.DataFrame) -> pd.DataFrame:
    cpt_df = get_cpt_codes()
    rows = []
    charge_id = 1

    # Build NPI → specialty lookup
    npi_to_specialty = dict(zip(providers_df["npi"], providers_df["specialty"]))

    for _, enc in encounters_df.iterrows():
        specialty = npi_to_specialty.get(enc["rendering_npi"], "PCP")
        categories = CPT_CATEGORY_BY_SPECIALTY.get(specialty, ["E&M"])
        available = cpt_df[cpt_df["category"].isin(categories)]

        if len(available) == 0:
            available = cpt_df[cpt_df["category"] == "E&M"]

        n_lines = 1 if specialty not in ("PT", "Behavioral Health", "Home Health") else random.randint(2, 4)
        selected_cpts = available.sample(min(n_lines, len(available)))

        for _, cpt_row in selected_cpts.iterrows():
            units = random.randint(1, 4) if specialty in ("PT", "Home Health") else 1
            rate_range = {
                "E&M": (80, 350), "Lab": (20, 90), "Imaging": (150, 1800),
                "Surgery": (800, 6000), "PT": (60, 180),
                "Behavioral Health": (80, 250), "Home Health": (90, 300),
                "Cardiology": (200, 900), "Preventive": (40, 200),
            }
            lo, hi = rate_range.get(cpt_row["category"], (50, 500))
            charge_amount = round(random.uniform(lo, hi) * units, 2)

            rows.append({
                "charge_id": f"CHG{charge_id:08d}",
                "encounter_id": enc["encounter_id"],
                "cpt_code": cpt_row["code"],
                "cpt_modifier": random.choice(["", "25", "59", "GT", ""]),
                "units": units,
                "charge_date": enc["encounter_date"],
                "charge_amount": charge_amount,
                "revenue_code": f"{random.randint(100, 999)}",
            })
            charge_id += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 10 — Claims (System B)
# ---------------------------------------------------------------------------

def generate_claims(
    encounters_df: pd.DataFrame,
    patients_df: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    providers_df: pd.DataFrame,
    payers_df: pd.DataFrame,
) -> pd.DataFrame:
    mrn_to_eligibility = eligibility_df.groupby("mrn").first().reset_index()
    mrn_to_plan = dict(zip(mrn_to_eligibility["mrn"], mrn_to_eligibility["plan_id"]))
    mrn_to_member = dict(zip(mrn_to_eligibility["mrn"], mrn_to_eligibility["member_id"]))

    # Payer lookup via policy
    policy_to_payer = {}
    npi_to_payer_contracts = {}  # npi → list of payer_ids

    # Build NPI → payer_id lookup from providers_df
    npi_to_specialty = dict(zip(providers_df["npi"], providers_df["specialty"]))

    claims = []
    claim_id = 1

    # Map plan_id to payer_id (import from payers to look up plan's payer)
    # We'll need policies to do this lookup — fetch separately
    from src.generate.domains import get_payer_definitions
    payer_defs = get_payer_definitions()
    payer_id_set = {p["payer_id"] for p in payer_defs}

    for _, enc in encounters_df.iterrows():
        mrn = enc["mrn"]
        plan_id = mrn_to_plan.get(mrn)
        member_id = mrn_to_member.get(mrn)
        if plan_id is None:
            continue

        # Derive payer_id from plan_id prefix (PYR001 from PLNPYR001PPO etc.)
        # plan_id format: PLN{pyr_suffix}{pt} or PLN{pyr_suffix}{pt}_V1/_V2
        # Find payer by matching payer_id suffix
        payer_id = None
        for pdef in payer_defs:
            pid = pdef["payer_id"]
            if pid[-3:] in plan_id:
                payer_id = pid
                break
        if payer_id is None:
            payer_id = "PYR001"

        billing_npi = enc["rendering_npi"]  # simplified: billing = rendering
        rendering_npi = enc["rendering_npi"]

        # Referring NPI for specialist visits (used in S-06)
        specialty = npi_to_specialty.get(rendering_npi, "PCP")
        referring_npi = None
        if specialty not in ("PCP", "Emergency Medicine"):
            # Pick a random provider as referrer
            pcp_providers = providers_df[providers_df["specialty"] == "PCP"]
            if len(pcp_providers) > 0:
                referring_npi = pcp_providers.sample(1).iloc[0]["npi"]

        # Auth number placeholder (may be populated even if link is missing - S-01)
        auth_number = f"AUTH{random.randint(100000, 999999)}" if random.random() < 0.35 else None

        claims.append({
            "claim_id": f"CLM{claim_id:08d}",
            "mrn": mrn,
            "member_id": member_id,
            "billing_npi": billing_npi,
            "rendering_npi": rendering_npi,
            "referring_npi": referring_npi,
            "payer_id": payer_id,
            "plan_id": plan_id,
            "claim_date": enc["encounter_date"],
            "total_billed": 0.0,  # set after service lines
            "claim_type": "professional",
            "claim_status": "submitted",
            "auth_number": auth_number,
        })
        claim_id += 1

    return pd.DataFrame(claims)


# ---------------------------------------------------------------------------
# Step 11 — Claim service lines (System B)
# ---------------------------------------------------------------------------

def generate_service_lines(
    claims_df: pd.DataFrame,
    charge_lines_df: pd.DataFrame,
    encounters_df: pd.DataFrame,
    icd10_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    enc_to_claim = {}
    for _, row in claims_df.iterrows():
        # Link claims to encounters by mrn + claim_date matching encounter_date
        pass  # built below

    # Build encounter_id → claim_id map via mrn + date
    enc_map = encounters_df[["encounter_id", "mrn", "encounter_date"]].copy()
    clm_map = claims_df[["claim_id", "mrn", "claim_date"]].copy()
    clm_map = clm_map.rename(columns={"claim_date": "encounter_date"})
    merged = enc_map.merge(clm_map, on=["mrn", "encounter_date"], how="inner")
    enc_to_claim = dict(zip(merged["encounter_id"], merged["claim_id"]))

    lines = []
    line_id = 1
    claim_totals = {}

    for _, chg in charge_lines_df.iterrows():
        claim_id = enc_to_claim.get(chg["encounter_id"])
        if claim_id is None:
            continue

        # Primary ICD-10 for this service line (pick a common one)
        icd_codes = icd10_df["code"].tolist()
        lines.append({
            "line_id": f"LN{line_id:09d}",
            "claim_id": claim_id,
            "cpt_code": chg["cpt_code"],
            "modifier": chg["cpt_modifier"],
            "icd10_primary": random.choice(icd_codes),
            "icd10_secondary": random.choice(icd_codes) if random.random() < 0.5 else None,
            "units": chg["units"],
            "line_billed": chg["charge_amount"],
            "service_date": chg["charge_date"],
        })
        claim_totals[claim_id] = claim_totals.get(claim_id, 0) + chg["charge_amount"]
        line_id += 1

    lines_df = pd.DataFrame(lines)

    # Update claim totals
    claims_df = claims_df.copy()
    claims_df["total_billed"] = claims_df["claim_id"].map(claim_totals).fillna(0).round(2)

    return lines_df, claims_df


# ---------------------------------------------------------------------------
# Step 12 — Authorizations (System D)
# ---------------------------------------------------------------------------

def generate_authorizations(
    claims_df: pd.DataFrame,
    service_lines_df: pd.DataFrame,
    payers_df: pd.DataFrame,
) -> pd.DataFrame:
    auth_required = get_auth_required_cpts()
    rows = []
    auth_id = 1

    # Find claims with auth-required CPT codes
    auth_lines = service_lines_df[service_lines_df["cpt_code"].isin(auth_required)]
    auth_claim_ids = auth_lines["claim_id"].unique().tolist()

    # ~80% of auth-required claims get an authorization
    selected = random.sample(auth_claim_ids, int(len(auth_claim_ids) * 0.80))

    claims_map = claims_df.set_index("claim_id")

    for cid in selected:
        if cid not in claims_map.index:
            continue
        claim = claims_map.loc[cid]
        claim_date = pd.to_datetime(claim["claim_date"]).date()

        # Determine specialty from primary CPT
        cpt = auth_lines[auth_lines["claim_id"] == cid]["cpt_code"].iloc[0]
        is_units_based = cpt.startswith(("971", "908", "G02", "G03", "G01"))
        approved_units = random.randint(4, 20) if is_units_based else 1

        auth_date = claim_date - timedelta(days=random.randint(1, 14))
        expiry = auth_date + timedelta(days=random.randint(60, 180))

        rows.append({
            "auth_id": f"AUT{auth_id:07d}",
            "mrn": claim["mrn"],
            "payer_id": claim["payer_id"],
            "requesting_npi": claim["billing_npi"],
            "auth_date": str(auth_date),
            "expiry_date": str(expiry),
            "status": "approved",
            "approved_units": approved_units,
            "linked_claim_id": cid,  # internal — used to build claim_auth_link
        })
        auth_id += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 13 — Auth details (System D)
# ---------------------------------------------------------------------------

def generate_auth_details(
    auths_df: pd.DataFrame,
    service_lines_df: pd.DataFrame,
) -> pd.DataFrame:
    auth_required = get_auth_required_cpts()
    rows = []
    detail_id = 1

    for _, auth in auths_df.iterrows():
        cid = auth.get("linked_claim_id")
        if cid:
            lines = service_lines_df[
                (service_lines_df["claim_id"] == cid) &
                (service_lines_df["cpt_code"].isin(auth_required))
            ]
            for _, line in lines.iterrows():
                rows.append({
                    "auth_detail_id": f"ADTL{detail_id:07d}",
                    "auth_id": auth["auth_id"],
                    "cpt_code": line["cpt_code"],
                    "icd10_code": line["icd10_primary"],
                    "approved_units": auth["approved_units"],
                })
                detail_id += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 14 — claim_auth_link (System D) — intentionally ~90% complete
# ---------------------------------------------------------------------------

def generate_claim_auth_link(auths_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    link_date = TODAY - timedelta(days=30)

    for _, auth in auths_df.iterrows():
        cid = auth.get("linked_claim_id")
        if cid and random.random() < 0.90:  # leave ~10% unlinked (for S-01)
            rows.append({
                "claim_id": cid,
                "auth_id": auth["auth_id"],
                "linked_date": str(link_date),
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 15 — Referral orders (System E)
# ---------------------------------------------------------------------------

def generate_referral_orders(
    encounters_df: pd.DataFrame,
    claims_df: pd.DataFrame,
    patients_df: pd.DataFrame,
    providers_df: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    policies_df: pd.DataFrame,
) -> pd.DataFrame:
    hmo_payer_ids = get_hmo_payer_ids()

    # Find HMO plan_ids
    hmo_plan_ids = policies_df[policies_df["plan_type"] == "HMO"]["plan_id"].tolist()
    hmo_mrns = eligibility_df[eligibility_df["plan_id"].isin(hmo_plan_ids)]["mrn"].tolist()

    pcp_providers = providers_df[providers_df["specialty"] == "PCP"]
    specialist_npis = providers_df[
        (providers_df["specialty"] != "PCP") &
        (providers_df.get("s02_uncredentialed", False) != True)
    ]["npi"].tolist() if "s02_uncredentialed" in providers_df.columns else providers_df[providers_df["specialty"] != "PCP"]["npi"].tolist()

    rows = []
    ref_id = 1

    for _, enc in encounters_df.iterrows():
        mrn = enc["mrn"]
        if mrn not in hmo_mrns:
            continue
        if enc["rendering_npi"] not in specialist_npis:
            continue
        if random.random() > 0.85:  # not all HMO specialist visits get referrals (gap = S-06)
            continue

        referrer = pcp_providers.sample(1).iloc[0]
        enc_date = pd.to_datetime(enc["encounter_date"]).date()
        referral_date = enc_date - timedelta(days=random.randint(1, 14))

        rows.append({
            "referral_id": f"REF{ref_id:07d}",
            "mrn": mrn,
            "referring_npi": referrer["npi"],
            "referred_to_npi": enc["rendering_npi"],
            "plan_id": eligibility_df[eligibility_df["mrn"] == mrn]["plan_id"].values[0]
            if len(eligibility_df[eligibility_df["mrn"] == mrn]) > 0 else None,
            "referral_date": str(referral_date),
            "expiry_date": str(referral_date + timedelta(days=90)),
            "cpt_code": None,
        })
        ref_id += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def generate_all():
    print("Generating synthetic RCM data...")

    # Load reference data
    cpt_df = get_cpt_codes()
    icd10_df = get_icd10_codes()

    print("\n[1/15] Payers + PayerPolicies")
    payers_df, policies_df = generate_payers()
    _save(payers_df, "system_c_payer", "payer_master.csv")
    _save(policies_df, "system_c_payer", "insurance_plan.csv")

    print("\n[2/15] Providers")
    providers_df = generate_providers(n=38)
    # Remove internal marker before saving
    save_providers = providers_df.drop(columns=["s02_uncredentialed"], errors="ignore")
    # Add marker back as a flag column for the contracts generator
    providers_df["s02_uncredentialed"] = providers_df.get("s02_uncredentialed", False)
    _save(save_providers, "system_e_provider", "provider_master.csv")

    print("\n[3/15] Contracts")
    contracts_df = generate_contracts(providers_df, payers_df)
    _save(contracts_df, "system_e_provider", "provider_payer_contract.csv")

    print("\n[4/15] Fee schedules")
    fee_df = generate_fee_schedules(contracts_df)
    _save(fee_df, "system_e_provider", "fee_schedule.csv")

    print("\n[5/15] Patients")
    patients_df = generate_patients(n=1000)
    save_patients = patients_df.drop(columns=["primary_payer_id"])
    _save(save_patients, "system_a_emr", "pt_demographics.csv")

    print("\n[6/15] Member eligibility")
    eligibility_df = generate_eligibility(patients_df, policies_df)
    _save(eligibility_df, "system_c_payer", "member_eligibility.csv")

    print("\n[7/15] Encounters")
    encounters_df = generate_encounters(patients_df, providers_df)
    _save(encounters_df, "system_a_emr", "encounter.csv")

    print("\n[8/15] Encounter diagnoses")
    enc_dx_df = generate_encounter_diagnoses(encounters_df)
    _save(enc_dx_df, "system_a_emr", "encounter_dx.csv")

    print("\n[9/15] Charge lines")
    charge_df = generate_charge_lines(encounters_df, providers_df)
    _save(charge_df, "system_a_emr", "charge_line.csv")

    print("\n[10/15] Claims")
    claims_df = generate_claims(encounters_df, patients_df, eligibility_df, providers_df, payers_df)

    print("\n[11/15] Claim service lines")
    lines_df, claims_df = generate_service_lines(claims_df, charge_df, encounters_df, icd10_df)
    _save(claims_df, "system_b_claims", "claim_header.csv")
    _save(lines_df, "system_b_claims", "claim_service_line.csv")

    print("\n[12/15] Authorizations")
    auths_df = generate_authorizations(claims_df, lines_df, payers_df)

    print("\n[13/15] Auth details")
    auth_details_df = generate_auth_details(auths_df, lines_df)

    print("\n[14/15] claim_auth_link")
    auth_link_df = generate_claim_auth_link(auths_df)

    # Save auth files (drop internal column)
    _save(auths_df.drop(columns=["linked_claim_id"]), "system_d_auth", "auth_request.csv")
    _save(auth_details_df, "system_d_auth", "auth_detail.csv")
    _save(auth_link_df, "system_d_auth", "claim_auth_link.csv")

    print("\n[15/15] Referral orders")
    referrals_df = generate_referral_orders(
        encounters_df, claims_df, patients_df, providers_df, eligibility_df, policies_df
    )
    _save(referrals_df, "system_e_provider", "referral_order.csv")

    print(f"\nGeneration complete.")
    print(f"  Patients:    {len(patients_df):>6}")
    print(f"  Encounters:  {len(encounters_df):>6}")
    print(f"  Claims:      {len(claims_df):>6}")
    print(f"  Providers:   {len(providers_df):>6}")
    print(f"  Auths:       {len(auths_df):>6}")
    print(f"  Referrals:   {len(referrals_df):>6}")


if __name__ == "__main__":
    generate_all()
