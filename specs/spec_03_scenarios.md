# Spec 03 — Anomaly Scenarios

**Read this file before implementing:** `flaw_injector.py`, `detection.py`, `detection_rules.yaml`

---

## Scenario overview

All six scenarios are common, recognized RCM problems. The graph's advantage is detecting them *systematically at scale* by traversing cross-system relationships no single source system can jointly validate.

**Demo narrative principle:** Lead every scenario with the business pain the ops team already feels. The graph is the mechanism — not the story.

| ID | Scenario | Severity | Risk type | Flaw_scenario tag |
|----|----------|----------|-----------|-------------------|
| S-01 | Prior Auth — Unverifiable Auth Chain | HIGH | Denial | `S-01` |
| S-02 | Rendering Provider Not Credentialed | HIGH | Denial (CO-4) | `S-02` |
| S-03 | Superseded Fee Schedule / Contract | MEDIUM | Underpayment | `S-03` |
| S-04 | Authorization Unit Exhaustion | HIGH | Denial / Overpayment | `S-04` |
| S-05 | Duplicate Patient Identity | HIGH | Entity integrity | `S-05` |
| S-06 | Invalid HMO Referral Chain | HIGH | Denial (CO-96) | `S-06` |

---

## S-01 — Prior Authorization: Unverifiable Auth Chain

**Business framing:** *"We have an auth number on the claim. The payer denied it anyway because they can't match the auth to this patient's procedure. We don't know if the auth was even for the right thing."*

**Why standard tools miss it:** `auth_number IS NOT NULL` passes. A `claim_auth_link` JOIN confirms a row exists. Neither check validates that the auth covers the right procedure, was granted by the correct payer, and hasn't expired — all of which require the full 4-hop path.

**Detection Cypher pattern:**
```cypher
MATCH (c:Claim {flaw_scenario: 'S-01'})
-[:BILLED_PROCEDURE]->(cpt:CPT_Code {requires_auth: true})
WHERE NOT EXISTS {
  MATCH (c)-[:HAS_AUTHORIZATION]->(a:Authorization)
        -[:AUTH_FOR_PROCEDURE]->(cpt)
  WHERE a.expiry_date >= c.claim_date
}
RETURN c
```

**Injection spec:**
- Select 8–12% of claims where `BILLED_PROCEDURE → CPT_Code[requires_auth=true]`
- Apply one of three sub-types per affected claim:
  - **(A) Missing link:** Delete `HAS_AUTHORIZATION` relationship; leave `auth_number` text on claim node intact
  - **(B) Wrong procedure:** Leave `HAS_AUTHORIZATION` edge but change `AUTH_FOR_PROCEDURE` target to a different CPT code
  - **(C) Expired auth:** Leave all relationships; set `Authorization.expiry_date` to 30 days before `Claim.claim_date`
- Tag affected Claims: `is_flawed: true`, `flaw_scenario: 'S-01'`
- Store deleted `HAS_AUTHORIZATION` relationship inventory in session state before deletion (for `clear_all_flaws()` restoration)

**Expected finding count:** 40–80 findings

---

## S-02 — Rendering Provider Not Credentialed with Billed Payer

**Business framing:** *"The claim went out under our group NPI, which is contracted. But the doctor who actually saw the patient isn't enrolled with this payer. We're getting CO-4 denials and don't know which claims are affected."*

**Why standard tools miss it:** Claim scrubbers validate the billing NPI against the payer network. Checking the rendering NPI *independently* against the same payer's contract table requires a separate join that most claim editors don't perform.

**Detection Cypher pattern:**
```cypher
MATCH (c:Claim {flaw_scenario: 'S-02'})
-[:BILLED_BY {billing_role: 'rendering'}]->(rp:Provider)
MATCH (c)-[:SUBMITTED_TO]->(py:Payer)
WHERE NOT EXISTS {
  MATCH (rp)-[:CONTRACTED_WITH]->(con:Contract)
       -[:CONTRACT_WITH_PAYER]->(py)
  WHERE con.effective_date <= c.claim_date
    AND (con.termination_date IS NULL OR con.termination_date >= c.claim_date)
}
RETURN c, rp, py
```

**Injection spec:**
- Add 5–8 `Provider` nodes as rendering-only physicians — no `provider_payer_contract` rows for 1–2 specific payers
- Assign them as rendering providers on 8–12% of claims submitted to those payers via `BILLED_BY {billing_role:'rendering'}` relationship
- Tag affected Claims: `is_flawed: true`, `flaw_scenario: 'S-02'`

**Expected finding count:** 40–80 findings

---

## S-03 — Fee Schedule / Contract Version Still Active After Renewal

**Business framing:** *"We renegotiated our BCBS contract in Q1. Our system still has the old fee schedule. We've been billing against 2022 rates for six months and only caught it in the quarterly reconciliation."*

**Why standard tools miss it:** The old contract row still exists in the source table with a potentially valid date range. A date range query returns both rows; without version chain awareness, the system uses the wrong one. `SUPERSEDED_BY` makes version chain traversal a single pattern match.

**Detection Cypher pattern:**
```cypher
// Contract version superseded
MATCH (c:Claim {flaw_scenario: 'S-03'})
-[:BILLED_BY]->(p:Provider)-[:CONTRACTED_WITH]->(con:Contract)
-[:SUPERSEDED_BY]->(newer:Contract)
RETURN c, con, newer

UNION

// Policy version superseded
MATCH (c:Claim {flaw_scenario: 'S-03'})
-[:COVERED_UNDER]->(cov:Coverage)-[:COVERED_BY]->(pp:PayerPolicy)
-[:POLICY_SUPERSEDED_BY]->(newer_pp:PayerPolicy)
RETURN c, pp, newer_pp
```

**Injection spec:**
- Contract version pairs (v1 → v2) are created in the **generator** for 2–3 payers; `SUPERSEDED_BY` edges built by **loader**
- Injector identifies post-renewal claims still referencing old Contract nodes
- Tags 10–15% of those claims: `is_flawed: true`, `flaw_scenario: 'S-03'`
- No relationship deletion needed — the `SUPERSEDED_BY` edge is the flaw signal

**Expected finding count:** 50–90 findings

---

## S-04 — Authorization Unit Exhaustion Across Multiple Claims

**Business framing:** *"The auth was approved for 12 PT visits. We billed 16. Each claim looked fine individually. The payer paid the first 12 and denied the last four — but we didn't catch it until the remittance came back."*

**Why standard tools miss it:** Claim editors validate each claim independently. Aggregating units across all claims linked to a single auth requires a GROUP BY that is rarely implemented in real-time scrubbers because it requires holding state across multiple claim submissions.

**Detection Cypher pattern:**
```cypher
MATCH (a:Authorization)<-[:HAS_AUTHORIZATION]-(c:Claim {flaw_scenario: 'S-04'})
      -[:BILLED_PROCEDURE]->(cpt:CPT_Code)
WITH a, sum(r.units) AS total_billed_units
     // r is the BILLED_PROCEDURE relationship; use relationship variable
WHERE total_billed_units > a.approved_units
RETURN a, total_billed_units, a.approved_units
```

**Full pattern with relationship variable:**
```cypher
MATCH (a:Authorization)<-[:HAS_AUTHORIZATION]-(c:Claim {flaw_scenario: 'S-04'})
MATCH (c)-[r:BILLED_PROCEDURE]->(cpt:CPT_Code)
WITH a, collect(c) AS claims, sum(r.units) AS total_billed_units
WHERE total_billed_units > a.approved_units
RETURN a, total_billed_units, a.approved_units, size(claims) AS claim_count
```

**Injection spec:**
- Select 15–20 `Authorization` nodes in PT/behavioral health/home health categories
- For each: set `approved_units` to a value that will be exceeded when all linked claim lines are summed
- Link 3–5 claims per auth; combined units 20–40% over the approved ceiling
- Tag affected Claims: `is_flawed: true`, `flaw_scenario: 'S-04'`

**Expected finding count:** 15–20 authorization violations (each finding = 1 Authorization exceeded, not 1 claim)

---

## S-05 — Duplicate Patient Identity Across Source Systems

**Business framing:** *"The patient registered at two different facilities. They have two MRNs. Half their claims are under one ID, half under the other. We're failing coordination of benefits checks and missing authorization limits because we can't see the full picture."*

**Why standard tools miss it:** Fuzzy name matching catches some variations but generates high false positives. The graph adds network-level signals: a patient pair sharing 3+ relationship targets (same provider, same payer, same zip, near-matching DOB) is far more likely to be a duplicate than demographic similarity alone suggests.

**Detection Cypher pattern:**
```cypher
MATCH (p1:Patient), (p2:Patient)
WHERE p1.patient_id < p2.patient_id       // prevent duplicate pairs
  AND p1.zip = p2.zip
  AND abs(duration.between(date(p1.dob), date(p2.dob)).days) <= 5
WITH p1, p2
MATCH (p1)-[:HAD_VISIT]->()-[:GENERATED_CLAIM]->(c1:Claim {flaw_scenario: 'S-05'})
      -[:SUBMITTED_TO]->(py:Payer)
MATCH (p2)-[:HAD_VISIT]->()-[:GENERATED_CLAIM]->(c2:Claim)
      -[:SUBMITTED_TO]->(py)
WITH p1, p2, count(DISTINCT py) AS shared_payers
WHERE shared_payers >= 2
RETURN p1, p2, shared_payers
```

**Injection spec:**
- Duplicate 30–50 `Patient` nodes with Faker-generated variations:
  - Name variation: nickname substitution (Robert → Bob), initial vs. full name
  - DOB transposition: single digit swap (e.g., 1962-03-14 → 1962-03-41 → corrected to valid nearby date)
  - Same zip code
- Split the original patient's Claims ~60/40 between the two identity nodes
- Tag affected Claims: `is_flawed: true`, `flaw_scenario: 'S-05'`

**Expected finding count:** 30–50 patient pairs

---

## S-06 — Invalid HMO Referral Chain

**Business framing:** *"We got a CO-96 denial — referral required. We have a referral ID on the claim. But it turns out the referring doctor isn't a PCP on this patient's HMO network, and the referral was dated two days after the visit."*

**Why standard tools miss it:** A column check confirms `referring_npi IS NOT NULL`. Validating all four conditions simultaneously requires joining 4 tables each with different cardinality — a conditional logic chain most claim editors don't implement in combination.

**Four simultaneous conditions for a valid HMO referral:**
1. Coverage is an HMO plan type
2. Rendering provider is a specialist (not PCP)
3. `ReferralOrder.order_date` is ≤ Visit date
4. Referring provider in ReferralOrder is a PCP contracted with the same HMO

**Detection Cypher pattern:**
```cypher
MATCH (c:Claim {flaw_scenario: 'S-06'})
-[:COVERED_UNDER]->(cov:Coverage)-[:COVERED_BY]->(pp:PayerPolicy {plan_type: 'HMO'})
MATCH (c)-[:BILLED_BY {billing_role:'rendering'}]->(rp:Provider {provider_type:'specialist'})
MATCH (c)-[:SUBMITTED_TO]->(py:Payer)
MATCH (v:Visit)-[:GENERATED_CLAIM]->(c)
WHERE (
  // Sub-type A: no referral at all
  NOT EXISTS { MATCH (c)-[:HAS_REFERRAL]->() }
  OR
  // Sub-type B: referral dated after visit
  EXISTS {
    MATCH (c)-[:HAS_REFERRAL]->(ro:ReferralOrder)
    WHERE ro.order_date > v.visit_date
  }
  OR
  // Sub-type C: referring provider is not a PCP contracted with this HMO
  EXISTS {
    MATCH (c)-[:HAS_REFERRAL]->(ro:ReferralOrder)-[:REFERRED_BY]->(ref_prov:Provider)
    WHERE ref_prov.specialty <> 'PCP'
    OR NOT EXISTS {
      MATCH (ref_prov)-[:CONTRACTED_WITH]->(con:Contract)-[:CONTRACT_WITH_PAYER]->(py)
    }
  }
)
RETURN c, rp, pp, py
```

**Injection spec:**
- Select 8–12% of HMO specialist claims
- Apply one sub-type per affected claim:
  - **(A)** Remove `HAS_REFERRAL` relationship; leave `referring_npi` text field intact on source data
  - **(B)** Set `ReferralOrder.order_date` to 2–5 days after `Visit.visit_date`
  - **(C)** Assign a referring provider who is a specialist (not PCP) or not contracted with that HMO
- Tag affected Claims: `is_flawed: true`, `flaw_scenario: 'S-06'`
- Store deleted `HAS_REFERRAL` relationship inventory for `clear_all_flaws()` restoration

**Expected finding count:** 40–80 findings

---

## Scenario isolation guarantee

Every injection function **must**:
1. Tag Claims with `flaw_scenario: 'S-XX'` before any relationship modification
2. All detection queries **must** scope via `{flaw_scenario: 'S-XX'}` on the Claim node
3. `clear_all_flaws()` removes ALL flaw tags and ALL Finding nodes in a single transaction

This ensures S-01 detection never touches S-02 claims and vice versa. Multiple scenarios can coexist without interference.

---

## `clear_all_flaws()` Cypher

```cypher
// Step 1: Delete all Finding nodes and their relationships
MATCH (f:Finding)
DETACH DELETE f;

// Step 2: Remove all flaw tags from Claim nodes
MATCH (c:Claim)
WHERE c.is_flawed = true
REMOVE c.is_flawed, c.flaw_scenario;

// Step 3: Restore deleted relationships from session state inventory
// (executed per-relationship by the Python layer — not a single Cypher statement)
```

> **Important:** `clear_all_flaws()` in Python must first restore deleted relationships from session state inventory, THEN run the Cypher above. See `flaw_injector.py` spec.

---

## `detection_rules.yaml` structure

```yaml
rules:
  - rule_id: "DR-S01"
    name: "Unverifiable Prior Authorization Chain"
    category: "prior_authorization"
    severity: "HIGH"
    risk_type: "denial"
    description: "Claim billed for an auth-required procedure where the authorization is missing, covers a different procedure, or has expired."
    applies_to: "Claim"
    version: "1.0"
    active: true
    cypher: |
      MATCH (c:Claim {flaw_scenario: 'S-01'})-[:BILLED_PROCEDURE]->(cpt:CPT_Code {requires_auth: true})
      WHERE NOT EXISTS {
        MATCH (c)-[:HAS_AUTHORIZATION]->(a:Authorization)-[:AUTH_FOR_PROCEDURE]->(cpt)
        WHERE a.expiry_date >= c.claim_date
      }
      WITH c, cpt
      CREATE (f:Finding {
        finding_id: 'F-' + c.claim_id + '-DR-S01',
        detected_at: datetime(),
        severity: 'HIGH',
        status: 'open',
        description: 'Auth chain invalid: claim ' + c.claim_id + ' has no valid authorization for ' + cpt.code,
        estimated_risk_amount: c.billed_amount
      })
      CREATE (c)-[:HAS_FINDING]->(f)
      WITH f
      MATCH (r:DetectionRule {rule_id: 'DR-S01'})
      CREATE (f)-[:TRIGGERED_BY]->(r)
      RETURN count(f) AS findings_created

  # ... rules DR-S02 through DR-S06 follow same structure
```
