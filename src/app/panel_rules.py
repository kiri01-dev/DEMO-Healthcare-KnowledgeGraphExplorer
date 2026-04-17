"""
panel_rules.py — Panel 2: Rule Library.

Shows all DetectionRule nodes with live finding counts.
"""

import streamlit as st
from neo4j import Driver


CATEGORY_COLORS = {
    "prior_authorization": "#e74c3c",
    "credentialing":       "#9b59b6",
    "contract":            "#f39c12",
    "authorization_units": "#e67e22",
    "entity_integrity":    "#3498db",
    "referral":            "#1abc9c",
}

SEVERITY_COLORS = {
    "HIGH":   "#c0392b",
    "MEDIUM": "#e67e22",
    "LOW":    "#27ae60",
}


def _get_rules(driver: Driver) -> list:
    with driver.session() as session:
        return session.run("""
            MATCH (r:DetectionRule)
            RETURN r.rule_id    AS rule_id,
                   r.name       AS name,
                   r.category   AS category,
                   r.severity   AS severity,
                   r.description AS description,
                   r.cypher     AS cypher,
                   r.version    AS version,
                   r.applies_to AS applies_to
            ORDER BY r.rule_id
        """).data()


def _get_finding_count(rule_id: str, driver: Driver) -> int:
    with driver.session() as session:
        return session.run(
            "MATCH (f:Finding)-[:TRIGGERED_BY]->(r:DetectionRule {rule_id:$id}) "
            "RETURN count(f) AS n",
            id=rule_id
        ).single()["n"]


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:10px;font-size:0.8rem;font-weight:600">{text}</span>'
    )


def render(driver: Driver) -> None:
    st.title("Rule Library")
    st.markdown(
        "_Here are the detection rules configured for this context. "
        "Each one is a named, versioned graph traversal._"
    )

    rules = _get_rules(driver)

    if not rules:
        st.warning("No DetectionRule nodes found. Run `python scripts/setup.py` first.")
        return

    # Category filter
    all_cats = sorted({r["category"] for r in rules if r["category"]})
    selected_cats = st.multiselect(
        "Filter by category", all_cats, default=all_cats,
        help="Show only rules in selected categories"
    )

    st.divider()

    shown = 0
    for rule in rules:
        if rule["category"] not in selected_cats:
            continue

        shown += 1
        finding_count = _get_finding_count(rule["rule_id"], driver)

        cat_color  = CATEGORY_COLORS.get(rule["category"], "#666")
        sev_color  = SEVERITY_COLORS.get(rule["severity"],  "#666")

        header_cols = st.columns([3, 1])
        with header_cols[0]:
            st.markdown(
                f'<span style="font-size:1.1rem;font-weight:700">'
                f'{rule["rule_id"]}</span>&nbsp;&nbsp;'
                + _badge(rule["category"], cat_color)
                + "&nbsp;"
                + _badge(rule["severity"], sev_color),
                unsafe_allow_html=True,
            )
        with header_cols[1]:
            if finding_count == 0:
                st.metric("Findings", "0")
            else:
                st.markdown(
                    f'<div style="text-align:right">'
                    f'<span style="background:#a02828;color:white;padding:4px 12px;'
                    f'border-radius:12px;font-weight:bold;font-size:1.1rem">'
                    f'⚠ {finding_count}</span></div>',
                    unsafe_allow_html=True,
                )

        with st.expander(f"**{rule['name']}**", expanded=True):
            st.markdown(rule.get("description", "No description available."))

            detail_cols = st.columns(2)
            with detail_cols[0]:
                if rule.get("version"):
                    st.caption(f"Version: {rule['version']}")
                if rule.get("applies_to"):
                    st.caption(f"Applies to: {rule['applies_to']}")

            with detail_cols[1]:
                if rule.get("cypher"):
                    with st.expander("View detection Cypher"):
                        st.code(rule["cypher"], language="cypher")

        st.markdown("---")

    if shown == 0:
        st.info("No rules match the selected categories.")

    # Static production callout
    st.info(
        "💡 **In production,** this library grows with the client's payer mix and denial history. "
        "New rules are added without code changes. Rules are versioned as payer policies evolve."
    )
