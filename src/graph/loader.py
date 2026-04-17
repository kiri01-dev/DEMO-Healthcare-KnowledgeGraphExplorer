"""
loader.py — Schema setup, baseline data loader, and DetectionRule loader.

All loading uses UNWIND batch pattern for performance.
setup_schema() is idempotent (IF NOT EXISTS on all constraints).
"""

import os
import yaml
import pandas as pd
from neo4j import Driver

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

CONSTRAINTS = [
    "CREATE CONSTRAINT patient_id_unique IF NOT EXISTS FOR (p:Patient) REQUIRE p.patient_id IS UNIQUE",
    "CREATE CONSTRAINT claim_id_unique    IF NOT EXISTS FOR (c:Claim)   REQUIRE c.claim_id   IS UNIQUE",
    "CREATE CONSTRAINT visit_id_unique    IF NOT EXISTS FOR (v:Visit)   REQUIRE v.visit_id   IS UNIQUE",
    "CREATE CONSTRAINT provider_npi_unique IF NOT EXISTS FOR (pr:Provider) REQUIRE pr.npi    IS UNIQUE",
    "CREATE CONSTRAINT payer_id_unique    IF NOT EXISTS FOR (py:Payer)  REQUIRE py.payer_id  IS UNIQUE",
    "CREATE CONSTRAINT policy_id_unique   IF NOT EXISTS FOR (pp:PayerPolicy) REQUIRE pp.policy_id IS UNIQUE",
    "CREATE CONSTRAINT cpt_code_unique    IF NOT EXISTS FOR (c:CPT_Code) REQUIRE c.code      IS UNIQUE",
    "CREATE CONSTRAINT icd10_code_unique  IF NOT EXISTS FOR (d:ICD10_Code) REQUIRE d.code    IS UNIQUE",
    "CREATE CONSTRAINT auth_id_unique     IF NOT EXISTS FOR (a:Authorization) REQUIRE a.auth_id IS UNIQUE",
    "CREATE CONSTRAINT contract_id_unique IF NOT EXISTS FOR (c:Contract) REQUIRE c.contract_id IS UNIQUE",
    "CREATE CONSTRAINT referral_id_unique IF NOT EXISTS FOR (r:ReferralOrder) REQUIRE r.referral_id IS UNIQUE",
    "CREATE CONSTRAINT coverage_id_unique IF NOT EXISTS FOR (c:Coverage) REQUIRE c.coverage_id IS UNIQUE",
    "CREATE CONSTRAINT rule_id_unique     IF NOT EXISTS FOR (r:DetectionRule) REQUIRE r.rule_id IS UNIQUE",
    "CREATE CONSTRAINT finding_id_unique  IF NOT EXISTS FOR (f:Finding) REQUIRE f.finding_id IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX claim_date_idx       IF NOT EXISTS FOR (c:Claim) ON (c.claim_date)",
    "CREATE INDEX claim_flaw_idx       IF NOT EXISTS FOR (c:Claim) ON (c.is_flawed, c.flaw_scenario)",
    "CREATE INDEX coverage_dates_idx   IF NOT EXISTS FOR (c:Coverage) ON (c.start_date, c.end_date)",
    "CREATE INDEX contract_dates_idx   IF NOT EXISTS FOR (c:Contract) ON (c.effective_date, c.termination_date)",
    "CREATE INDEX policy_dates_idx     IF NOT EXISTS FOR (p:PayerPolicy) ON (p.effective_date, p.termination_date)",
    "CREATE INDEX finding_status_idx   IF NOT EXISTS FOR (f:Finding) ON (f.status)",
    "CREATE INDEX finding_detected_idx IF NOT EXISTS FOR (f:Finding) ON (f.detected_at)",
    "CREATE INDEX patient_zip_dob_idx  IF NOT EXISTS FOR (p:Patient) ON (p.zip, p.dob)",
]


def setup_schema(driver: Driver) -> None:
    """Create all constraints and indexes. Safe to run multiple times."""
    with driver.session() as session:
        for stmt in CONSTRAINTS:
            session.run(stmt)
        for stmt in INDEXES:
            session.run(stmt)


# ---------------------------------------------------------------------------
# Reference data loaders
# ---------------------------------------------------------------------------

def _batch_run(session, cypher: str, rows: list, batch_size: int = 500):
    for i in range(0, len(rows), batch_size):
        session.run(cypher, rows=rows[i:i + batch_size])


def load_cpt_codes(driver: Driver, ref_dir: str) -> int:
    df = pd.read_csv(os.path.join(ref_dir, "cpt_codes.csv"))
    df = df.drop_duplicates(subset=["code"])
    df["requires_auth"] = df["requires_auth"].astype(bool)
    rows = df.to_dict("records")

    with driver.session() as session:
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (c:CPT_Code {code: row.code})
            SET c.description   = row.description,
                c.category      = row.category,
                c.requires_auth = row.requires_auth
        """, rows)
    return len(rows)


def load_icd10_codes(driver: Driver, ref_dir: str) -> int:
    df = pd.read_csv(os.path.join(ref_dir, "icd10_codes.csv"))
    rows = df.to_dict("records")

    with driver.session() as session:
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (d:ICD10_Code {code: row.code})
            SET d.description = row.description,
                d.category    = row.category
        """, rows)
    return len(rows)


# ---------------------------------------------------------------------------
# System C — Payers and PayerPolicies
# ---------------------------------------------------------------------------

def load_payers(driver: Driver, gen_dir: str) -> int:
    df = pd.read_csv(os.path.join(gen_dir, "system_c_payer", "payer_master.csv"))
    rows = df.fillna("").to_dict("records")
    with driver.session() as session:
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (py:Payer {payer_id: row.payer_id})
            SET py.payer_name       = row.payer_name,
                py.payer_type       = row.payer_type,
                py.clearinghouse_id = row.clearinghouse_id
        """, rows)
    return len(rows)


def load_payer_policies(driver: Driver, gen_dir: str) -> int:
    df = pd.read_csv(os.path.join(gen_dir, "system_c_payer", "insurance_plan.csv"))
    df["term_date"] = df["term_date"].fillna("")
    rows = df.to_dict("records")

    with driver.session() as session:
        # Load PayerPolicy nodes
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (pp:PayerPolicy {policy_id: row.plan_id})
            SET pp.plan_name       = row.plan_name,
                pp.plan_type       = row.plan_type,
                pp.effective_date  = row.effective_date,
                pp.termination_date = CASE WHEN row.term_date = '' THEN null ELSE row.term_date END,
                pp.version         = toInteger(row.version_num)
        """, rows)
        # HAS_POLICY edges (Payer → PayerPolicy)
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (py:Payer {payer_id: row.payer_id})
            MATCH (pp:PayerPolicy {policy_id: row.plan_id})
            MERGE (py)-[:HAS_POLICY]->(pp)
        """, rows)

    # POLICY_SUPERSEDED_BY edges — v1 → v2 per payer
    _create_policy_superseded_by(driver, df)
    return len(rows)


def _create_policy_superseded_by(driver: Driver, policies_df: pd.DataFrame):
    """Link expired policy versions to their replacements."""
    for payer_id, group in policies_df.groupby("payer_id"):
        if group["version_num"].max() < 2:
            continue
        v1 = group[group["version_num"] == 1]
        v2 = group[group["version_num"] == 2]
        for _, r1 in v1.iterrows():
            for _, r2 in v2.iterrows():
                with driver.session() as session:
                    session.run("""
                        MATCH (p1:PayerPolicy {policy_id: $p1_id})
                        MATCH (p2:PayerPolicy {policy_id: $p2_id})
                        MERGE (p1)-[:POLICY_SUPERSEDED_BY]->(p2)
                    """, p1_id=r1["plan_id"], p2_id=r2["plan_id"])


# ---------------------------------------------------------------------------
# System E — Providers and Contracts
# ---------------------------------------------------------------------------

def load_providers(driver: Driver, gen_dir: str) -> int:
    df = pd.read_csv(os.path.join(gen_dir, "system_e_provider", "provider_master.csv"))
    df = df.fillna("")
    rows = df.to_dict("records")
    with driver.session() as session:
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (p:Provider {npi: row.npi})
            SET p.provider_id   = row.npi,
                p.name          = row.first_name + ' ' + row.last_name,
                p.last_name     = row.last_name,
                p.first_name    = row.first_name,
                p.specialty     = row.specialty,
                p.provider_type = row.provider_type,
                p.tax_id        = row.tax_id,
                p.license_state = row.license_state,
                p.license_num   = row.license_num,
                p.excluded_flag = toBoolean(row.excluded_flag)
        """, rows)
    return len(rows)


def load_contracts(driver: Driver, gen_dir: str) -> int:
    df = pd.read_csv(os.path.join(gen_dir, "system_e_provider", "provider_payer_contract.csv"))
    df["term_date"] = df["term_date"].fillna("")
    rows = df.to_dict("records")

    with driver.session() as session:
        # Contract nodes
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (c:Contract {contract_id: row.contract_id})
            SET c.effective_date    = row.effective_date,
                c.termination_date  = CASE WHEN row.term_date = '' THEN null ELSE row.term_date END,
                c.fee_schedule      = row.fee_schedule_id,
                c.version_num       = toInteger(row.version_num),
                c.contract_type     = row.contract_type
        """, rows)

        # CONTRACTED_WITH: Provider → Contract
        # In clean baseline, providers are connected to v2 (current) contracts only.
        # For payers with v1/v2, link provider to v2 only.
        v2_rows = [r for r in rows if r.get("version_num", 1) == 2]
        v1_only_rows = [r for r in rows if r.get("version_num", 1) == 1 and
                        not any(r2.get("npi") == r["npi"] and r2.get("payer_id") == r["payer_id"]
                                for r2 in rows if r2.get("version_num", 1) == 2)]
        active_rows = v2_rows + v1_only_rows

        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (p:Provider {npi: row.npi})
            MATCH (c:Contract {contract_id: row.contract_id})
            MERGE (p)-[:CONTRACTED_WITH]->(c)
        """, active_rows)

        # CONTRACT_WITH_PAYER: Contract → Payer
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (c:Contract {contract_id: row.contract_id})
            MATCH (py:Payer {payer_id: row.payer_id})
            MERGE (c)-[:CONTRACT_WITH_PAYER]->(py)
        """, rows)

    # SUPERSEDED_BY edges: v1 → v2 per (npi, payer_id)
    _create_contract_superseded_by(driver, df)
    return len(rows)


def _create_contract_superseded_by(driver: Driver, contracts_df: pd.DataFrame):
    """Link expired contract versions to their replacements."""
    for (npi, payer_id), group in contracts_df.groupby(["npi", "payer_id"]):
        if group["version_num"].max() < 2:
            continue
        v1 = group[group["version_num"] == 1]
        v2 = group[group["version_num"] == 2]
        for _, r1 in v1.iterrows():
            for _, r2 in v2.iterrows():
                with driver.session() as session:
                    session.run("""
                        MATCH (c1:Contract {contract_id: $c1_id})
                        MATCH (c2:Contract {contract_id: $c2_id})
                        MERGE (c1)-[:SUPERSEDED_BY]->(c2)
                    """, c1_id=r1["contract_id"], c2_id=r2["contract_id"])


# ---------------------------------------------------------------------------
# System A — Patients, Visits, Diagnoses, Charge lines
# ---------------------------------------------------------------------------

def load_patients(driver: Driver, gen_dir: str) -> int:
    df = pd.read_csv(os.path.join(gen_dir, "system_a_emr", "pt_demographics.csv"))
    df = df.fillna("")
    rows = df.to_dict("records")
    with driver.session() as session:
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (p:Patient {patient_id: row.mrn})
            SET p.mrn        = row.mrn,
                p.last_name  = row.last_name,
                p.first_name = row.first_name,
                p.dob        = row.dob,
                p.sex        = row.sex,
                p.zip        = row.zip,
                p.race       = row.race,
                p.language   = row.language
        """, rows)
    return len(rows)


def load_visits(driver: Driver, gen_dir: str) -> int:
    df = pd.read_csv(os.path.join(gen_dir, "system_a_emr", "encounter.csv"))
    df = df.fillna("")
    rows = df.to_dict("records")

    with driver.session() as session:
        # Visit nodes
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (v:Visit {visit_id: row.encounter_id})
            SET v.visit_date       = row.encounter_date,
                v.visit_type       = row.encounter_type,
                v.place_of_service = row.place_of_service,
                v.facility_id      = row.facility_id
        """, rows)
        # HAD_VISIT: Patient → Visit
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (p:Patient {patient_id: row.mrn})
            MATCH (v:Visit {visit_id: row.encounter_id})
            MERGE (p)-[:HAD_VISIT]->(v)
        """, rows)
    return len(rows)


# ---------------------------------------------------------------------------
# System C — Coverage / Eligibility
# ---------------------------------------------------------------------------

def load_coverages(driver: Driver, gen_dir: str) -> int:
    df = pd.read_csv(os.path.join(gen_dir, "system_c_payer", "member_eligibility.csv"))
    df["end_date"] = df["end_date"].fillna("")
    rows = df.to_dict("records")

    with driver.session() as session:
        # Coverage nodes
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (cov:Coverage {coverage_id: row.eligibility_id})
            SET cov.member_id  = row.member_id,
                cov.start_date = row.start_date,
                cov.end_date   = CASE WHEN row.end_date = '' THEN null ELSE row.end_date END,
                cov.copay      = toFloat(row.copay),
                cov.deductible = toFloat(row.deductible)
        """, rows)
        # ENROLLED_IN: Patient → Coverage
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (p:Patient {patient_id: row.mrn})
            MATCH (cov:Coverage {coverage_id: row.eligibility_id})
            MERGE (p)-[:ENROLLED_IN {enrollment_date: row.start_date}]->(cov)
        """, rows)
        # COVERED_BY: Coverage → PayerPolicy
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (cov:Coverage {coverage_id: row.eligibility_id})
            MATCH (pp:PayerPolicy {policy_id: row.plan_id})
            MERGE (cov)-[:COVERED_BY]->(pp)
        """, rows)
    return len(rows)


# ---------------------------------------------------------------------------
# System B — Claims
# ---------------------------------------------------------------------------

def load_claims(driver: Driver, gen_dir: str) -> int:
    df = pd.read_csv(os.path.join(gen_dir, "system_b_claims", "claim_header.csv"))
    df = df.fillna("")
    rows = df.to_dict("records")

    with driver.session() as session:
        # Claim nodes
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (c:Claim {claim_id: row.claim_id})
            SET c.claim_date    = row.claim_date,
                c.billed_amount = toFloat(row.total_billed),
                c.claim_status  = row.claim_status,
                c.claim_type    = row.claim_type,
                c.auth_number   = CASE WHEN row.auth_number = '' THEN null ELSE row.auth_number END
        """, rows)

        # GENERATED_CLAIM: Visit → Claim (join on mrn + date)
        # We link via encounter_id through charge lines instead — use a two-step approach
        # First: build an encounter_id_from_service_lines lookup
        # For now: link Visit→Claim via mrn + date match
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (v:Visit {visit_date: row.claim_date})<-[:HAD_VISIT]-(p:Patient {patient_id: row.mrn})
            MATCH (c:Claim {claim_id: row.claim_id})
            MERGE (v)-[:GENERATED_CLAIM]->(c)
        """, rows)

        # SUBMITTED_TO: Claim → Payer
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (c:Claim {claim_id: row.claim_id})
            MATCH (py:Payer {payer_id: row.payer_id})
            MERGE (c)-[:SUBMITTED_TO {submission_date: row.claim_date}]->(py)
        """, rows)

        # BILLED_BY billing: Claim → Provider (billing NPI)
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (c:Claim {claim_id: row.claim_id})
            MATCH (p:Provider {npi: row.billing_npi})
            MERGE (c)-[:BILLED_BY {billing_role: 'billing'}]->(p)
        """, rows)

        # BILLED_BY rendering: Claim → Provider (rendering NPI)
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (c:Claim {claim_id: row.claim_id})
            MATCH (p:Provider {npi: row.rendering_npi})
            MERGE (c)-[:BILLED_BY {billing_role: 'rendering'}]->(p)
        """, rows)

        # COVERED_UNDER: Claim → Coverage (via member_id)
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (c:Claim {claim_id: row.claim_id})
            MATCH (cov:Coverage {member_id: row.member_id})
            MERGE (c)-[:COVERED_UNDER]->(cov)
        """, rows)

    return len(rows)


def load_service_lines(driver: Driver, gen_dir: str) -> int:
    df = pd.read_csv(os.path.join(gen_dir, "system_b_claims", "claim_service_line.csv"))
    df = df.fillna("")
    rows = df.to_dict("records")

    with driver.session() as session:
        # BILLED_PROCEDURE: Claim → CPT_Code
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (c:Claim {claim_id: row.claim_id})
            MATCH (cpt:CPT_Code {code: row.cpt_code})
            MERGE (c)-[r:BILLED_PROCEDURE {modifier: row.modifier}]->(cpt)
            SET r.units = toInteger(row.units)
        """, rows)

        # CODED_DIAGNOSIS: Claim → ICD10_Code (primary)
        primary_rows = [r for r in rows if r.get("icd10_primary", "")]
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (c:Claim {claim_id: row.claim_id})
            MATCH (dx:ICD10_Code {code: row.icd10_primary})
            MERGE (c)-[:CODED_DIAGNOSIS {dx_position: 'primary'}]->(dx)
        """, primary_rows)

    return len(rows)


# ---------------------------------------------------------------------------
# System D — Authorizations
# ---------------------------------------------------------------------------

def load_authorizations(driver: Driver, gen_dir: str) -> int:
    auth_df = pd.read_csv(os.path.join(gen_dir, "system_d_auth", "auth_request.csv"))
    auth_df = auth_df.fillna("")
    detail_df = pd.read_csv(os.path.join(gen_dir, "system_d_auth", "auth_detail.csv"))
    link_df = pd.read_csv(os.path.join(gen_dir, "system_d_auth", "claim_auth_link.csv"))

    auth_rows = auth_df.to_dict("records")
    with driver.session() as session:
        # Authorization nodes
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (a:Authorization {auth_id: row.auth_id})
            SET a.auth_date      = row.auth_date,
                a.expiry_date    = row.expiry_date,
                a.auth_status    = row.status,
                a.approved_units = toInteger(row.approved_units)
        """, auth_rows)

        # AUTH_GRANTED_BY: Authorization → Payer
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (a:Authorization {auth_id: row.auth_id})
            MATCH (py:Payer {payer_id: row.payer_id})
            MERGE (a)-[:AUTH_GRANTED_BY]->(py)
        """, auth_rows)

        # AUTH_FOR_PROCEDURE: Authorization → CPT_Code (from auth_detail)
        detail_rows = detail_df.to_dict("records")
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (a:Authorization {auth_id: row.auth_id})
            MATCH (cpt:CPT_Code {code: row.cpt_code})
            MERGE (a)-[:AUTH_FOR_PROCEDURE]->(cpt)
        """, detail_rows)

        # HAS_AUTHORIZATION: Claim → Authorization (from claim_auth_link)
        link_rows = link_df.to_dict("records")
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (c:Claim {claim_id: row.claim_id})
            MATCH (a:Authorization {auth_id: row.auth_id})
            MERGE (c)-[:HAS_AUTHORIZATION]->(a)
        """, link_rows)

    return len(auth_rows)


# ---------------------------------------------------------------------------
# System E — Referral orders
# ---------------------------------------------------------------------------

def load_referrals(driver: Driver, gen_dir: str) -> int:
    df = pd.read_csv(os.path.join(gen_dir, "system_e_provider", "referral_order.csv"))
    df = df.fillna("")
    rows = df.to_dict("records")

    with driver.session() as session:
        # ReferralOrder nodes
        _batch_run(session, """
            UNWIND $rows AS row
            MERGE (ro:ReferralOrder {referral_id: row.referral_id})
            SET ro.order_date          = row.referral_date,
                ro.expiry_date         = row.expiry_date,
                ro.referring_provider_id = row.referring_npi
        """, rows)

        # HAS_REFERRAL: Claim → ReferralOrder
        # Link via mrn + referred_to_npi + date (approximate join)
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (c:Claim)-[:BILLED_BY {billing_role:'rendering'}]->(rp:Provider {npi: row.referred_to_npi})
            MATCH (p:Patient {patient_id: row.mrn})-[:HAD_VISIT]->(v:Visit)-[:GENERATED_CLAIM]->(c)
            WHERE v.visit_date >= row.referral_date
            MATCH (ro:ReferralOrder {referral_id: row.referral_id})
            MERGE (c)-[:HAS_REFERRAL]->(ro)
        """, rows)

        # REFERRED_BY: ReferralOrder → Provider (referring PCP)
        _batch_run(session, """
            UNWIND $rows AS row
            MATCH (ro:ReferralOrder {referral_id: row.referral_id})
            MATCH (p:Provider {npi: row.referring_npi})
            MERGE (ro)-[:REFERRED_BY]->(p)
        """, [r for r in rows if r.get("referring_npi", "")])

    return len(rows)


# ---------------------------------------------------------------------------
# DetectionRule loader
# ---------------------------------------------------------------------------

def load_detection_rules(driver: Driver, rules_path: str) -> int:
    with open(rules_path, "r") as f:
        data = yaml.safe_load(f)

    rules = data.get("rules", [])
    rows = []
    for r in rules:
        rows.append({
            "rule_id":     r["rule_id"],
            "name":        r["name"],
            "category":    r["category"],
            "severity":    r["severity"],
            "risk_type":   r["risk_type"],
            "description": r["description"],
            "applies_to":  r["applies_to"],
            "version":     r["version"],
            "active":      r["active"],
            "cypher":      r["cypher"].strip(),
        })

    with driver.session() as session:
        for row in rows:
            session.run("""
                MERGE (r:DetectionRule {rule_id: $rule_id})
                SET r.name        = $name,
                    r.category    = $category,
                    r.severity    = $severity,
                    r.risk_type   = $risk_type,
                    r.description = $description,
                    r.applies_to  = $applies_to,
                    r.version     = $version,
                    r.active      = $active,
                    r.cypher      = $cypher
            """, **row)

    return len(rows)


# ---------------------------------------------------------------------------
# Main load orchestration
# ---------------------------------------------------------------------------

def load_baseline(driver: Driver, gen_dir: str) -> dict:
    """
    Load all System A–E CSVs into Neo4j in dependency order.
    Returns dict of {node_label: count}.
    """
    ref_dir = os.path.join(gen_dir, "..", "reference")
    counts = {}

    print("  Loading CPT codes...")
    counts["CPT_Code"] = load_cpt_codes(driver, ref_dir)

    print("  Loading ICD-10 codes...")
    counts["ICD10_Code"] = load_icd10_codes(driver, ref_dir)

    print("  Loading payers...")
    counts["Payer"] = load_payers(driver, gen_dir)

    print("  Loading payer policies...")
    counts["PayerPolicy"] = load_payer_policies(driver, gen_dir)

    print("  Loading providers...")
    counts["Provider"] = load_providers(driver, gen_dir)

    print("  Loading contracts...")
    counts["Contract"] = load_contracts(driver, gen_dir)

    print("  Loading patients...")
    counts["Patient"] = load_patients(driver, gen_dir)

    print("  Loading coverages...")
    counts["Coverage"] = load_coverages(driver, gen_dir)

    print("  Loading visits...")
    counts["Visit"] = load_visits(driver, gen_dir)

    print("  Loading claims...")
    counts["Claim"] = load_claims(driver, gen_dir)

    print("  Loading service lines...")
    load_service_lines(driver, gen_dir)

    print("  Loading authorizations...")
    counts["Authorization"] = load_authorizations(driver, gen_dir)

    print("  Loading referrals...")
    counts["ReferralOrder"] = load_referrals(driver, gen_dir)

    return counts


def clear_database(driver: Driver) -> None:
    """Drop all nodes and relationships. Dev/reset use only."""
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
