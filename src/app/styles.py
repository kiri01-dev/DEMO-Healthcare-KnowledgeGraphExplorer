"""
styles.py — xVector brand CSS for the KG DQ Demo.
"""

import streamlit as st

CUSTOM_CSS = """
<style>
/* ── Global ── */
html, body, [data-testid="stApp"] {
    background-color: #f7f5f0;
    font-family: system-ui, -apple-system, sans-serif;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #1a1a2e;
}
[data-testid="stSidebar"] * {
    color: #e8e8f0 !important;
}
[data-testid="stSidebar"] .stRadio label {
    color: #e8e8f0 !important;
}

/* ── Buttons ── */
.stButton > button {
    background-color: #b84a1f;
    color: white;
    border: none;
    border-radius: 4px;
    font-weight: 600;
}
.stButton > button:hover {
    background-color: #9a3d18;
    color: white;
}

/* ── Metrics ── */
[data-testid="stMetricValue"] {
    color: #1a1a2e;
    font-weight: 700;
}

/* ── Finding badge ── */
.finding-badge {
    background-color: #a02828;
    color: white;
    padding: 2px 10px;
    border-radius: 12px;
    font-weight: bold;
    font-size: 0.9rem;
}

/* ── Card / expander ── */
[data-testid="stExpander"] {
    border: 1px solid #ddd;
    border-radius: 6px;
    background: white;
}

/* ── Tables ── */
[data-testid="stDataFrame"] {
    border-radius: 6px;
}

/* ── Section headers ── */
h2 { color: #1a1a2e; }
h3 { color: #b84a1f; }
</style>
"""


def inject_css() -> None:
    """Inject xVector brand CSS into the Streamlit app."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
