"""
viz.py — pyvis graph visualizations.

All functions return HTML strings rendered via st.components.v1.html().
Never writes temp files to disk. Height set explicitly (Windows iframe fix).
"""

import json
from pyvis.network import Network
from neo4j import Driver


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

NODE_COLORS = {
    "Patient":       "#4a90d9",
    "Visit":         "#5ba55b",
    "Claim":         "#888888",   # clean claim
    "ClaimFlawed":   "#e08c2a",   # flawed claim (amber)
    "CPT_Code":      "#95a5a6",
    "ICD10_Code":    "#bdc3c7",
    "Payer":         "#2eacb0",
    "PayerPolicy":   "#17849c",
    "Coverage":      "#aed6f1",
    "Provider":      "#9b59b6",
    "Contract":      "#7f8c8d",
    "Authorization": "#f39c12",
    "ReferralOrder": "#e74c3c",
    "DetectionRule": "#4a3b7a",
    "Finding":       "#a02828",
}

PYVIS_OPTIONS = json.dumps({
    "physics": {
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
            "gravitationalConstant": -60,
            "centralGravity": 0.01,
            "springLength": 120,
            "springConstant": 0.08,
            "damping": 0.4,
        },
        "stabilization": {"iterations": 150},
    },
    "nodes": {
        "font": {"size": 13, "color": "#222222"},
        "borderWidth": 2,
        "borderWidthSelected": 4,
    },
    "edges": {
        "font": {"size": 10, "color": "#555555", "align": "middle"},
        "arrows": {"to": {"enabled": True, "scaleFactor": 0.6}},
        "smooth": {"type": "continuous"},
    },
    "interaction": {
        "hover": True,
        "navigationButtons": False,
        "zoomView": True,
    },
})


def _new_net(height: str = "500px") -> Network:
    net = Network(height=height, width="100%", directed=True, bgcolor="#ffffff")
    net.set_options(PYVIS_OPTIONS)
    return net


# ---------------------------------------------------------------------------
# Panel 1 — Static ontology schema diagram
# ---------------------------------------------------------------------------

def build_ontology_diagram() -> str:
    """
    Returns pyvis HTML string showing all 14 node types and 21 relationship types.
    This is a schema diagram — not live data.
    """
    net = _new_net("480px")

    # Node type definitions: (label, color, shape)
    node_types = [
        ("Patient",       NODE_COLORS["Patient"],       "dot"),
        ("Visit",         NODE_COLORS["Visit"],         "dot"),
        ("Claim",         NODE_COLORS["ClaimFlawed"],   "dot"),
        ("CPT_Code",      NODE_COLORS["CPT_Code"],      "diamond"),
        ("ICD10_Code",    NODE_COLORS["ICD10_Code"],    "diamond"),
        ("Payer",         NODE_COLORS["Payer"],         "dot"),
        ("PayerPolicy",   NODE_COLORS["PayerPolicy"],   "dot"),
        ("Coverage",      NODE_COLORS["Coverage"],      "dot"),
        ("Provider",      NODE_COLORS["Provider"],      "dot"),
        ("Contract",      NODE_COLORS["Contract"],      "dot"),
        ("Authorization", NODE_COLORS["Authorization"], "dot"),
        ("ReferralOrder", NODE_COLORS["ReferralOrder"], "dot"),
        ("DetectionRule", NODE_COLORS["DetectionRule"], "star"),
        ("Finding",       NODE_COLORS["Finding"],       "star"),
    ]

    for label, color, shape in node_types:
        net.add_node(label, label=label, color=color, shape=shape, size=22,
                     title=f"Node type: {label}")

    # Relationship edges (representative, not exhaustive — one per rel type)
    edges = [
        ("Patient",       "Visit",         "HAD_VISIT"),
        ("Visit",         "Claim",         "GENERATED_CLAIM"),
        ("Claim",         "CPT_Code",      "BILLED_PROCEDURE"),
        ("Claim",         "ICD10_Code",    "CODED_DIAGNOSIS"),
        ("Claim",         "Payer",         "SUBMITTED_TO"),
        ("Claim",         "Provider",      "BILLED_BY"),
        ("Claim",         "Coverage",      "COVERED_UNDER"),
        ("Payer",         "PayerPolicy",   "HAS_POLICY"),
        ("Coverage",      "PayerPolicy",   "COVERED_BY"),
        ("Patient",       "Coverage",      "ENROLLED_IN"),
        ("PayerPolicy",   "CPT_Code",      "COVERS_PROCEDURE"),
        ("Provider",      "Contract",      "CONTRACTED_WITH"),
        ("Contract",      "Payer",         "CONTRACT_WITH_PAYER"),
        ("Claim",         "Authorization", "HAS_AUTHORIZATION"),
        ("Authorization", "Payer",         "AUTH_GRANTED_BY"),
        ("Authorization", "CPT_Code",      "AUTH_FOR_PROCEDURE"),
        ("Claim",         "ReferralOrder", "HAS_REFERRAL"),
        ("ReferralOrder", "Provider",      "REFERRED_BY"),
        ("Contract",      "Contract",      "SUPERSEDED_BY"),
        ("Claim",         "Finding",       "HAS_FINDING"),
        ("Finding",       "DetectionRule", "TRIGGERED_BY"),
    ]

    for src, tgt, rel in edges:
        net.add_edge(src, tgt, label=rel, title=rel, color="#999999",
                     font={"size": 9})

    return net.generate_html()


# ---------------------------------------------------------------------------
# Panel 3 — Claim neighborhood subgraph (live data)
# ---------------------------------------------------------------------------

def build_claim_neighborhood(claim_id: str, driver: Driver,
                              max_nodes: int = 300) -> str:
    """
    Returns pyvis HTML for the 2-hop neighborhood around a Claim.
    Flawed claims render amber. Finding nodes render deep red.
    """
    with driver.session() as session:
        data = session.run("""
            MATCH (c:Claim {claim_id: $cid})
            OPTIONAL MATCH (v:Visit)-[:GENERATED_CLAIM]->(c)
            OPTIONAL MATCH (p:Patient)-[:HAD_VISIT]->(v)
            OPTIONAL MATCH (c)-[:BILLED_PROCEDURE]->(cpt:CPT_Code)
            OPTIONAL MATCH (c)-[:CODED_DIAGNOSIS]->(dx:ICD10_Code)
            OPTIONAL MATCH (c)-[:SUBMITTED_TO]->(py:Payer)
            OPTIONAL MATCH (c)-[:BILLED_BY]->(prov:Provider)
            OPTIONAL MATCH (c)-[:COVERED_UNDER]->(cov:Coverage)
            OPTIONAL MATCH (c)-[:HAS_AUTHORIZATION]->(auth:Authorization)
            OPTIONAL MATCH (c)-[:HAS_REFERRAL]->(ro:ReferralOrder)
            OPTIONAL MATCH (c)-[:HAS_FINDING]->(f:Finding)-[:TRIGGERED_BY]->(r:DetectionRule)
            RETURN c, v, p,
                   collect(DISTINCT cpt) AS cpts,
                   collect(DISTINCT dx)  AS dxs,
                   py, prov, cov, auth, ro,
                   collect(DISTINCT f)   AS findings,
                   collect(DISTINCT r)   AS rules
        """, cid=claim_id).single()

    if not data:
        return "<html><body><p>Claim not found.</p></body></html>"

    net = _new_net("580px")

    def _safe(node, key, default=""):
        if node is None:
            return default
        return dict(node).get(key, default)

    c = data["c"]
    c_props = dict(c)
    is_flawed = c_props.get("is_flawed", False)
    claim_color = NODE_COLORS["ClaimFlawed"] if is_flawed else NODE_COLORS["Claim"]

    net.add_node(claim_id, label=f"Claim\n{claim_id}",
                 color=claim_color, shape="dot", size=28,
                 title=_node_title("Claim", c_props))

    def _add(nid, label, color, shape, props, size=20):
        if nid:
            net.add_node(str(nid), label=label, color=color, shape=shape,
                         size=size, title=_node_title(label.split("\n")[0], props))

    def _edge(src, tgt, rel):
        if src and tgt:
            net.add_edge(str(src), str(tgt), label=rel, color="#aaaaaa",
                         font={"size": 9})

    # Visit
    v = data.get("v")
    if v:
        vp = dict(v)
        vid = vp.get("visit_id", "visit")
        _add(vid, f"Visit\n{vp.get('visit_date','')}", NODE_COLORS["Visit"], "dot", vp)
        _edge(vid, claim_id, "GENERATED_CLAIM")

        # Patient
        p = data.get("p")
        if p:
            pp = dict(p)
            pid = pp.get("patient_id", "patient")
            _add(pid, f"Patient\n{pp.get('last_name','')}", NODE_COLORS["Patient"], "dot", pp, 24)
            _edge(pid, vid, "HAD_VISIT")

    # CPT codes
    for cpt in (data.get("cpts") or []):
        if cpt:
            cp = dict(cpt)
            code = cp.get("code", "")
            _add(code, f"CPT\n{code}", NODE_COLORS["CPT_Code"], "diamond", cp, 14)
            _edge(claim_id, code, "BILLED_PROCEDURE")

    # ICD-10 codes
    for dx in (data.get("dxs") or [])[:4]:
        if dx:
            dp = dict(dx)
            code = dp.get("code", "")
            _add(code, f"ICD10\n{code}", NODE_COLORS["ICD10_Code"], "diamond", dp, 12)
            _edge(claim_id, code, "CODED_DIAGNOSIS")

    # Payer
    py = data.get("py")
    if py:
        pyp = dict(py)
        pyid = pyp.get("payer_id", "payer")
        _add(pyid, f"Payer\n{pyp.get('payer_name','')[:15]}", NODE_COLORS["Payer"], "dot", pyp)
        _edge(claim_id, pyid, "SUBMITTED_TO")

    # Provider
    prov = data.get("prov")
    if prov:
        prvp = dict(prov)
        npi = prvp.get("npi", "prov")
        _add(npi, f"Provider\n{prvp.get('name','')[:15]}", NODE_COLORS["Provider"], "dot", prvp)
        _edge(claim_id, npi, "BILLED_BY")

    # Coverage
    cov = data.get("cov")
    if cov:
        covp = dict(cov)
        cov_id = covp.get("coverage_id", "cov")
        _add(cov_id, "Coverage", NODE_COLORS["Coverage"], "dot", covp, 14)
        _edge(claim_id, cov_id, "COVERED_UNDER")

    # Authorization
    auth = data.get("auth")
    if auth:
        ap = dict(auth)
        aid = ap.get("auth_id", "auth")
        _add(aid, f"Auth\n{aid}", NODE_COLORS["Authorization"], "dot", ap)
        _edge(claim_id, aid, "HAS_AUTHORIZATION")

    # Referral
    ro = data.get("ro")
    if ro:
        rop = dict(ro)
        rid = rop.get("referral_id", "ref")
        _add(rid, f"Referral\n{rid}", NODE_COLORS["ReferralOrder"], "dot", rop, 14)
        _edge(claim_id, rid, "HAS_REFERRAL")

    # Findings
    for f in (data.get("findings") or []):
        if f:
            fp = dict(f)
            fid = fp.get("finding_id", "finding")
            _add(fid, f"Finding\n{fp.get('severity','')}", NODE_COLORS["Finding"], "star", fp, 22)
            _edge(claim_id, fid, "HAS_FINDING")

    for r in (data.get("rules") or []):
        if r:
            rp = dict(r)
            rid_r = rp.get("rule_id", "rule")
            _add(rid_r, f"Rule\n{rid_r}", NODE_COLORS["DetectionRule"], "star", rp, 18)
            # find which finding triggered this rule
            for f in (data.get("findings") or []):
                if f:
                    _edge(dict(f).get("finding_id"), rid_r, "TRIGGERED_BY")

    return net.generate_html()


def _node_title(label: str, props: dict) -> str:
    """Build tooltip HTML from node properties."""
    lines = [f"<b>{label}</b>"]
    for k, v in props.items():
        if v is not None and v != "" and not k.startswith("_"):
            lines.append(f"{k}: {v}")
    return "<br>".join(lines)


# ---------------------------------------------------------------------------
# Panel 5 — Actual subgraph (with flaw + Finding)
# ---------------------------------------------------------------------------

def build_actual_subgraph(claim_id: str, driver: Driver, scenario: str = None) -> str:
    """
    Left pane: what actually exists in the graph for a flawed claim.
    - Affected nodes: amber
    - Missing relationships: dashed red MISSING edges (S-01 only)
    - Finding node: deep red
    Scenario-aware: S-05 shows duplicate patient context instead of auth chain.
    """
    # Auto-detect scenario if not passed
    if scenario is None:
        with driver.session() as _s:
            rec = _s.run(
                "MATCH (c:Claim {claim_id:$cid}) RETURN c.flaw_scenario AS s",
                cid=claim_id
            ).single()
            scenario = rec["s"] if rec else None
    with driver.session() as session:
        data = session.run("""
            MATCH (c:Claim {claim_id: $cid})
            OPTIONAL MATCH (v:Visit)-[:GENERATED_CLAIM]->(c)
            OPTIONAL MATCH (p:Patient)-[:HAD_VISIT]->(v)
            OPTIONAL MATCH (c)-[:SUBMITTED_TO]->(py:Payer)
            OPTIONAL MATCH (c)-[:BILLED_BY {billing_role:'rendering'}]->(rp:Provider)
            OPTIONAL MATCH (c)-[:HAS_AUTHORIZATION]->(auth:Authorization)
            OPTIONAL MATCH (auth)-[:AUTH_FOR_PROCEDURE]->(cpt:CPT_Code)
            OPTIONAL MATCH (c)-[:HAS_REFERRAL]->(ro:ReferralOrder)
            OPTIONAL MATCH (c)-[:HAS_FINDING]->(f:Finding)-[:TRIGGERED_BY]->(rule:DetectionRule)
            RETURN c, v, p, py, rp, auth, cpt, ro, f, rule
        """, cid=claim_id).single()

    if not data:
        return "<html><body><p>Claim not found.</p></body></html>"

    net = _new_net("380px")

    c_props = dict(data["c"])
    flaw_scenario = c_props.get("flaw_scenario", "")

    # Claim — always amber in actual view when flawed
    net.add_node(claim_id, label=f"Claim\n{claim_id}",
                 color=NODE_COLORS["ClaimFlawed"], shape="dot", size=28,
                 title=_node_title("Claim", c_props))

    def _add(node_id, label, color, props=None):
        if node_id:
            net.add_node(str(node_id), label=label, color=color, shape="dot",
                         size=20, title=_node_title(label.split("\n")[0], props or {}))

    def _edge(s, t, lbl, dashed=False, color="#aaaaaa"):
        if s and t:
            net.add_edge(str(s), str(t), label=lbl, color=color,
                         dashes=dashed, font={"size": 9})

    # Visit + Patient
    v = data.get("v")
    if v:
        vp = dict(v)
        vid = vp["visit_id"]
        _add(vid, f"Visit\n{vp.get('visit_date','')}", NODE_COLORS["Visit"], vp)
        _edge(vid, claim_id, "GENERATED_CLAIM")
        p = data.get("p")
        if p:
            pp = dict(p)
            pid = pp["patient_id"]
            _add(pid, f"Patient\n{pp.get('last_name','')}", NODE_COLORS["Patient"], pp)
            _edge(pid, vid, "HAD_VISIT")

    # Payer
    py = data.get("py")
    if py:
        pyp = dict(py)
        pyid = pyp["payer_id"]
        _add(pyid, f"Payer\n{pyp.get('payer_name','')[:15]}", NODE_COLORS["Payer"], pyp)
        _edge(claim_id, pyid, "SUBMITTED_TO")

    # Rendering provider
    rp = data.get("rp")
    if rp:
        rpp = dict(rp)
        npi = rpp["npi"]
        _add(npi, f"Provider\n{rpp.get('name','')[:15]}", NODE_COLORS["Provider"], rpp)
        _edge(claim_id, npi, "BILLED_BY")

    # Authorization — only show for auth-related scenarios
    auth = data.get("auth")
    if scenario in ("S-01", "S-04", None):
        if auth:
            ap = dict(auth)
            aid = ap["auth_id"]

            if scenario == "S-04":
                # S-04: fetch actual billed units from graph to annotate the node
                with driver.session() as _us:
                    unit_data = _us.run("""
                        MATCH (c:Claim {claim_id: $cid})-[r:BILLED_PROCEDURE]->(:CPT_Code)
                        MATCH (c)-[:HAS_AUTHORIZATION]->(a:Authorization {auth_id: $aid})
                        RETURN sum(r.units) AS billed, a.approved_units AS approved
                    """, cid=claim_id, aid=aid).single()
                if unit_data:
                    billed   = int(unit_data["billed"]   or 0)
                    approved = int(unit_data["approved"] or 0)
                    over     = billed - approved
                    auth_color = "#cc0000"
                    auth_label = (f"Auth\n{aid}\n"
                                  f"⚠ {billed}/{approved} units\n"
                                  f"(+{over} over limit)")
                    auth_title = (f"<b>⚠ UNIT EXHAUSTION</b><br>"
                                  f"Auth ID: {aid}<br>"
                                  f"Approved units: {approved}<br>"
                                  f"Billed units: {billed}<br>"
                                  f"Over by: {over} units")
                    net.add_node(aid, label=auth_label, color=auth_color,
                                 shape="dot", size=24, borderWidth=3, title=auth_title)
                    _edge(claim_id, aid, "HAS_AUTHORIZATION")
                    # Also annotate the BILLED_PROCEDURE edge with units
                    cpt = data.get("cpt")
                    if cpt:
                        cp = dict(cpt)
                        _add(cp["code"], f"CPT\n{cp['code']}", NODE_COLORS["CPT_Code"], cp)
                        net.add_edge(claim_id, cp["code"],
                                     label=f"BILLED_PROCEDURE\n({billed} units)",
                                     color="#cc0000", font={"size": 9, "color": "#cc0000"})
                        _edge(aid, cp["code"], "AUTH_FOR_PROCEDURE")
                else:
                    _add(aid, f"Auth\n{aid}", NODE_COLORS["Authorization"], ap)
                    _edge(claim_id, aid, "HAS_AUTHORIZATION")
            else:
                # S-01: highlight expired auth
                c_props_local = dict(data["c"])
                claim_dt = c_props_local.get("claim_date", "")
                expiry = ap.get("expiry_date", "")
                auth_color = "#cc0000" if (expiry and claim_dt and expiry < claim_dt) else NODE_COLORS["Authorization"]
                auth_label = f"Auth\n{aid}" + ("\n⚠ EXPIRED" if auth_color == "#cc0000" else "")
                _add(aid, auth_label, auth_color, ap)
                _edge(claim_id, aid, "HAS_AUTHORIZATION")
                cpt = data.get("cpt")
                if cpt:
                    cp = dict(cpt)
                    _add(cp["code"], f"CPT\n{cp['code']}", NODE_COLORS["CPT_Code"], cp)
                    _edge(aid, cp["code"], "AUTH_FOR_PROCEDURE")

        elif scenario == "S-01":
            # Only show MISSING placeholder for S-01 (auth genuinely expected)
            net.add_node("__missing_auth__", label="Authorization\n(MISSING)",
                         color="#cc0000", shape="dot", size=20, borderWidth=3,
                         title="Authorization relationship missing — link was severed")
            _edge(claim_id, "__missing_auth__", "HAS_AUTHORIZATION\n(MISSING)",
                  dashed=True, color="#cc0000")

    # Duplicate patient context — S-05
    if scenario == "S-05":
        with driver.session() as _ds:
            dup_data = _ds.run("""
                MATCH (c:Claim {claim_id: $cid})
                MATCH (v:Visit)-[:GENERATED_CLAIM]->(c)
                MATCH (p_dup:Patient)-[:HAD_VISIT]->(v)
                WHERE p_dup.flaw_scenario = 'S-05'
                OPTIONAL MATCH (p_orig:Patient {patient_id: p_dup.duplicate_of})
                RETURN p_dup.patient_id AS dup_id,
                       p_dup.first_name + ' ' + p_dup.last_name AS dup_name,
                       p_dup.dob AS dup_dob,
                       p_orig.patient_id AS orig_id,
                       p_orig.first_name + ' ' + p_orig.last_name AS orig_name,
                       p_orig.dob AS orig_dob
                LIMIT 1
            """, cid=claim_id).single()
        if dup_data:
            dd = dict(dup_data)
            dup_id  = dd.get("dup_id", "dup")
            orig_id = dd.get("orig_id", "orig")
            dup_title = (f"<b>DUPLICATE Patient</b><br>Name: {dd.get('dup_name','')}"
                         f"<br>DOB: {dd.get('dup_dob','')}<br>MRN: {dup_id}")
            orig_title = (f"<b>Canonical Patient</b><br>Name: {dd.get('orig_name','')}"
                          f"<br>DOB: {dd.get('orig_dob','')}<br>MRN: {orig_id}")
            net.add_node(dup_id,  label=f"Patient (DUP)\n{dd.get('dup_name','')[:15]}",
                         color="#cc0000", shape="dot", size=24, title=dup_title)
            net.add_node(orig_id, label=f"Patient (canonical)\n{dd.get('orig_name','')[:15]}",
                         color=NODE_COLORS["Patient"], shape="dot", size=24, title=orig_title)
            net.add_edge(dup_id, orig_id, label="DUPLICATE_OF",
                         color="#cc0000", dashes=True, font={"size": 10})

    # S-02 — Missing contract between rendering provider and payer
    if scenario == "S-02" and rp and py:
        rpp = dict(rp)
        pyp = dict(py)
        npi = rpp.get("npi", "prov")
        pyid = pyp.get("payer_id", "payer")
        with driver.session() as _cs:
            contract_check = _cs.run("""
                MATCH (rp:Provider {npi: $npi})
                MATCH (py:Payer {payer_id: $pyid})
                OPTIONAL MATCH (rp)-[:CONTRACTED_WITH]->(con:Contract)-[:CONTRACT_WITH_PAYER]->(py)
                RETURN count(con) AS contract_count
            """, npi=npi, pyid=pyid).single()
        if contract_check and contract_check["contract_count"] == 0:
            net.add_node("__missing_contract__",
                         label="Contract\n(MISSING)",
                         color="#cc0000", shape="dot", size=20, borderWidth=3,
                         title="No active contract found — provider not credentialed with this payer")
            _edge(npi, "__missing_contract__", "CONTRACTED_WITH\n(MISSING)",
                  dashed=True, color="#cc0000")
            _edge("__missing_contract__", pyid, "CONTRACT_WITH_PAYER\n(MISSING)",
                  dashed=True, color="#cc0000")

    # S-03 — Show both old (stale) and new contract with SUPERSEDED_BY
    if scenario == "S-03" and rp:
        rpp = dict(rp)
        npi = rpp.get("npi", "prov")
        with driver.session() as _cs3:
            con_data = _cs3.run("""
                MATCH (p:Provider {npi: $npi})-[:CONTRACTED_WITH]->(old:Contract)
                MATCH (old)-[:SUPERSEDED_BY]->(newer:Contract)
                RETURN old.contract_id AS old_id, old.version_num AS old_v,
                       newer.contract_id AS new_id, newer.version_num AS new_v
                LIMIT 1
            """, npi=npi).single()
        if con_data:
            cd = dict(con_data)
            old_id = str(cd.get("old_id") or "old_con")
            new_id = str(cd.get("new_id") or "new_con")
            net.add_node(old_id,
                         label=f"Contract v{cd.get('old_v','?')}\n{old_id}\n⚠ STALE",
                         color="#cc0000", shape="dot", size=20,
                         title=f"<b>STALE Contract</b><br>ID: {old_id}<br>Version: {cd.get('old_v','?')}<br>This is the contract the claim was resolved against")
            net.add_node(new_id,
                         label=f"Contract v{cd.get('new_v','?')}\n{new_id}\n✓ CURRENT",
                         color="#27ae60", shape="dot", size=20,
                         title=f"<b>Current Contract</b><br>ID: {new_id}<br>Version: {cd.get('new_v','?')}<br>This should have been used")
            _edge(npi, old_id, "CONTRACTED_WITH\n(stale)", color="#cc0000")
            _edge(old_id, new_id, "SUPERSEDED_BY", dashed=True, color="#cc0000")

    # Referral — S-06 shows missing or post-dated referral indicator
    ro = data.get("ro")
    if scenario == "S-06":
        v_node = data.get("v")
        visit_date = dict(v_node).get("visit_date", "") if v_node else ""
        if ro is None:
            # Referral entirely missing
            net.add_node("__missing_referral__",
                         label="Referral\n(MISSING)",
                         color="#cc0000", shape="dot", size=20, borderWidth=3,
                         title="HMO claim requires a referral order — none found in graph")
            _edge(claim_id, "__missing_referral__", "HAS_REFERRAL\n(MISSING)",
                  dashed=True, color="#cc0000")
        else:
            rop = dict(ro)
            rid = rop["referral_id"]
            ref_date = rop.get("order_date", "")
            is_postdated = ref_date and visit_date and ref_date > visit_date
            ref_color = "#cc0000" if is_postdated else NODE_COLORS["ReferralOrder"]
            ref_label = f"Referral\n{rid}" + (f"\n⚠ POST-DATED\n{ref_date}" if is_postdated else "")
            net.add_node(rid, label=ref_label, color=ref_color, shape="dot", size=20,
                         title=f"<b>{'⚠ POST-DATED REFERRAL' if is_postdated else 'Referral'}</b><br>"
                               f"ID: {rid}<br>Order date: {ref_date}<br>Visit date: {visit_date}")
            _edge(claim_id, rid, "HAS_REFERRAL")
            # Show referring provider with specialty check
            with driver.session() as _rs:
                ref_prov = _rs.run("""
                    MATCH (ro:ReferralOrder {referral_id: $rid})-[:REFERRED_BY]->(p:Provider)
                    RETURN p.npi AS npi, p.name AS name, p.specialty AS specialty
                    LIMIT 1
                """, rid=rid).single()
            if ref_prov:
                rfd = dict(ref_prov)
                ref_npi = str(rfd.get("npi") or "ref_prov")
                is_not_pcp = rfd.get("specialty", "") != "PCP"
                prov_color = "#cc0000" if is_not_pcp else "#27ae60"
                prov_label = (f"Provider\n{rfd.get('name','')[:15]}"
                              + (f"\n⚠ NOT PCP\n({rfd.get('specialty','')})" if is_not_pcp else "\n✓ PCP"))
                net.add_node(ref_npi, label=prov_label,
                             color=prov_color, shape="dot", size=20,
                             title=f"Referring Provider: {rfd.get('name','')}<br>Specialty: {rfd.get('specialty','')}")
                _edge(rid, ref_npi, "REFERRED_BY")
    elif ro and scenario not in ("S-06",):
        rop = dict(ro)
        rid = rop["referral_id"]
        _add(rid, f"Referral\n{rid}", NODE_COLORS["ReferralOrder"], rop)
        _edge(claim_id, rid, "HAS_REFERRAL")

    # Finding + DetectionRule
    f = data.get("f")
    if f:
        fp = dict(f)
        fid = fp["finding_id"]
        net.add_node(fid, label=f"Finding\n{fp.get('severity','')}",
                     color=NODE_COLORS["Finding"], shape="star", size=26,
                     title=_node_title("Finding", fp))
        _edge(claim_id, fid, "HAS_FINDING", color="#a02828")

        rule = data.get("rule")
        if rule:
            rp2 = dict(rule)
            rid2 = rp2["rule_id"]
            net.add_node(rid2, label=f"Rule\n{rid2}",
                         color=NODE_COLORS["DetectionRule"], shape="star", size=22,
                         title=_node_title("DetectionRule", rp2))
            _edge(fid, rid2, "TRIGGERED_BY", color="#4a3b7a")

    return net.generate_html()


# ---------------------------------------------------------------------------
# Panel 5 — Expected subgraph (clean ontology path)
# ---------------------------------------------------------------------------

SCENARIO_NARRATIVES = {
    "S-01": {
        "title": "Expected: Valid Auth Chain",
        "nodes": [
            ("Patient",       "Patient",       "#4a90d9"),
            ("Visit",         "Visit",         "#5ba55b"),
            ("Claim",         "Claim",         "#888888"),
            ("Authorization", "Authorization", "#f39c12"),
            ("CPT_Code",      "CPT Code",      "#95a5a6"),
            ("Payer",         "Payer",         "#2eacb0"),
        ],
        "edges": [
            ("Patient", "Visit",         "HAD_VISIT"),
            ("Visit",   "Claim",         "GENERATED_CLAIM"),
            ("Claim",   "Authorization", "HAS_AUTHORIZATION"),
            ("Authorization", "CPT_Code", "AUTH_FOR_PROCEDURE"),
            ("Claim",   "Payer",         "SUBMITTED_TO"),
        ],
    },
    "S-02": {
        "title": "Expected: Credentialed Provider",
        "nodes": [
            ("Patient",  "Patient",   "#4a90d9"),
            ("Visit",    "Visit",     "#5ba55b"),
            ("Claim",    "Claim",     "#888888"),
            ("Provider", "Provider",  "#9b59b6"),
            ("Contract", "Contract",  "#7f8c8d"),
            ("Payer",    "Payer",     "#2eacb0"),
        ],
        "edges": [
            ("Patient", "Visit",    "HAD_VISIT"),
            ("Visit",   "Claim",    "GENERATED_CLAIM"),
            ("Claim",   "Provider", "BILLED_BY (rendering)"),
            ("Provider","Contract", "CONTRACTED_WITH"),
            ("Contract","Payer",    "CONTRACT_WITH_PAYER"),
            ("Claim",   "Payer",    "SUBMITTED_TO"),
        ],
    },
    "S-03": {
        "title": "Expected: Current Contract Version",
        "nodes": [
            ("Patient",    "Patient",      "#4a90d9"),
            ("Visit",      "Visit",        "#5ba55b"),
            ("Claim",      "Claim",        "#888888"),
            ("Provider",   "Provider",     "#9b59b6"),
            ("ContractV1", "Contract v1",  "#7f8c8d"),
            ("ContractV2", "Contract v2\n(current)", "#27ae60"),
            ("Payer",      "Payer",        "#2eacb0"),
        ],
        "edges": [
            ("Patient",    "Visit",       "HAD_VISIT"),
            ("Visit",      "Claim",       "GENERATED_CLAIM"),
            ("Claim",      "Provider",    "BILLED_BY"),
            ("Provider",   "ContractV2",  "CONTRACTED_WITH (current)"),
            ("ContractV1", "ContractV2",  "SUPERSEDED_BY"),
            ("ContractV2", "Payer",       "CONTRACT_WITH_PAYER"),
        ],
    },
    "S-04": {
        "title": "Expected: Units Within Auth Limit",
        "nodes": [
            ("Patient",       "Patient",       "#4a90d9"),
            ("Visit",         "Visit",         "#5ba55b"),
            ("Claim",         "Claim",         "#888888"),
            ("Authorization", "Authorization", "#f39c12"),
            ("CPT_Code",      "CPT Code",      "#95a5a6"),
        ],
        "edges": [
            ("Patient",       "Visit",         "HAD_VISIT"),
            ("Visit",         "Claim",         "GENERATED_CLAIM"),
            ("Claim",         "Authorization", "HAS_AUTHORIZATION"),
            ("Authorization", "CPT_Code",      "AUTH_FOR_PROCEDURE"),
            ("Claim",         "CPT_Code",      "BILLED_PROCEDURE\n(units <= approved)"),
        ],
    },
    "S-05": {
        "title": "Expected: Unique Patient Identity",
        "nodes": [
            ("Patient", "Patient\n(one canonical record)", "#4a90d9"),
            ("Visit",   "Visit",                           "#5ba55b"),
            ("Claim",   "Claim",                           "#888888"),
        ],
        "edges": [
            ("Patient", "Visit", "HAD_VISIT"),
            ("Visit",   "Claim", "GENERATED_CLAIM"),
        ],
    },
    "S-06": {
        "title": "Expected: Valid HMO Referral",
        "nodes": [
            ("Patient",       "Patient",       "#4a90d9"),
            ("Visit",         "Visit",         "#5ba55b"),
            ("Claim",         "Claim",         "#888888"),
            ("ReferralOrder", "Referral\n(before visit)", "#e74c3c"),
            ("PCP",           "PCP Provider",  "#9b59b6"),
            ("Coverage",      "HMO Coverage",  "#aed6f1"),
        ],
        "edges": [
            ("Patient",       "Visit",         "HAD_VISIT"),
            ("Visit",         "Claim",         "GENERATED_CLAIM"),
            ("Claim",         "ReferralOrder", "HAS_REFERRAL"),
            ("ReferralOrder", "PCP",           "REFERRED_BY (PCP)"),
            ("Claim",         "Coverage",      "COVERED_UNDER (HMO)"),
        ],
    },
}


def build_expected_subgraph(scenario_id: str, driver: Driver = None) -> str:
    """
    Right pane: clean expected path per ontology for the given scenario.
    All edges solid green. No Finding node.
    """
    spec = SCENARIO_NARRATIVES.get(scenario_id, SCENARIO_NARRATIVES["S-01"])
    net = _new_net("380px")

    for node_id, label, color in spec["nodes"]:
        net.add_node(node_id, label=label, color=color, shape="dot", size=22,
                     title=f"Expected: {label}")

    for src, tgt, label in spec["edges"]:
        net.add_edge(src, tgt, label=label, color="#27ae60",
                     width=2, font={"size": 9, "color": "#1a6e34"})

    return net.generate_html()
