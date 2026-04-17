"""
panel_loader.py — Panel 4: Scenario Loader.

Inject/clear flaws and run detection rules. The most interactive panel.
"""

import streamlit as st
from neo4j import Driver
from graph import flaw_injector, detection


SCENARIOS = [
    {
        "id":          "S-01",
        "name":        "Unverifiable Prior Authorization Chain",
        "category":    "prior_authorization",
        "severity":    "HIGH",
        "description": "Auth chain broken: missing HAS_AUTHORIZATION, wrong CPT, or expired auth.",
        "quote":       "\"This claim passed pre-bill edits. The graph found the auth chain was severed.\"",
        "rule_id":     "DR-S01",
        "cat_color":   "#e74c3c",
    },
    {
        "id":          "S-02",
        "name":        "Rendering Provider Not Credentialed with Billed Payer",
        "category":    "credentialing",
        "severity":    "HIGH",
        "description": "Rendering NPI has no active contract with the payer on the claim.",
        "quote":       "\"Credentialing gaps are invisible in flat-file edits. Graph traversal finds them in milliseconds.\"",
        "rule_id":     "DR-S02",
        "cat_color":   "#9b59b6",
    },
    {
        "id":          "S-03",
        "name":        "Claim Resolved Against Superseded Contract Version",
        "category":    "contract",
        "severity":    "MEDIUM",
        "description": "Provider connected to expired contract v1; current v2 was superseded.",
        "quote":       "\"Contract versioning errors cause systematic underpayment — invisible until graph traversal exposes the SUPERSEDED_BY chain.\"",
        "rule_id":     "DR-S03",
        "cat_color":   "#f39c12",
    },
    {
        "id":          "S-04",
        "name":        "Authorization Unit Exhaustion Across Claims",
        "category":    "authorization_units",
        "severity":    "MEDIUM",
        "description": "Sum of billed units across linked claims exceeds approved auth units.",
        "quote":       "\"No single claim looks wrong. The graph aggregates across claims to find the exhaustion.\"",
        "rule_id":     "DR-S04",
        "cat_color":   "#e67e22",
    },
    {
        "id":          "S-05",
        "name":        "Duplicate Patient Identity Across Source Systems",
        "category":    "entity_integrity",
        "severity":    "MEDIUM",
        "description": "Duplicate patient nodes with name/DOB variations sharing same provider+payer.",
        "quote":       "\"Duplicate identities split care history. The graph finds them where EMRs and clearinghouses can't.\"",
        "rule_id":     "DR-S05",
        "cat_color":   "#3498db",
    },
    {
        "id":          "S-06",
        "name":        "Invalid HMO Referral Chain",
        "category":    "referral",
        "severity":    "HIGH",
        "description": "HMO specialist claim: missing referral, post-visit referral date, or non-PCP referrer.",
        "quote":       "\"HMO referral chain violations cascade to denials. The graph checks the full chain — not just the claim header.\"",
        "rule_id":     "DR-S06",
        "cat_color":   "#1abc9c",
    },
]

STATUS_COLORS = {
    "pending": ("#888888", "⬜"),
    "loaded":  ("#27ae60", "✅"),
}


def _init_state():
    if "scenario_status" not in st.session_state:
        st.session_state.scenario_status = {s["id"]: "pending" for s in SCENARIOS}
    if "scenario_inventory" not in st.session_state:
        st.session_state.scenario_inventory = {}
    if "scenario_results" not in st.session_state:
        st.session_state.scenario_results = {}


def _sync_state_from_graph(driver: Driver) -> int:
    """
    Query the graph for active flawed scenarios and sync session state.
    Returns total count of flawed claims across all scenarios.
    """
    total_flawed = 0
    try:
        with driver.session() as s:
            rows = s.run("""
                MATCH (c:Claim)
                WHERE c.flaw_scenario IS NOT NULL
                RETURN c.flaw_scenario AS sid, count(c) AS n
            """).data()
        active_in_graph = {r["sid"] for r in rows if r["n"] > 0}
        total_flawed = sum(r["n"] for r in rows)

        for sid in active_in_graph:
            if st.session_state.scenario_status.get(sid) == "pending":
                st.session_state.scenario_status[sid] = "loaded"
    except Exception:
        pass
    return total_flawed


def render(driver: Driver) -> None:
    _init_state()

    st.title("Scenario Loader")
    st.markdown(
        "_Introduce a data quality problem that happens in real operations. "
        "Watch the sidebar update as findings are created._"
    )

    # ── Sync session state from graph (survives page reload) ──────────────────
    total_flawed = _sync_state_from_graph(driver)

    # ── Clear All Flaws ───────────────────────────────────────────────────────
    any_loaded = total_flawed > 0 or any(
        v == "loaded" for v in st.session_state.scenario_status.values()
    )

    col_hdr, col_clear = st.columns([4, 1])
    with col_clear:
        if any_loaded:
            if st.button("🗑 Clear All Flaws", use_container_width=True):
                with st.spinner("Restoring baseline..."):
                    flaw_injector.clear_all_flaws(
                        driver,
                        st.session_state.scenario_inventory
                    )
                st.session_state.scenario_status = {
                    s["id"]: "pending" for s in SCENARIOS
                }
                st.session_state.scenario_inventory = {}
                st.session_state.scenario_results = {}
                st.rerun()

    st.divider()

    # ── Scenario rows ─────────────────────────────────────────────────────────
    for scenario in SCENARIOS:
        sid    = scenario["id"]
        status = st.session_state.scenario_status.get(sid, "pending")
        color, icon = STATUS_COLORS.get(status, ("#888", "⬜"))

        with st.container():
            row_cols = st.columns([0.5, 4, 1.5, 1.5])

            with row_cols[0]:
                st.markdown(
                    f'<div style="font-size:1.4rem;padding-top:6px">{icon}</div>',
                    unsafe_allow_html=True,
                )

            with row_cols[1]:
                st.markdown(
                    f'<span style="font-weight:700;font-size:1rem">{sid}: {scenario["name"]}</span><br>'
                    f'<span style="background:{scenario["cat_color"]};color:white;padding:1px 7px;'
                    f'border-radius:8px;font-size:0.75rem">{scenario["category"]}</span>&nbsp;'
                    f'<span style="color:#666;font-size:0.85rem">{scenario["description"]}</span>',
                    unsafe_allow_html=True,
                )

            with row_cols[2]:
                # Live finding count for this scenario
                try:
                    with driver.session() as _s:
                        fc = _s.run(
                            "MATCH (f:Finding)-[:TRIGGERED_BY]->(r:DetectionRule {rule_id:$rid}) "
                            "RETURN count(f) AS n",
                            rid=scenario["rule_id"]
                        ).single()["n"]
                except Exception:
                    fc = 0
                if fc > 0:
                    st.markdown(
                        f'<span style="background:#a02828;color:white;padding:3px 10px;'
                        f'border-radius:10px;font-weight:bold">{fc} findings</span>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("0 findings")

            with row_cols[3]:
                if status == "pending":
                    if st.button(f"Inject {sid}", key=f"inject_{sid}",
                                 use_container_width=True):
                        with st.spinner(f"Injecting {sid}..."):
                            result = flaw_injector.inject(sid, driver)
                        with st.spinner(f"Running detection {scenario['rule_id']}..."):
                            finding_count = detection.run_rule(
                                scenario["rule_id"], driver
                            )

                        result["finding_count"] = finding_count
                        st.session_state.scenario_results[sid] = result
                        st.session_state.scenario_inventory[sid] = result.get("inventory", [])
                        st.session_state.scenario_status[sid] = "loaded"
                        st.rerun()
                else:
                    st.markdown(
                        f'<span style="color:{color};font-weight:600">Loaded</span>',
                        unsafe_allow_html=True,
                    )

        # Post-injection summary card
        if status == "loaded" and sid in st.session_state.scenario_results:
            res = st.session_state.scenario_results[sid]
            with st.expander(f"📊 {sid} Injection Summary", expanded=False):
                sc1, sc2, sc3 = st.columns(3)
                sc1.metric("Claims Affected", res.get("claims_affected", "—"))
                sc2.metric("Findings Created", res.get("finding_count", "—"))
                sc3.metric("Changes Made",
                           len(res.get("inventory", [])))

                st.markdown(f"**Changes:** {res.get('changes_summary', '')}")
                st.markdown(f"> {scenario['quote']}")

        st.markdown("<hr style='margin:6px 0;border-color:#eee'>",
                    unsafe_allow_html=True)

    # ── Production callout ───────────────────────────────────────────────────
    st.info(
        "💡 Each scenario is isolated by `flaw_scenario` tag. "
        "Multiple scenarios can be active simultaneously without interference. "
        "Detection Cypher is stored in the graph as `DetectionRule` nodes — "
        "the runner is generic."
    )
