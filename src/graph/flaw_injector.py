"""
flaw_injector.py — Six flaw injection functions + clear_all_flaws().

Each inject_s0X() function:
  1. Stores a deletion inventory (relationships to be removed) BEFORE deleting
  2. Tags affected Claims with is_flawed=True, flaw_scenario='S-0X'
  3. Modifies graph structure (removes/adds relationships or modifies properties)
  4. Returns {claims_affected, changes_summary, inventory}

The inventory dict is stored in Streamlit session_state by the UI layer.
clear_all_flaws() accepts inventory_by_scenario and reverses all changes.

Scenario isolation: all injection functions scope to their own flaw_scenario tag.
Detection queries scope to that same tag — no cross-scenario interference.
"""

import random
from datetime import date, timedelta
from neo4j import Driver

random.seed(42)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(driver: Driver, cypher: str, **params):
    with driver.session() as session:
        return session.run(cypher, **params).data()


def _run_single(driver: Driver, cypher: str, **params):
    with driver.session() as session:
        result = session.run(cypher, **params)
        rec = result.single()
        return rec[0] if rec else None


# ---------------------------------------------------------------------------
# S-01: Prior Authorization — Unverifiable Auth Chain
# ---------------------------------------------------------------------------

def inject_s01(driver: Driver) -> dict:
    """
    For 8-12% of claims with auth-required procedures:
    - Type A: remove HAS_AUTHORIZATION relationship (auth_number text remains)
    - Type B: change AUTH_FOR_PROCEDURE to point to a different CPT code
    - Type C: set Authorization.expiry_date before Claim.claim_date
    """
    # Find candidates: claims with auth-required CPTs that currently have valid auth
    candidates = _run(driver, """
        MATCH (c:Claim)-[:BILLED_PROCEDURE]->(cpt:CPT_Code {requires_auth: true})
        MATCH (c)-[:HAS_AUTHORIZATION]->(a:Authorization)-[:AUTH_FOR_PROCEDURE]->(cpt)
        WHERE coalesce(c.is_flawed, false) = false
        WITH c, a, cpt
        RETURN c.claim_id AS claim_id, a.auth_id AS auth_id, cpt.code AS cpt_code
        LIMIT 120
    """)

    if not candidates:
        return {"claims_affected": 0, "changes_summary": "No candidates found", "inventory": []}

    # Select ~10% of candidates
    selected = random.sample(candidates, max(1, int(len(candidates) * 0.10)))
    inventory = []
    type_a_count = type_b_count = type_c_count = 0

    for i, row in enumerate(selected):
        sub_type = ["A", "B", "C"][i % 3]

        # Tag the claim first
        _run(driver, """
            MATCH (c:Claim {claim_id: $claim_id})
            SET c.is_flawed = true, c.flaw_scenario = 'S-01'
        """, claim_id=row["claim_id"])

        if sub_type == "A":
            # Store and delete HAS_AUTHORIZATION
            inventory.append({
                "type": "HAS_AUTHORIZATION",
                "claim_id": row["claim_id"],
                "auth_id": row["auth_id"],
            })
            _run(driver, """
                MATCH (c:Claim {claim_id: $claim_id})-[r:HAS_AUTHORIZATION]->(a:Authorization {auth_id: $auth_id})
                DELETE r
            """, claim_id=row["claim_id"], auth_id=row["auth_id"])
            type_a_count += 1

        elif sub_type == "B":
            # Find a different CPT code and change AUTH_FOR_PROCEDURE
            other_cpt = _run(driver, """
                MATCH (cpt:CPT_Code {requires_auth: true})
                WHERE cpt.code <> $cpt_code
                RETURN cpt.code AS code LIMIT 1
            """, cpt_code=row["cpt_code"])

            if other_cpt:
                inventory.append({
                    "type": "AUTH_FOR_PROCEDURE",
                    "auth_id": row["auth_id"],
                    "original_cpt": row["cpt_code"],
                    "changed_to": other_cpt[0]["code"],
                })
                _run(driver, """
                    MATCH (a:Authorization {auth_id: $auth_id})-[r:AUTH_FOR_PROCEDURE]->(cpt:CPT_Code {code: $cpt_code})
                    DELETE r
                    WITH a
                    MATCH (new_cpt:CPT_Code {code: $new_code})
                    MERGE (a)-[:AUTH_FOR_PROCEDURE]->(new_cpt)
                """, auth_id=row["auth_id"], cpt_code=row["cpt_code"], new_code=other_cpt[0]["code"])
                type_b_count += 1

        elif sub_type == "C":
            # Set auth expiry 30 days before claim date
            claim_date_str = _run_single(driver, """
                MATCH (c:Claim {claim_id: $claim_id}) RETURN c.claim_date
            """, claim_id=row["claim_id"])
            if claim_date_str:
                original_expiry = _run_single(driver, """
                    MATCH (a:Authorization {auth_id: $auth_id}) RETURN a.expiry_date
                """, auth_id=row["auth_id"])
                claim_date = date.fromisoformat(str(claim_date_str))
                new_expiry = str(claim_date - timedelta(days=30))
                inventory.append({
                    "type": "AUTH_EXPIRY",
                    "auth_id": row["auth_id"],
                    "original_expiry": str(original_expiry),
                })
                _run(driver, """
                    MATCH (a:Authorization {auth_id: $auth_id})
                    SET a.expiry_date = $new_expiry
                """, auth_id=row["auth_id"], new_expiry=new_expiry)
                type_c_count += 1

    total = type_a_count + type_b_count + type_c_count
    summary = (f"Type A (missing link): {type_a_count} | "
               f"Type B (wrong procedure): {type_b_count} | "
               f"Type C (expired auth): {type_c_count}")

    return {
        "claims_affected": total,
        "changes_summary": summary,
        "inventory": inventory,
    }


# ---------------------------------------------------------------------------
# S-02: Rendering Provider Not Credentialed with Billed Payer
# ---------------------------------------------------------------------------

def inject_s02(driver: Driver) -> dict:
    """
    Find uncredentialed providers (no contract with S02 target payers).
    Swap the rendering provider on 8-12% of claims submitted to those payers.
    """
    from generate.domains import S02_TARGET_PAYER_IDS

    # Find uncredentialed providers (those with no contract for the target payers)
    uncred_providers = _run(driver, """
        MATCH (p:Provider)
        WHERE p.specialty IN ['Orthopedics', 'Cardiology', 'Gastroenterology', 'Neurology']
        OPTIONAL MATCH (p)-[:CONTRACTED_WITH]->(:Contract)-[:CONTRACT_WITH_PAYER]->(py:Payer)
        WHERE py.payer_id IN $target_payers
        WITH p, count(py) AS contract_count
        WHERE contract_count = 0
        RETURN p.npi AS npi LIMIT 8
    """, target_payers=S02_TARGET_PAYER_IDS)

    if not uncred_providers:
        return {"claims_affected": 0, "changes_summary": "No uncredentialed providers found", "inventory": []}

    uncred_npis = [r["npi"] for r in uncred_providers]

    # Find claims to target: submitted to target payers, not yet flawed
    target_claims = _run(driver, """
        MATCH (c:Claim)-[:SUBMITTED_TO]->(py:Payer)
        WHERE py.payer_id IN $target_payers
          AND coalesce(c.is_flawed, false) = false
        MATCH (c)-[:BILLED_BY {billing_role: 'rendering'}]->(rp:Provider)
        WHERE NOT (rp.npi IN $uncred_npis)
        RETURN c.claim_id AS claim_id, rp.npi AS original_rendering_npi
        LIMIT 100
    """, target_payers=S02_TARGET_PAYER_IDS, uncred_npis=uncred_npis)

    if not target_claims:
        return {"claims_affected": 0, "changes_summary": "No target claims found", "inventory": []}

    selected = random.sample(target_claims, max(1, int(len(target_claims) * 0.10)))
    inventory = []

    for row in selected:
        # Pick a random uncredentialed provider
        new_npi = random.choice(uncred_npis)

        inventory.append({
            "type": "BILLED_BY_RENDERING",
            "claim_id": row["claim_id"],
            "original_npi": row["original_rendering_npi"],
            "injected_npi": new_npi,
        })

        # Tag claim and swap rendering provider
        _run(driver, """
            MATCH (c:Claim {claim_id: $claim_id})
            SET c.is_flawed = true, c.flaw_scenario = 'S-02'
        """, claim_id=row["claim_id"])

        _run(driver, """
            MATCH (c:Claim {claim_id: $claim_id})-[r:BILLED_BY {billing_role: 'rendering'}]->()
            DELETE r
            WITH c
            MATCH (new_p:Provider {npi: $new_npi})
            CREATE (c)-[:BILLED_BY {billing_role: 'rendering'}]->(new_p)
        """, claim_id=row["claim_id"], new_npi=new_npi)

    return {
        "claims_affected": len(selected),
        "changes_summary": f"{len(selected)} claims assigned uncredentialed rendering providers",
        "inventory": inventory,
    }


# ---------------------------------------------------------------------------
# S-03: Fee Schedule / Contract Version Still Active After Renewal
# ---------------------------------------------------------------------------

def inject_s03(driver: Driver) -> dict:
    """
    For providers contracted with S03 renewal payers:
    swap their CONTRACTED_WITH edge from v2 (current) back to v1 (superseded).
    Tag affected claims.
    """
    from generate.domains import S03_RENEWAL_PAYER_IDS

    # Find providers with v2 contracts for renewal payers
    v2_contracts = _run(driver, """
        MATCH (p:Provider)-[:CONTRACTED_WITH]->(c2:Contract)-[:CONTRACT_WITH_PAYER]->(py:Payer)
        WHERE py.payer_id IN $renewal_payers
        MATCH (c1:Contract)-[:SUPERSEDED_BY]->(c2)
        WHERE c1.version_num = 1
        RETURN p.npi AS npi, c1.contract_id AS v1_id, c2.contract_id AS v2_id
        LIMIT 30
    """, renewal_payers=S03_RENEWAL_PAYER_IDS)

    if not v2_contracts:
        return {"claims_affected": 0, "changes_summary": "No versioned contracts found", "inventory": []}

    # Select a subset of providers to "regress" to v1
    selected_contracts = random.sample(v2_contracts, max(1, int(len(v2_contracts) * 0.40)))
    inventory = []
    claims_affected = 0

    for row in selected_contracts:
        inventory.append({
            "type": "CONTRACTED_WITH",
            "npi": row["npi"],
            "v1_contract_id": row["v1_id"],
            "v2_contract_id": row["v2_id"],
        })

        # Swap: delete CONTRACTED_WITH → v2, add CONTRACTED_WITH → v1
        _run(driver, """
            MATCH (p:Provider {npi: $npi})-[r:CONTRACTED_WITH]->(c2:Contract {contract_id: $v2_id})
            DELETE r
            WITH p
            MATCH (c1:Contract {contract_id: $v1_id})
            CREATE (p)-[:CONTRACTED_WITH]->(c1)
        """, npi=row["npi"], v2_id=row["v2_id"], v1_id=row["v1_id"])

        # Tag all claims by this provider with payers in S03 list
        result = _run(driver, """
            MATCH (c:Claim)-[:BILLED_BY]->(p:Provider {npi: $npi})
            MATCH (c)-[:SUBMITTED_TO]->(py:Payer)
            WHERE py.payer_id IN $renewal_payers
              AND coalesce(c.is_flawed, false) = false
            SET c.is_flawed = true, c.flaw_scenario = 'S-03'
            RETURN count(c) AS n
        """, npi=row["npi"], renewal_payers=S03_RENEWAL_PAYER_IDS)

        if result:
            claims_affected += result[0].get("n", 0)

    return {
        "claims_affected": claims_affected,
        "changes_summary": f"{len(selected_contracts)} providers regressed to superseded contract version",
        "inventory": inventory,
    }


# ---------------------------------------------------------------------------
# S-04: Authorization Unit Exhaustion
# ---------------------------------------------------------------------------

def inject_s04(driver: Driver) -> dict:
    """
    Find PT/BH/HH claims with authorizations where billed units >= 4.
    Lower each auth's approved_units to below the claim's billed units.
    Tag affected claims.
    (Data has 1:1 claim-to-auth; scenario demonstrates unit exhaustion
    on a per-claim basis — approved_units set below what was billed.)
    """
    candidates = _run(driver, """
        MATCH (c:Claim)-[:HAS_AUTHORIZATION]->(a:Authorization)
        MATCH (c)-[r:BILLED_PROCEDURE]->(cpt:CPT_Code)
        WHERE cpt.category IN ['PT', 'Behavioral Health', 'Home Health']
          AND coalesce(c.is_flawed, false) = false
        WITH c, a, sum(r.units) AS total_units
        WHERE total_units >= 4 AND a.approved_units >= total_units
        RETURN c.claim_id AS claim_id, a.auth_id AS auth_id,
               total_units, a.approved_units AS current_approved
        LIMIT 60
    """)

    if not candidates:
        return {"claims_affected": 0, "changes_summary": "No eligible PT/BH/HH auth claims found", "inventory": []}

    selected = random.sample(candidates, min(25, len(candidates)))
    inventory = []
    claims_affected = 0

    for row in selected:
        total = row["total_units"]
        # Set approved_units to 60-75% of billed — claim now exceeds auth
        new_approved = max(1, int(total * random.uniform(0.60, 0.75)))

        inventory.append({
            "type": "AUTH_UNITS_MODIFIED",
            "auth_id": row["auth_id"],
            "original_approved_units": row["current_approved"],
        })

        _run(driver, """
            MATCH (a:Authorization {auth_id: $auth_id})
            SET a.approved_units = $new_approved
        """, auth_id=row["auth_id"], new_approved=new_approved)

        _run(driver, """
            MATCH (c:Claim {claim_id: $claim_id})
            SET c.is_flawed = true, c.flaw_scenario = 'S-04'
        """, claim_id=row["claim_id"])
        claims_affected += 1

    return {
        "claims_affected": claims_affected,
        "changes_summary": f"{len(selected)} authorizations reduced below billed units",
        "inventory": inventory,
    }


# ---------------------------------------------------------------------------
# S-05: Duplicate Patient Identity
# ---------------------------------------------------------------------------

def inject_s05(driver: Driver) -> dict:
    """
    Duplicate 30-40 patient nodes with name/DOB variations.
    Move ~40% of original patient's claims to the duplicate node.
    """
    from faker import Faker
    fake = Faker()
    fake.seed_instance(99)

    # Get patients with multiple claims
    candidates = _run(driver, """
        MATCH (p:Patient)-[:HAD_VISIT]->()-[:GENERATED_CLAIM]->(c:Claim)
        WHERE coalesce(p.flaw_scenario, '') <> 'S-05'
        WITH p, count(c) AS claim_count
        WHERE claim_count >= 4
        RETURN p.patient_id AS patient_id, p.dob AS dob, p.zip AS zip,
               p.last_name AS last_name, p.first_name AS first_name
        ORDER BY rand()
        LIMIT 35
    """)

    if not candidates:
        return {"claims_affected": 0, "changes_summary": "No candidates found", "inventory": []}

    inventory = []
    claims_affected = 0

    name_variants = {
        "Robert": "Bob", "William": "Bill", "James": "Jim",
        "Michael": "Mike", "Thomas": "Tom", "Richard": "Rich",
        "Charles": "Chuck", "Joseph": "Joe", "Patricia": "Pat",
        "Katherine": "Kate", "Elizabeth": "Beth", "Margaret": "Peg",
    }

    for pt in candidates:
        dup_id = f"MRN_DUP_{pt['patient_id']}"

        # Create name variation
        first = pt["first_name"]
        dup_first = name_variants.get(first, first[:3] + ".")

        # Create DOB transposition (swap a digit in day)
        dob = pt["dob"]
        try:
            d = date.fromisoformat(dob)
            offset = random.choice([-2, -1, 1, 2, 3])
            new_d = d + timedelta(days=offset)
            dup_dob = str(new_d)
        except Exception:
            dup_dob = dob

        inventory.append({
            "type": "DUPLICATE_PATIENT",
            "duplicate_patient_id": dup_id,
            "original_patient_id": pt["patient_id"],
        })

        # Create duplicate Patient node
        _run(driver, """
            MERGE (dup:Patient {patient_id: $dup_id})
            SET dup.mrn          = $dup_id,
                dup.last_name    = $last_name,
                dup.first_name   = $first_name,
                dup.dob          = $dob,
                dup.zip          = $zip,
                dup.is_flawed    = true,
                dup.flaw_scenario = 'S-05',
                dup.duplicate_of = $orig_id
        """,
        dup_id=dup_id,
        last_name=pt["last_name"],
        first_name=dup_first,
        dob=dup_dob,
        zip=pt["zip"],
        orig_id=pt["patient_id"])

        # Get ~40% of original patient's visits/claims to move to duplicate
        visits_to_move = _run(driver, """
            MATCH (p:Patient {patient_id: $pid})-[rv:HAD_VISIT]->(v:Visit)
            WITH v, rv ORDER BY rand()
            LIMIT 2
            RETURN v.visit_id AS visit_id
        """, pid=pt["patient_id"])

        for v_row in visits_to_move:
            # Re-point HAD_VISIT from original to duplicate
            _run(driver, """
                MATCH (orig:Patient {patient_id: $orig_id})-[r:HAD_VISIT]->(v:Visit {visit_id: $vid})
                DELETE r
                WITH v
                MATCH (dup:Patient {patient_id: $dup_id})
                MERGE (dup)-[:HAD_VISIT]->(v)
            """, orig_id=pt["patient_id"], dup_id=dup_id, vid=v_row["visit_id"])

            # Tag claims generated by moved visits
            _run(driver, """
                MATCH (v:Visit {visit_id: $vid})-[:GENERATED_CLAIM]->(c:Claim)
                SET c.is_flawed = true, c.flaw_scenario = 'S-05',
                    c.mrn = $dup_id
            """, vid=v_row["visit_id"], dup_id=dup_id)
            claims_affected += 1

    return {
        "claims_affected": claims_affected,
        "changes_summary": f"{len(candidates)} patient records duplicated with name/DOB variations",
        "inventory": inventory,
    }


# ---------------------------------------------------------------------------
# S-06: Invalid HMO Referral Chain
# ---------------------------------------------------------------------------

def inject_s06(driver: Driver) -> dict:
    """
    For 8-12% of HMO specialist claims:
    - Type A: remove HAS_REFERRAL (referring_npi text remains)
    - Type B: set referral order_date AFTER visit date
    - Type C: assign a specialist (not PCP) as the referring provider
    """
    # Find HMO specialist claims with valid referrals that are not yet flawed
    candidates = _run(driver, """
        MATCH (c:Claim)-[:COVERED_UNDER]->(cov:Coverage)-[:COVERED_BY]->(pp:PayerPolicy {plan_type: 'HMO'})
        MATCH (c)-[:HAS_REFERRAL]->(ro:ReferralOrder)-[:REFERRED_BY]->(pcp:Provider {specialty: 'PCP'})
        MATCH (c)-[:BILLED_BY {billing_role: 'rendering'}]->(rp:Provider)
        WHERE rp.specialty <> 'PCP'
          AND coalesce(c.is_flawed, false) = false
        MATCH (v:Visit)-[:GENERATED_CLAIM]->(c)
        RETURN c.claim_id AS claim_id, ro.referral_id AS referral_id,
               pcp.npi AS pcp_npi, v.visit_date AS visit_date,
               ro.order_date AS referral_date
        LIMIT 100
    """)

    if not candidates:
        return {"claims_affected": 0, "changes_summary": "No HMO specialist claims with referrals found", "inventory": []}

    selected = random.sample(candidates, max(1, int(len(candidates) * 0.12)))
    inventory = []
    type_a = type_b = type_c = 0

    # Find a specialist (non-PCP) to use for type C
    specialist_prov = _run(driver, """
        MATCH (p:Provider)
        WHERE NOT (p.specialty IN ['PCP', 'Home Health'])
          AND p.provider_type = 'physician'
        RETURN p.npi AS npi LIMIT 1
    """)
    specialist_npi = specialist_prov[0]["npi"] if specialist_prov else None

    for i, row in enumerate(selected):
        sub_type = ["A", "B", "C"][i % 3]
        if sub_type == "C" and specialist_npi is None:
            sub_type = "A"

        _run(driver, """
            MATCH (c:Claim {claim_id: $claim_id})
            SET c.is_flawed = true, c.flaw_scenario = 'S-06'
        """, claim_id=row["claim_id"])

        if sub_type == "A":
            inventory.append({
                "type": "HAS_REFERRAL",
                "claim_id": row["claim_id"],
                "referral_id": row["referral_id"],
            })
            _run(driver, """
                MATCH (c:Claim {claim_id: $claim_id})-[r:HAS_REFERRAL]->(:ReferralOrder {referral_id: $rid})
                DELETE r
            """, claim_id=row["claim_id"], rid=row["referral_id"])
            type_a += 1

        elif sub_type == "B":
            try:
                visit_date = date.fromisoformat(str(row["visit_date"]))
                late_date = str(visit_date + timedelta(days=random.randint(2, 5)))
                inventory.append({
                    "type": "REFERRAL_DATE_CHANGED",
                    "referral_id": row["referral_id"],
                    "original_date": str(row["referral_date"]),
                })
                _run(driver, """
                    MATCH (ro:ReferralOrder {referral_id: $rid})
                    SET ro.order_date = $late_date
                """, rid=row["referral_id"], late_date=late_date)
                type_b += 1
            except Exception:
                pass

        elif sub_type == "C":
            inventory.append({
                "type": "REFERRED_BY_CHANGED",
                "referral_id": row["referral_id"],
                "original_pcp_npi": row["pcp_npi"],
                "injected_specialist_npi": specialist_npi,
            })
            _run(driver, """
                MATCH (ro:ReferralOrder {referral_id: $rid})-[r:REFERRED_BY]->()
                DELETE r
                WITH ro
                MATCH (spec:Provider {npi: $spec_npi})
                CREATE (ro)-[:REFERRED_BY]->(spec)
            """, rid=row["referral_id"], spec_npi=specialist_npi)
            type_c += 1

    total = type_a + type_b + type_c
    summary = (f"Type A (no referral): {type_a} | "
               f"Type B (late referral): {type_b} | "
               f"Type C (non-PCP referrer): {type_c}")

    return {
        "claims_affected": total,
        "changes_summary": summary,
        "inventory": inventory,
    }


# ---------------------------------------------------------------------------
# Unified inject dispatcher
# ---------------------------------------------------------------------------

INJECT_MAP = {
    "S-01": inject_s01,
    "S-02": inject_s02,
    "S-03": inject_s03,
    "S-04": inject_s04,
    "S-05": inject_s05,
    "S-06": inject_s06,
}


def inject(scenario_id: str, driver: Driver) -> dict:
    """Dispatch to the correct inject function by scenario ID.
    Seeds random per scenario so results are deterministic across runs."""
    fn = INJECT_MAP.get(scenario_id)
    if fn is None:
        raise ValueError(f"Unknown scenario: {scenario_id}")
    seed = {"S-01": 101, "S-02": 102, "S-03": 103,
            "S-04": 104, "S-05": 105, "S-06": 106}.get(scenario_id, 42)
    random.seed(seed)
    return fn(driver)


# ---------------------------------------------------------------------------
# clear_all_flaws — full baseline restoration
# ---------------------------------------------------------------------------

def clear_all_flaws(driver: Driver, inventory_by_scenario: dict) -> None:
    """
    Restore all deleted/modified relationships and remove flaw tags.
    inventory_by_scenario: {scenario_id: [inventory_items]}
    """
    # Step 1: Restore deleted/modified items from inventory
    for scenario_id, items in inventory_by_scenario.items():
        for item in items:
            t = item.get("type")

            if t == "HAS_AUTHORIZATION":
                _run(driver, """
                    MATCH (c:Claim {claim_id: $claim_id})
                    MATCH (a:Authorization {auth_id: $auth_id})
                    MERGE (c)-[:HAS_AUTHORIZATION]->(a)
                """, claim_id=item["claim_id"], auth_id=item["auth_id"])

            elif t == "AUTH_FOR_PROCEDURE":
                # Restore original CPT, remove injected CPT
                _run(driver, """
                    MATCH (a:Authorization {auth_id: $auth_id})-[r:AUTH_FOR_PROCEDURE]->(cpt:CPT_Code {code: $changed_to})
                    DELETE r
                    WITH a
                    MATCH (orig_cpt:CPT_Code {code: $original_cpt})
                    MERGE (a)-[:AUTH_FOR_PROCEDURE]->(orig_cpt)
                """, auth_id=item["auth_id"],
                    changed_to=item["changed_to"],
                    original_cpt=item["original_cpt"])

            elif t == "AUTH_EXPIRY":
                _run(driver, """
                    MATCH (a:Authorization {auth_id: $auth_id})
                    SET a.expiry_date = $original_expiry
                """, auth_id=item["auth_id"], original_expiry=item["original_expiry"])

            elif t == "BILLED_BY_RENDERING":
                _run(driver, """
                    MATCH (c:Claim {claim_id: $claim_id})-[r:BILLED_BY {billing_role: 'rendering'}]->()
                    DELETE r
                    WITH c
                    MATCH (orig:Provider {npi: $orig_npi})
                    CREATE (c)-[:BILLED_BY {billing_role: 'rendering'}]->(orig)
                """, claim_id=item["claim_id"], orig_npi=item["original_npi"])

            elif t == "CONTRACTED_WITH":
                _run(driver, """
                    MATCH (p:Provider {npi: $npi})-[r:CONTRACTED_WITH]->(c1:Contract {contract_id: $v1_id})
                    DELETE r
                    WITH p
                    MATCH (c2:Contract {contract_id: $v2_id})
                    CREATE (p)-[:CONTRACTED_WITH]->(c2)
                """, npi=item["npi"], v1_id=item["v1_contract_id"], v2_id=item["v2_contract_id"])

            elif t == "AUTH_UNITS_MODIFIED":
                _run(driver, """
                    MATCH (a:Authorization {auth_id: $auth_id})
                    SET a.approved_units = $original_units
                """, auth_id=item["auth_id"], original_units=item["original_approved_units"])

            elif t == "DUPLICATE_PATIENT":
                dup_id = item["duplicate_patient_id"]
                orig_id = item["original_patient_id"]
                # Move HAD_VISIT back to original patient
                _run(driver, """
                    MATCH (dup:Patient {patient_id: $dup_id})-[r:HAD_VISIT]->(v:Visit)
                    DELETE r
                    WITH v
                    MATCH (orig:Patient {patient_id: $orig_id})
                    MERGE (orig)-[:HAD_VISIT]->(v)
                """, dup_id=dup_id, orig_id=orig_id)
                # Delete duplicate patient node
                _run(driver, """
                    MATCH (dup:Patient {patient_id: $dup_id})
                    DETACH DELETE dup
                """, dup_id=dup_id)

            elif t == "HAS_REFERRAL":
                _run(driver, """
                    MATCH (c:Claim {claim_id: $claim_id})
                    MATCH (ro:ReferralOrder {referral_id: $referral_id})
                    MERGE (c)-[:HAS_REFERRAL]->(ro)
                """, claim_id=item["claim_id"], referral_id=item["referral_id"])

            elif t == "REFERRAL_DATE_CHANGED":
                _run(driver, """
                    MATCH (ro:ReferralOrder {referral_id: $rid})
                    SET ro.order_date = $original_date
                """, rid=item["referral_id"], original_date=item["original_date"])

            elif t == "REFERRED_BY_CHANGED":
                _run(driver, """
                    MATCH (ro:ReferralOrder {referral_id: $rid})-[r:REFERRED_BY]->()
                    DELETE r
                    WITH ro
                    MATCH (pcp:Provider {npi: $pcp_npi})
                    CREATE (ro)-[:REFERRED_BY]->(pcp)
                """, rid=item["referral_id"], pcp_npi=item["original_pcp_npi"])

    # Step 2: Delete all Finding nodes
    with driver.session() as session:
        session.run("MATCH (f:Finding) DETACH DELETE f")

    # Step 3: Remove flaw tags from all Claim nodes
    with driver.session() as session:
        session.run("""
            MATCH (c:Claim)
            WHERE c.is_flawed = true
            REMOVE c.is_flawed, c.flaw_scenario
        """)

    # Step 4: Remove flaw tags from Patient nodes (S-05)
    with driver.session() as session:
        session.run("""
            MATCH (p:Patient)
            WHERE p.is_flawed = true
            REMOVE p.is_flawed, p.flaw_scenario, p.duplicate_of
        """)
