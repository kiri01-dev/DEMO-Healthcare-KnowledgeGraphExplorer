"""
findings.py — Finding CRUD operations.

All reads and writes go directly to Neo4j — no session state caching.
The graph is the system of record for the monitoring workflow.
"""

from neo4j import Driver


def list_findings(driver: Driver, status: str = None, scenario: str = None) -> list:
    """
    Return findings as a list of dicts.
    Optionally filter by status ('open', 'acknowledged', 'resolved')
    and/or scenario (e.g., 'S-01').
    """
    where_clauses = []
    params = {}

    if status:
        where_clauses.append("f.status = $status")
        params["status"] = status

    where_str = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    scenario_filter = ""
    if scenario:
        scenario_filter = "AND c.flaw_scenario = $scenario"
        params["scenario"] = scenario

    cypher = f"""
        MATCH (c:Claim)-[:HAS_FINDING]->(f:Finding)-[:TRIGGERED_BY]->(r:DetectionRule)
        MATCH (p:Patient)-[:HAD_VISIT]->()-[:GENERATED_CLAIM]->(c)
        {where_str}
        {scenario_filter}
        RETURN
            f.finding_id              AS finding_id,
            c.claim_id                AS claim_id,
            p.patient_id              AS patient_id,
            r.rule_id                 AS rule_id,
            r.name                    AS rule_name,
            r.category                AS category,
            f.severity                AS severity,
            f.status                  AS status,
            f.detected_at             AS detected_at,
            f.description             AS description,
            f.estimated_risk_amount   AS estimated_risk_amount,
            f.resolved_at             AS resolved_at,
            c.flaw_scenario           AS scenario
        ORDER BY f.detected_at DESC
    """

    with driver.session() as session:
        return session.run(cypher, **params).data()


def get_finding(driver: Driver, finding_id: str) -> dict:
    """Return a single finding by ID."""
    with driver.session() as session:
        result = session.run("""
            MATCH (c:Claim)-[:HAS_FINDING]->(f:Finding {finding_id: $id})-[:TRIGGERED_BY]->(r:DetectionRule)
            MATCH (p:Patient)-[:HAD_VISIT]->()-[:GENERATED_CLAIM]->(c)
            RETURN
                f.finding_id            AS finding_id,
                c.claim_id              AS claim_id,
                p.patient_id            AS patient_id,
                r.rule_id               AS rule_id,
                r.name                  AS rule_name,
                f.severity              AS severity,
                f.status                AS status,
                f.detected_at           AS detected_at,
                f.description           AS description,
                f.estimated_risk_amount AS estimated_risk_amount,
                f.resolved_at           AS resolved_at,
                f.resolution_note       AS resolution_note,
                c.flaw_scenario         AS scenario
        """, id=finding_id)
        record = result.single()
        return dict(record) if record else {}


def acknowledge_finding(finding_id: str, driver: Driver) -> None:
    """Set Finding.status = 'acknowledged'."""
    with driver.session() as session:
        session.run("""
            MATCH (f:Finding {finding_id: $id})
            SET f.status = 'acknowledged'
        """, id=finding_id)


def resolve_finding(finding_id: str, driver: Driver, note: str = "") -> None:
    """Set Finding.status = 'resolved', write resolved_at timestamp and optional resolution note."""
    with driver.session() as session:
        session.run("""
            MATCH (f:Finding {finding_id: $id})
            SET f.status = 'resolved',
                f.resolved_at = toString(datetime()),
                f.resolution_note = $note
        """, id=finding_id, note=note.strip())


def get_finding_summary(driver: Driver) -> dict:
    """
    Return aggregate counts and total risk for the Findings Dashboard scorecard.
    {open, acknowledged, resolved, total_risk, by_severity}
    """
    with driver.session() as session:
        row = session.run("""
            MATCH (f:Finding)
            RETURN
                sum(CASE WHEN f.status = 'open'         THEN 1 ELSE 0 END) AS open,
                sum(CASE WHEN f.status = 'acknowledged' THEN 1 ELSE 0 END) AS acknowledged,
                sum(CASE WHEN f.status = 'resolved'     THEN 1 ELSE 0 END) AS resolved,
                sum(CASE WHEN f.status = 'open'
                          THEN toFloat(coalesce(f.estimated_risk_amount, 0))
                          ELSE 0 END)                                       AS total_risk
        """).single()

        severity_rows = session.run("""
            MATCH (f:Finding {status: 'open'})
            RETURN f.severity AS severity, count(f) AS n
        """).data()

    by_severity = {r["severity"]: r["n"] for r in severity_rows}
    return {
        "open":         row["open"] if row else 0,
        "acknowledged": row["acknowledged"] if row else 0,
        "resolved":     row["resolved"] if row else 0,
        "total_risk":   round(row["total_risk"] if row else 0, 2),
        "by_severity":  by_severity,
    }


def get_finding_subgraph(finding_id: str, driver: Driver) -> dict:
    """
    Return the immediate neighborhood of a finding:
    the Claim, the Finding, the DetectionRule, the Patient, and the Visit.
    Used for the split-pane visualization.
    Returns {nodes: [...], edges: [...]}.
    """
    with driver.session() as session:
        data = session.run("""
            MATCH (c:Claim)-[:HAS_FINDING]->(f:Finding {finding_id: $id})-[:TRIGGERED_BY]->(r:DetectionRule)
            OPTIONAL MATCH (p:Patient)-[:HAD_VISIT]->(v:Visit)-[:GENERATED_CLAIM]->(c)
            OPTIONAL MATCH (c)-[:SUBMITTED_TO]->(py:Payer)
            OPTIONAL MATCH (c)-[:BILLED_BY {billing_role: 'rendering'}]->(rp:Provider)
            OPTIONAL MATCH (c)-[:HAS_AUTHORIZATION]->(a:Authorization)
            RETURN c, f, r, p, v, py, rp, a
        """, id=finding_id).single()

    if not data:
        return {"nodes": [], "edges": []}

    nodes = []
    edges = []

    def _add_node(node, label, color, extra=None):
        if node is None:
            return None
        props = dict(node)
        nid = str(props.get("finding_id") or props.get("claim_id") or
                  props.get("rule_id") or props.get("patient_id") or
                  props.get("visit_id") or props.get("payer_id") or
                  props.get("npi") or props.get("auth_id") or id(node))
        nodes.append({"id": nid, "label": label, "color": color, "props": props})
        return nid

    NODE_COLORS = {
        "Claim":         "#e08c2a",
        "Finding":       "#a02828",
        "DetectionRule": "#4a3b7a",
        "Patient":       "#4a90d9",
        "Visit":         "#5ba55b",
        "Payer":         "#2eacb0",
        "Provider":      "#9b59b6",
        "Authorization": "#f39c12",
    }

    c_id  = _add_node(data["c"],  "Claim",         NODE_COLORS["Claim"])
    f_id  = _add_node(data["f"],  "Finding",       NODE_COLORS["Finding"])
    r_id  = _add_node(data["r"],  "DetectionRule", NODE_COLORS["DetectionRule"])
    p_id  = _add_node(data.get("p"),  "Patient",   NODE_COLORS["Patient"])
    v_id  = _add_node(data.get("v"),  "Visit",     NODE_COLORS["Visit"])
    py_id = _add_node(data.get("py"), "Payer",     NODE_COLORS["Payer"])
    rp_id = _add_node(data.get("rp"), "Provider",  NODE_COLORS["Provider"])
    a_id  = _add_node(data.get("a"),  "Auth",      NODE_COLORS["Authorization"])

    def _edge(src, tgt, label):
        if src and tgt:
            edges.append({"from": src, "to": tgt, "label": label})

    _edge(c_id,  f_id,  "HAS_FINDING")
    _edge(f_id,  r_id,  "TRIGGERED_BY")
    _edge(p_id,  v_id,  "HAD_VISIT")
    _edge(v_id,  c_id,  "GENERATED_CLAIM")
    _edge(c_id,  py_id, "SUBMITTED_TO")
    _edge(c_id,  rp_id, "BILLED_BY (rendering)")
    _edge(c_id,  a_id,  "HAS_AUTHORIZATION")

    return {"nodes": nodes, "edges": edges}


def get_finding_diagnostics(finding_id: str, driver: Driver) -> dict:
    """
    Return structured diagnostic facts for a finding based on its scenario.
    Used by the dashboard to show the exact comparison that triggered the rule.
    Returns {scenario, rows: [{label, actual, expected, status}]}
    """
    finding = get_finding(driver, finding_id)
    if not finding:
        return {}

    scenario = finding.get("scenario", "")
    claim_id = finding.get("claim_id", "")
    rows = []

    with driver.session() as session:

        if scenario == "S-01":
            data = session.run("""
                MATCH (c:Claim {claim_id: $cid})
                MATCH (c)-[:BILLED_PROCEDURE]->(billed:CPT_Code)
                OPTIONAL MATCH (c)-[:HAS_AUTHORIZATION]->(a:Authorization)
                OPTIONAL MATCH (a)-[:AUTH_FOR_PROCEDURE]->(auth_cpt:CPT_Code)
                RETURN c.claim_id AS claim_id,
                       c.claim_date AS claim_date,
                       billed.code AS billed_cpt,
                       billed.description AS cpt_desc,
                       a.auth_id AS auth_id,
                       a.auth_date AS auth_date,
                       a.expiry_date AS expiry_date,
                       a.approved_units AS approved_units,
                       auth_cpt.code AS auth_cpt
                LIMIT 1
            """, cid=claim_id).single()
            if data:
                d = dict(data)
                claim_date = d.get("claim_date", "")
                expiry = d.get("expiry_date", "")
                billed = d.get("billed_cpt", "")
                auth_cpt = d.get("auth_cpt", "NONE")
                auth_id = d.get("auth_id", "NONE")

                rows = [
                    {"label": "Claim Date",        "actual": claim_date,         "expected": "Service date",      "status": "info"},
                    {"label": "Auth ID",            "actual": auth_id,            "expected": "Valid auth required","status": "info" if auth_id != "NONE" else "fail"},
                    {"label": "Auth Expiry Date",   "actual": expiry,             "expected": f">= {claim_date}",  "status": "pass" if expiry and expiry >= claim_date else "fail"},
                    {"label": "CPT Billed",         "actual": billed,             "expected": billed,              "status": "info"},
                    {"label": "CPT Auth Covers",    "actual": auth_cpt,           "expected": billed,              "status": "pass" if auth_cpt == billed else "fail"},
                    {"label": "Procedure Desc",     "actual": d.get("cpt_desc",""),  "expected": "",               "status": "info"},
                ]

        elif scenario == "S-02":
            data = session.run("""
                MATCH (c:Claim {claim_id: $cid})
                MATCH (c)-[:BILLED_BY {billing_role:'rendering'}]->(rp:Provider)
                MATCH (c)-[:SUBMITTED_TO]->(py:Payer)
                OPTIONAL MATCH (rp)-[:CONTRACTED_WITH]->(con:Contract)-[:CONTRACT_WITH_PAYER]->(py)
                RETURN rp.npi AS rendering_npi, rp.name AS rendering_name,
                       rp.specialty AS specialty,
                       py.payer_id AS payer_id, py.payer_name AS payer_name,
                       con.contract_id AS contract_id,
                       con.effective_date AS eff_date,
                       con.termination_date AS term_date,
                       c.claim_date AS claim_date
                LIMIT 1
            """, cid=claim_id).single()
            if data:
                d = dict(data)
                has_contract = d.get("contract_id") is not None
                rows = [
                    {"label": "Rendering NPI",      "actual": d.get("rendering_npi",""),  "expected": "Must be credentialed", "status": "info"},
                    {"label": "Rendering Provider", "actual": d.get("rendering_name",""), "expected": "",                     "status": "info"},
                    {"label": "Specialty",          "actual": d.get("specialty",""),       "expected": "",                     "status": "info"},
                    {"label": "Billed Payer",       "actual": d.get("payer_name",""),      "expected": "Active contract req'd","status": "info"},
                    {"label": "Contract Found",     "actual": d.get("contract_id","NONE"), "expected": "Active contract",      "status": "pass" if has_contract else "fail"},
                    {"label": "Contract Effective", "actual": d.get("eff_date","N/A"),     "expected": f"<= {d.get('claim_date','')}", "status": "info"},
                    {"label": "Contract Termination","actual": d.get("term_date","N/A"),   "expected": f">= {d.get('claim_date','')}", "status": "info"},
                ]

        elif scenario == "S-03":
            data = session.run("""
                MATCH (c:Claim {claim_id: $cid})
                MATCH (c)-[:BILLED_BY]->(p:Provider)-[:CONTRACTED_WITH]->(old_con:Contract)
                MATCH (old_con)-[:SUPERSEDED_BY]->(new_con:Contract)
                RETURN p.npi AS npi, p.name AS name,
                       old_con.contract_id AS old_contract,
                       old_con.version_num AS old_version,
                       old_con.termination_date AS old_term,
                       new_con.contract_id AS new_contract,
                       new_con.version_num AS new_version,
                       new_con.effective_date AS new_eff,
                       c.claim_date AS claim_date
                LIMIT 1
            """, cid=claim_id).single()
            if data:
                d = dict(data)
                rows = [
                    {"label": "Provider",             "actual": d.get("name",""),        "expected": "",                       "status": "info"},
                    {"label": "Contract Used",        "actual": d.get("old_contract",""), "expected": d.get("new_contract",""), "status": "fail"},
                    {"label": "Contract Version",     "actual": f"v{d.get('old_version','?')}", "expected": f"v{d.get('new_version','?')}", "status": "fail"},
                    {"label": "Old Contract Expired", "actual": d.get("old_term",""),    "expected": "Should not be active",   "status": "fail"},
                    {"label": "New Contract Active",  "actual": d.get("new_eff",""),     "expected": "Should be in use",       "status": "fail"},
                    {"label": "Claim Date",           "actual": d.get("claim_date",""),  "expected": "",                       "status": "info"},
                ]

        elif scenario == "S-04":
            data = session.run("""
                MATCH (c:Claim {claim_id: $cid})-[:HAS_AUTHORIZATION]->(a:Authorization)
                MATCH (c)-[r:BILLED_PROCEDURE]->(cpt:CPT_Code)
                WITH c, a, sum(r.units) AS total_billed, a.approved_units AS approved
                RETURN a.auth_id AS auth_id,
                       total_billed, approved,
                       (total_billed - approved) AS over_by,
                       c.claim_date AS claim_date
                LIMIT 1
            """, cid=claim_id).single()
            if data:
                d = dict(data)
                rows = [
                    {"label": "Auth ID",          "actual": d.get("auth_id",""),     "expected": "",                              "status": "info"},
                    {"label": "Units Billed",      "actual": str(d.get("total_billed",0)), "expected": f"<= {d.get('approved',0)}", "status": "fail"},
                    {"label": "Units Approved",    "actual": str(d.get("approved",0)),     "expected": "Approved limit",            "status": "info"},
                    {"label": "Over by",           "actual": str(d.get("over_by",0)) + " units", "expected": "0",                  "status": "fail"},
                ]

        elif scenario == "S-05":
            data = session.run("""
                MATCH (c:Claim {claim_id: $cid})
                MATCH (v:Visit)-[:GENERATED_CLAIM]->(c)
                MATCH (p_dup:Patient)-[:HAD_VISIT]->(v)
                WHERE p_dup.flaw_scenario = 'S-05'
                MATCH (p_orig:Patient {patient_id: p_dup.duplicate_of})
                RETURN p_dup.patient_id AS dup_id,
                       p_dup.first_name + ' ' + p_dup.last_name AS dup_name,
                       p_dup.dob AS dup_dob,
                       p_orig.patient_id AS orig_id,
                       p_orig.first_name + ' ' + p_orig.last_name AS orig_name,
                       p_orig.dob AS orig_dob,
                       p_dup.zip AS zip
                LIMIT 1
            """, cid=claim_id).single()
            if data:
                d = dict(data)
                rows = [
                    {"label": "Duplicate MRN",   "actual": d.get("dup_id",""),   "expected": "Should not exist",      "status": "fail"},
                    {"label": "Duplicate Name",  "actual": d.get("dup_name",""), "expected": d.get("orig_name",""),   "status": "warn"},
                    {"label": "Duplicate DOB",   "actual": d.get("dup_dob",""),  "expected": d.get("orig_dob",""),    "status": "warn"},
                    {"label": "Canonical MRN",   "actual": d.get("orig_id",""),  "expected": "Canonical record",      "status": "info"},
                    {"label": "Canonical Name",  "actual": d.get("orig_name",""),"expected": "",                      "status": "info"},
                    {"label": "Canonical DOB",   "actual": d.get("orig_dob",""), "expected": "",                      "status": "info"},
                    {"label": "Shared Zip",      "actual": d.get("zip",""),      "expected": "Match confirms duplicate","status": "warn"},
                ]

        elif scenario == "S-06":
            data = session.run("""
                MATCH (c:Claim {claim_id: $cid})
                MATCH (v:Visit)-[:GENERATED_CLAIM]->(c)
                MATCH (c)-[:COVERED_UNDER]->(:Coverage)-[:COVERED_BY]->(pp:PayerPolicy)
                OPTIONAL MATCH (c)-[:HAS_REFERRAL]->(ro:ReferralOrder)
                OPTIONAL MATCH (ro)-[:REFERRED_BY]->(ref_prov:Provider)
                RETURN v.visit_date AS visit_date,
                       pp.plan_type AS plan_type,
                       ro.referral_id AS referral_id,
                       ro.order_date AS referral_date,
                       ref_prov.npi AS ref_npi,
                       ref_prov.name AS ref_name,
                       ref_prov.specialty AS ref_specialty
                LIMIT 1
            """, cid=claim_id).single()
            if data:
                d = dict(data)
                visit = d.get("visit_date","")
                ref_date = d.get("referral_date","")
                specialty = d.get("ref_specialty","")
                rows = [
                    {"label": "Plan Type",          "actual": d.get("plan_type",""),  "expected": "HMO requires referral",           "status": "info"},
                    {"label": "Visit Date",         "actual": visit,                  "expected": "",                                "status": "info"},
                    {"label": "Referral ID",        "actual": d.get("referral_id","MISSING"), "expected": "Valid referral required", "status": "fail" if not d.get("referral_id") else "info"},
                    {"label": "Referral Date",      "actual": ref_date or "N/A",      "expected": f"< {visit} (before visit)",       "status": "pass" if ref_date and ref_date < visit else "fail"},
                    {"label": "Referring Provider", "actual": d.get("ref_name","N/A"),"expected": "",                                "status": "info"},
                    {"label": "Referring Specialty","actual": specialty or "N/A",     "expected": "PCP",                             "status": "pass" if specialty == "PCP" else "fail"},
                ]

    return {"scenario": scenario, "claim_id": claim_id, "rows": rows}
