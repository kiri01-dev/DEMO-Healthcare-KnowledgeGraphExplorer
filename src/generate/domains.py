"""
domains.py — Reference data loader and domain definitions.

Loads CPT and ICD-10 reference CSVs; defines payer mix, specialty mix,
and auth-required CPT list used by the data generator.
"""

import os
import pandas as pd

# Locate reference data relative to project root
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REF_DIR = os.path.join(_THIS_DIR, "..", "..", "data", "reference")


def get_cpt_codes() -> pd.DataFrame:
    """Return CPT code reference table."""
    path = os.path.join(_REF_DIR, "cpt_codes.csv")
    df = pd.read_csv(path)
    df["requires_auth"] = df["requires_auth"].astype(bool)
    # Drop duplicates on code (keep first)
    df = df.drop_duplicates(subset=["code"]).reset_index(drop=True)
    return df


def get_icd10_codes() -> pd.DataFrame:
    """Return ICD-10 code reference table."""
    path = os.path.join(_REF_DIR, "icd10_codes.csv")
    return pd.read_csv(path)


def get_auth_required_cpts() -> list:
    """Return list of CPT codes that require prior authorization."""
    df = get_cpt_codes()
    return df[df["requires_auth"] == True]["code"].tolist()


def get_cpts_by_category(category: str) -> list:
    """Return list of CPT codes for a given category."""
    df = get_cpt_codes()
    return df[df["category"] == category]["code"].tolist()


def get_payer_definitions() -> list:
    """
    Return canonical payer definitions.
    Each entry: {payer_id, payer_name, payer_type, plan_types, weight}
    weight drives patient assignment probability (must sum to 1.0).
    """
    return [
        {
            "payer_id": "PYR001",
            "payer_name": "Medicare FFS",
            "payer_type": "Medicare",
            "plan_types": ["PPO"],
            "weight": 0.15,
        },
        {
            "payer_id": "PYR002",
            "payer_name": "Medicare Advantage",
            "payer_type": "Medicare",
            "plan_types": ["PPO"],
            "weight": 0.08,
        },
        {
            "payer_id": "PYR003",
            "payer_name": "State Medicaid MCO",
            "payer_type": "Medicaid",
            "plan_types": ["PPO"],   # Medicaid MCO is PPO-type; HMO quota met by PYR007/008
            "weight": 0.18,
        },
        {
            "payer_id": "PYR004",
            "payer_name": "BlueCross BlueShield PPO",
            "payer_type": "commercial",
            "plan_types": ["PPO"],
            "weight": 0.13,
        },
        {
            "payer_id": "PYR005",
            "payer_name": "Aetna PPO",
            "payer_type": "commercial",
            "plan_types": ["PPO"],
            "weight": 0.10,
        },
        {
            "payer_id": "PYR006",
            "payer_name": "UnitedHealthcare PPO",
            "payer_type": "commercial",
            "plan_types": ["PPO"],
            "weight": 0.10,
        },
        {
            "payer_id": "PYR007",
            "payer_name": "Humana HMO",
            "payer_type": "commercial",
            "plan_types": ["HMO"],
            "weight": 0.15,
        },
        {
            "payer_id": "PYR008",
            "payer_name": "Cigna HMO",
            "payer_type": "commercial",
            "plan_types": ["HMO"],
            "weight": 0.10,
        },
    ]


def get_hmo_payer_ids() -> list:
    """Return list of payer_ids that are HMO plans."""
    return [p["payer_id"] for p in get_payer_definitions()
            if "HMO" in p["plan_types"]]


def get_specialty_mix() -> dict:
    """
    Return specialty → proportion mapping for provider generation.
    PT/behavioral health/home health must total ~20% (DR-05).
    """
    return {
        "PCP":                0.22,
        "Cardiology":         0.07,
        "Orthopedics":        0.07,
        "Gastroenterology":   0.05,
        "Neurology":          0.04,
        "Oncology":           0.03,
        "Ophthalmology":      0.03,
        "General Surgery":    0.05,
        "PT":                 0.15,   # physical therapy — must reach ~20% combined
        "Behavioral Health":  0.12,   # behavioral health / psychiatry
        "Home Health":        0.06,   # home health agency
        "Radiology":          0.05,
        "Emergency Medicine": 0.06,
    }


# CPT categories by clinical use (used by generator for encounter → CPT assignment)
CPT_CATEGORY_BY_SPECIALTY = {
    "PCP":                ["E&M", "Lab", "Preventive"],
    "Cardiology":         ["E&M", "Cardiology", "Imaging", "Lab"],
    "Orthopedics":        ["E&M", "Surgery", "Imaging", "PT"],
    "Gastroenterology":   ["E&M", "Surgery", "Lab"],
    "Neurology":          ["E&M", "Imaging", "Lab"],
    "Oncology":           ["E&M", "Imaging", "Lab"],
    "Ophthalmology":      ["E&M", "Surgery"],
    "General Surgery":    ["E&M", "Surgery", "Imaging"],
    "PT":                 ["PT"],
    "Behavioral Health":  ["Behavioral Health"],
    "Home Health":        ["Home Health"],
    "Radiology":          ["Imaging"],
    "Emergency Medicine": ["E&M", "Lab", "Imaging"],
}

# Payers that will have contract version pairs (for S-03 scenario)
S03_RENEWAL_PAYER_IDS = ["PYR004", "PYR007"]

# S-02: payers for which uncredentialed rendering providers will be added
S02_TARGET_PAYER_IDS = ["PYR004", "PYR005"]
