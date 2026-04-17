"""
panel_findings.py — Panel 5: Findings Dashboard.

Reads findings from Neo4j (not session state). All lifecycle actions
write directly back to the graph. The graph is the system of record.
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from neo4j import Driver
from graph import viz, findings as findings_module


SCENARIO_NARRATIVES = {
    "S-01": {
        "title":   "Unverifiable Prior Authorization Chain",
        "flaw":    "The HAS_AUTHORIZATION relationship was severed, the AUTH_FOR_PROCEDURE "
                   "points to a different CPT, or the authorization expired before the claim date.",
        "why_missed": "Standard claim edits check for the presence of an auth number in the claim "
                       "header. They cannot traverse the authorization graph to verify the chain is intact.",
        "how_detected": "The detection rule traverses: Claim → BILLED_PROCEDURE → CPT (requires_auth=true), "
                         "then checks for a valid HAS_AUTHORIZATION → AUTH_FOR_PROCEDURE path to the same CPT "
                         "with a non-expired expiry_date.",
        "rule":    "DR-S01",
    },
    "S-02": {
        "title":   "Rendering Provider Not Credentialed with Billed Payer",
        "flaw":    "The rendering NPI on the claim has no active CONTRACTED_WITH → CONTRACT_WITH_PAYER "
                   "path to the payer in SUBMITTED_TO.",
        "why_missed": "Credentialing checks in clearinghouses look up provider tables by NPI. "
                       "They don't traverse the contract graph to verify the specific payer relationship.",
        "how_detected": "The rule checks: Claim (BILLED_BY rendering) → Provider. Then verifies "
                          "Provider has CONTRACTED_WITH → Contract → CONTRACT_WITH_PAYER → same Payer.",
        "rule":    "DR-S02",
    },
    "S-03": {
        "title":   "Claim Resolved Against Superseded Contract Version",
        "flaw":    "The provider's CONTRACTED_WITH edge points to a v1 Contract that has a "
                   "SUPERSEDED_BY edge to a newer v2. Payment was calculated using v1 rates.",
        "why_missed": "Most systems store contract version as a field on the claim. "
                       "The relationship between contract versions is not modeled — "
                       "so supersession is invisible.",
        "how_detected": "The rule finds: Provider CONTRACTED_WITH → Contract, then checks "
                          "for a SUPERSEDED_BY edge leading to a newer version. If found, the "
                          "claim was resolved against a stale contract.",
        "rule":    "DR-S03",
    },
    "S-04": {
        "title":   "Authorization Unit Exhaustion Across Claims",
        "flaw":    "Multiple claims linked to the same authorization have billed units "
                   "that cumulatively exceed the approved_units on the Authorization node.",
        "why_missed": "Claim-level edits check units on a single claim. "
                       "Cross-claim aggregation against a shared authorization requires "
                       "a graph traversal that flat-file systems cannot perform.",
        "how_detected": "The rule aggregates: SUM(BILLED_PROCEDURE.units) across all Claims "
                          "sharing HAS_AUTHORIZATION → same Authorization. Fires when sum > approved_units.",
        "rule":    "DR-S04",
    },
    "S-05": {
        "title":   "Duplicate Patient Identity Across Source Systems",
        "flaw":    "A duplicate Patient node exists with a name variation and transposed DOB, "
                   "sharing the same Provider and Payer as the canonical record.",
        "why_missed": "MPI (Master Patient Index) matching works on demographic fields in isolation. "
                       "Graph proximity — same provider, same payer, same zip — is not considered.",
        "how_detected": "The rule finds Patient pairs with matching zip + near-matching DOB that "
                          "share a Provider and Payer via claim traversal, then flags both.",
        "rule":    "DR-S05",
    },
    "S-06": {
        "title":   "Invalid HMO Referral Chain",
        "flaw":    "An HMO specialist claim is missing a referral, has a referral dated after "
                   "the visit, or was referred by a non-PCP specialist.",
        "why_missed": "Referral validation in pre-bill edits checks for a referral number in "
                       "the claim header. It cannot verify: referral date sequence, PCP credential, "
                       "or referral-to-provider match.",
        "how_detected": "The rule traverses: Claim (HMO coverage) → HAS_REFERRAL → ReferralOrder "
                          "→ REFERRED_BY → Provider (must be PCP specialty, date must precede visit).",
        "rule":    "DR-S06",
    },
}


def _render_scorecard(driver: Driver) -> None:
    summary = findings_module.get_finding_summary(driver)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open",         summary["open"])
    c2.metric("Acknowledged", summary["acknowledged"])
    c3.metric("Resolved",     summary["resolved"])
    c4.metric("Total Risk ($)", f"${summary['total_risk']:,.0f}",
              help="Illustrative — sum of estimated_risk_amount on open findings")

    by_sev = summary.get("by_severity", {})
    if by_sev:
        sev_cols = st.columns(3)
        sev_cols[0].metric("🔴 HIGH",   by_sev.get("HIGH", 0))
        sev_cols[1].metric("🟠 MEDIUM", by_sev.get("MEDIUM", 0))
        sev_cols[2].metric("🟢 LOW",    by_sev.get("LOW", 0))


def render(driver: Driver) -> None:
    st.title("Findings Dashboard")
    st.markdown(
        "_The graph found these before a single claim was worked. "
        "Every finding is in the graph — trackable, assignable, auditable over time._"
    )

    # ── Scorecard ─────────────────────────────────────────────────────────────
    st.subheader("Summary")
    _render_scorecard(driver)

    st.divider()

    # ── Findings table ────────────────────────────────────────────────────────
    st.subheader("Findings")

    filter_cols = st.columns([2, 2, 1])
    with filter_cols[0]:
        status_filter = st.selectbox(
            "Status filter", ["open", "acknowledged", "resolved", "all"],
            index=0
        )
    with filter_cols[1]:
        scenario_filter = st.selectbox(
            "Scenario filter",
            ["all", "S-01", "S-02", "S-03", "S-04", "S-05", "S-06"],
            index=0
        )

    status_arg   = None if status_filter   == "all" else status_filter
    scenario_arg = None if scenario_filter == "all" else scenario_filter

    all_findings = findings_module.list_findings(
        driver, status=status_arg, scenario=scenario_arg
    )

    if not all_findings:
        st.info("No findings match the current filter. Inject a scenario from Panel 4 first.")
        return

    # Build DataFrame for display
    display_cols = ["finding_id", "claim_id", "patient_id", "rule_id",
                    "rule_name", "severity", "status", "detected_at", "scenario"]
    df = pd.DataFrame(all_findings)[display_cols]

    st.dataframe(df, use_container_width=True, hide_index=True,
                 height=min(400, 50 + 35 * len(df)))

    st.divider()

    # ── Row selection for detail view ─────────────────────────────────────────
    st.subheader("Finding Detail")
    finding_ids = [f["finding_id"] for f in all_findings]
    selected_fid = st.selectbox("Select a finding to inspect", finding_ids)

    if not selected_fid:
        return

    finding = findings_module.get_finding(driver, selected_fid)
    if not finding:
        st.warning("Finding not found.")
        return

    # Lifecycle buttons + resolution note
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 4])
    with btn_col1:
        if finding["status"] == "open":
            if st.button("👁 Acknowledge"):
                findings_module.acknowledge_finding(selected_fid, driver)
                st.rerun()
    with btn_col2:
        if finding["status"] in ("open", "acknowledged"):
            if st.button("✅ Resolve"):
                note = st.session_state.get(f"resolve_note_{selected_fid}", "")
                findings_module.resolve_finding(selected_fid, driver, note=note)
                st.rerun()

    if finding["status"] in ("open", "acknowledged"):
        note_key = f"resolve_note_{selected_fid}"
        st.text_area(
            "Resolution note *(written to graph on Resolve)*",
            key=note_key,
            placeholder="e.g. Contacted provider — resubmitting with correct auth number. Routed to billing team.",
            height=80,
        )
    elif finding.get("resolution_note"):
        st.markdown(
            f'<div style="background:#f0f4f0;border-left:3px solid #27ae60;'
            f'padding:8px 12px;border-radius:4px;margin-bottom:8px">'
            f'📝 <b>Resolution note:</b> {finding["resolution_note"]}</div>',
            unsafe_allow_html=True,
        )

    # Finding metadata
    meta_col1, meta_col2 = st.columns(2)
    with meta_col1:
        st.markdown(f"**Finding ID:** `{finding['finding_id']}`")
        st.markdown(f"**Claim ID:** `{finding['claim_id']}`")
        st.markdown(f"**Patient ID:** `{finding['patient_id']}`")
        st.markdown(f"**Rule:** {finding['rule_id']} — {finding['rule_name']}")
    with meta_col2:
        sev_colors = {"HIGH": "#c0392b", "MEDIUM": "#e67e22", "LOW": "#27ae60"}
        sev = finding.get("severity", "")
        st.markdown(
            f'**Severity:** <span style="color:{sev_colors.get(sev,"#666")};font-weight:bold">{sev}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**Status:** `{finding['status']}`")
        st.markdown(f"**Detected:** {finding.get('detected_at', '')}")
        if finding.get("estimated_risk_amount"):
            st.markdown(f"**Est. Risk:** ${float(finding['estimated_risk_amount']):,.2f} *(illustrative)*")
    st.markdown(f"**Description:** {finding.get('description', '')}")

    st.divider()

    # ── Diagnostic detail table ───────────────────────────────────────────────
    st.subheader("Diagnostic Detail")
    diag = findings_module.get_finding_diagnostics(selected_fid, driver)
    rows = diag.get("rows", [])

    if rows:
        STATUS_ICON = {"pass": "✅", "fail": "❌", "warn": "⚠️", "info": "ℹ️"}
        STATUS_COLOR = {"pass": "#27ae60", "fail": "#c0392b", "warn": "#e67e22", "info": "#555"}

        for row in rows:
            s = row.get("status", "info")
            icon = STATUS_ICON.get(s, "")
            color = STATUS_COLOR.get(s, "#555")
            expected = row.get("expected", "")

            cols = st.columns([2, 3, 3, 0.5])
            cols[0].markdown(f"**{row['label']}**")
            cols[1].markdown(f"`{row['actual']}`")
            if expected:
                cols[2].markdown(f"<span style='color:{color};font-size:0.85rem'>Expected: {expected}</span>",
                                unsafe_allow_html=True)
            cols[3].markdown(f"<span style='font-size:1.1rem'>{icon}</span>",
                            unsafe_allow_html=True)
    else:
        st.caption("No diagnostic detail available for this finding.")

    st.divider()

    # ── Split-pane subgraph ───────────────────────────────────────────────────
    st.subheader("Graph View")
    claim_id = finding["claim_id"]
    scenario = finding.get("scenario", "S-01")

    pane_left, pane_right = st.columns(2)

    with pane_left:
        st.caption("🔴 Actual graph (with flaw)")
        with st.spinner("Loading actual subgraph..."):
            html_actual = viz.build_actual_subgraph(claim_id, driver)
        components.html(html_actual, height=400)

    with pane_right:
        st.caption("✅ Expected path (clean ontology)")
        with st.spinner("Loading expected subgraph..."):
            html_expected = viz.build_expected_subgraph(scenario, driver)
        components.html(html_expected, height=400)

    st.divider()

    # ── Scenario narrative ────────────────────────────────────────────────────
    narrative = SCENARIO_NARRATIVES.get(scenario)
    if narrative:
        with st.expander(f"📖 Scenario Narrative: {narrative['title']}", expanded=False):
            st.markdown(f"**What the flaw is:**\n{narrative['flaw']}")
            st.markdown(f"**Why standard tools miss it:**\n{narrative['why_missed']}")
            st.markdown(f"**How the graph detected it:**\n{narrative['how_detected']}")
            st.markdown(
                f"**DetectionRule fired:** `{narrative['rule']}`"
            )
