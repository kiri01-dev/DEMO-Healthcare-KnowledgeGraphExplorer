"""
panel_ontology.py — Panel 1: Ontology Explorer.

Shows the schema diagram, node type inventory, and relationship counts.
"""

import streamlit as st
import streamlit.components.v1 as components
from neo4j import Driver
from graph import viz


NODE_PROPERTIES = {
    "Patient":       ["patient_id", "first_name", "last_name", "dob", "sex", "zip"],
    "Visit":         ["visit_id", "visit_date", "place_of_service", "visit_type"],
    "Claim":         ["claim_id", "claim_date", "billed_amount", "claim_status", "is_flawed", "flaw_scenario"],
    "CPT_Code":      ["code", "description", "category", "requires_auth"],
    "ICD10_Code":    ["code", "description", "category"],
    "Payer":         ["payer_id", "payer_name", "payer_type"],
    "PayerPolicy":   ["policy_id", "effective_date", "termination_date", "plan_type", "version"],
    "Coverage":      ["coverage_id", "start_date", "end_date", "member_id"],
    "Provider":      ["provider_id", "npi", "name", "specialty", "provider_type"],
    "Contract":      ["contract_id", "effective_date", "termination_date", "fee_schedule", "version_num"],
    "Authorization": ["auth_id", "auth_date", "approved_units", "expiry_date", "auth_status"],
    "ReferralOrder": ["referral_id", "order_date", "referring_provider_id"],
    "DetectionRule": ["rule_id", "name", "category", "severity", "risk_type", "active"],
    "Finding":       ["finding_id", "detected_at", "severity", "status", "description", "estimated_risk_amount"],
}

RELATIONSHIP_TYPES = [
    "HAD_VISIT", "GENERATED_CLAIM", "BILLED_PROCEDURE", "CODED_DIAGNOSIS",
    "SUBMITTED_TO", "BILLED_BY", "COVERED_UNDER", "HAS_POLICY", "COVERED_BY",
    "ENROLLED_IN", "COVERS_PROCEDURE", "CONTRACTED_WITH", "CONTRACT_WITH_PAYER",
    "HAS_AUTHORIZATION", "AUTH_GRANTED_BY", "AUTH_FOR_PROCEDURE",
    "HAS_REFERRAL", "REFERRED_BY", "SUPERSEDED_BY", "POLICY_SUPERSEDED_BY",
    "HAS_FINDING", "TRIGGERED_BY",
]


def _get_node_counts(driver: Driver) -> dict:
    with driver.session() as session:
        rows = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt"
        ).data()
    return {r["label"]: r["cnt"] for r in rows if r["label"]}


def _get_rel_counts(driver: Driver) -> dict:
    with driver.session() as session:
        rows = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS cnt"
        ).data()
    return {r["rel_type"]: r["cnt"] for r in rows}


def render(driver: Driver) -> None:
    st.title("Ontology Explorer")
    st.markdown(
        "_Here is the semantic model of your revenue cycle — "
        "every entity and relationship that governs how a clean claim looks._"
    )

    # --- Schema diagram ---
    st.subheader("Schema Diagram")
    with st.spinner("Rendering schema..."):
        html = viz.build_ontology_diagram()
    components.html(html, height=500)

    st.divider()

    # --- Node inventory ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Node Types")
        node_counts = _get_node_counts(driver)

        rows = []
        for label, props in NODE_PROPERTIES.items():
            rows.append({
                "Label": label,
                "Properties": len(props),
                "Instances": node_counts.get(label, 0),
            })

        import pandas as pd
        df = pd.DataFrame(rows).sort_values("Instances", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)

    with col2:
        st.subheader("Relationship Types")
        rel_counts = _get_rel_counts(driver)

        rel_rows = []
        for rel in RELATIONSHIP_TYPES:
            rel_rows.append({
                "Relationship": rel,
                "Count": rel_counts.get(rel, 0),
            })

        df_rel = pd.DataFrame(rel_rows).sort_values("Count", ascending=False)
        st.dataframe(df_rel, use_container_width=True, hide_index=True)

    st.divider()

    # --- Node type detail ---
    st.subheader("Node Type Detail")
    selected_label = st.selectbox("Select a node type", list(NODE_PROPERTIES.keys()))

    if selected_label:
        props = NODE_PROPERTIES[selected_label]
        count = node_counts.get(selected_label, 0)

        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Instance count", f"{count:,}")
            st.markdown(f"**Properties ({len(props)}):**")
            for p in props:
                st.markdown(f"- `{p}`")

        with c2:
            st.markdown("**Sample values:**")
            try:
                with driver.session() as session:
                    sample = session.run(
                        f"MATCH (n:{selected_label}) RETURN n LIMIT 3"
                    ).data()
                for i, row in enumerate(sample):
                    node = dict(row["n"])
                    with st.expander(f"Sample {i + 1}"):
                        for k, v in node.items():
                            if v is not None:
                                st.text(f"{k}: {v}")
            except Exception as e:
                st.warning(f"Could not load sample: {e}")
