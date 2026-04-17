"""
panel_foundation.py — Panel 3: KG Foundation.

Search by Claim ID or Patient ID and render the 2-hop neighborhood.
"""

import streamlit as st
import streamlit.components.v1 as components
from neo4j import Driver
from graph import viz


def _get_metrics(driver: Driver) -> dict:
    with driver.session() as session:
        total = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
        rels  = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
        open_f = session.run(
            "MATCH (f:Finding {status:'open'}) RETURN count(f) AS n"
        ).single()["n"]
        active = session.run(
            "MATCH (c:Claim) WHERE c.flaw_scenario IS NOT NULL "
            "RETURN DISTINCT c.flaw_scenario AS s LIMIT 6"
        ).data()
    active_names = ", ".join(r["s"] for r in active) if active else "None"
    return {
        "total_nodes": total,
        "total_rels":  rels,
        "open_findings": open_f,
        "active_scenarios": active_names,
    }


def _get_sample_claim_id(driver: Driver) -> str:
    with driver.session() as session:
        rec = session.run("MATCH (c:Claim) RETURN c.claim_id LIMIT 1").single()
    return rec["c.claim_id"] if rec else ""


def _get_patient_claims(patient_id: str, driver: Driver) -> list:
    with driver.session() as session:
        rows = session.run("""
            MATCH (p:Patient {patient_id: $pid})-[:HAD_VISIT]->(v:Visit)-[:GENERATED_CLAIM]->(c:Claim)
            RETURN c.claim_id AS claim_id
            LIMIT 20
        """, pid=patient_id).data()
    return [r["claim_id"] for r in rows]


def render(driver: Driver) -> None:
    st.title("KG Foundation")
    st.markdown(
        "_Here is what the live graph looks like. "
        "Every claim, every provider, every auth chain — traversable._"
    )

    # ── Metrics bar ──────────────────────────────────────────────────────────
    metrics = _get_metrics(driver)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Nodes",         f"{metrics['total_nodes']:,}")
    m2.metric("Total Relationships",  f"{metrics['total_rels']:,}")
    m3.metric("Open Findings",        str(metrics["open_findings"]))
    m4.metric("Active Scenarios",     metrics["active_scenarios"] or "None")

    st.divider()

    # ── Search ───────────────────────────────────────────────────────────────
    col_search, col_btn = st.columns([4, 1])
    with col_search:
        query = st.text_input(
            "Search by Claim ID or Patient ID",
            placeholder="e.g. CLM0000001 or PT00001",
            label_visibility="visible",
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        search_clicked = st.button("Search", use_container_width=True)

    # Resolve claim_id to render
    claim_id_to_render = None

    if query and search_clicked:
        q = query.strip()
        if q.startswith("CLM") or q.startswith("clm"):
            claim_id_to_render = q.upper()
        elif q.startswith("PT") or q.startswith("MRN"):
            claims = _get_patient_claims(q, driver)
            if claims:
                claim_id_to_render = claims[0]
                st.info(f"Patient {q} has {len(claims)} claims. Showing first: **{claim_id_to_render}**")
                if len(claims) > 1:
                    with st.expander("Switch to another claim"):
                        selected = st.selectbox("Claim ID", claims)
                        if selected:
                            claim_id_to_render = selected
            else:
                st.warning(f"No claims found for patient {q}.")
        else:
            # Try as claim ID directly
            claim_id_to_render = q

    # Default view: sample claim
    if not claim_id_to_render:
        claim_id_to_render = _get_sample_claim_id(driver)
        if not search_clicked:
            st.caption(f"Showing sample claim: **{claim_id_to_render}** — search to explore others")

    # ── Graph visualization ───────────────────────────────────────────────────
    if claim_id_to_render:
        with st.spinner("Rendering graph..."):
            html = viz.build_claim_neighborhood(claim_id_to_render, driver)
        components.html(html, height=600)

        # ── Legend ───────────────────────────────────────────────────────────
        st.markdown("**Node legend:**")
        legend_items = [
            ("#4a90d9", "Patient"),
            ("#5ba55b", "Visit"),
            ("#888888", "Claim (clean)"),
            ("#e08c2a", "Claim (flawed)"),
            ("#9b59b6", "Provider"),
            ("#2eacb0", "Payer"),
            ("#f39c12", "Authorization"),
            ("#e74c3c", "ReferralOrder"),
            ("#95a5a6", "CPT Code"),
            ("#a02828", "Finding"),
            ("#4a3b7a", "DetectionRule"),
        ]
        cols = st.columns(6)
        for i, (color, label) in enumerate(legend_items):
            with cols[i % 6]:
                st.markdown(
                    f'<span style="display:inline-block;width:12px;height:12px;'
                    f'background:{color};border-radius:50%;margin-right:4px"></span>'
                    f'<span style="font-size:0.8rem">{label}</span>',
                    unsafe_allow_html=True,
                )
