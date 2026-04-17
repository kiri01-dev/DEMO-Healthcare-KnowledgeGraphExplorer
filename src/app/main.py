"""
main.py — Streamlit entry point for the KG Data Quality Demo.

Run:
    streamlit run src/app/main.py
"""

import sys
import os

# Ensure src/ is on the path so `from app.X` and `from graph.X` resolve
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# --- Page config (must be first Streamlit call) ---
st.set_page_config(
    page_title="KG Data Quality Demo",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app.styles import inject_css
from graph.connection import get_driver, check_connection
import app.panel_ontology  as panel_ontology
import app.panel_rules     as panel_rules
import app.panel_foundation as panel_foundation
import app.panel_loader    as panel_loader
import app.panel_findings  as panel_findings

inject_css()

PANELS = [
    "Ontology Explorer",
    "Rule Library",
    "KG Foundation",
    "Scenario Loader",
    "Findings Dashboard",
]

# ---------------------------------------------------------------------------
# Neo4j connection (cached)
# ---------------------------------------------------------------------------

@st.cache_resource
def _get_driver():
    return get_driver()


driver = _get_driver()
connected = check_connection(driver)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🔬 KG DQ Demo")
    st.markdown("*xVector — Healthcare RCM*")
    st.divider()

    # Connection status
    if connected:
        st.markdown("🟢 **Neo4j Connected**")
    else:
        st.markdown("🔴 **Neo4j Disconnected**")
        st.error("Cannot reach Neo4j.\nCheck `.env` and restart Neo4j.")

    # Live open finding count
    if connected:
        try:
            with driver.session() as _s:
                _count = _s.run(
                    "MATCH (f:Finding {status:'open'}) RETURN count(f) AS n"
                ).single()["n"]
        except Exception:
            _count = 0

        if _count == 0:
            st.metric("Open Findings", "0")
        else:
            st.markdown(
                f'<div class="finding-badge">⚠ {_count} open findings</div>',
                unsafe_allow_html=True,
            )
            st.markdown("")

    st.divider()

    panel = st.radio("Navigate", PANELS, label_visibility="collapsed")

# ---------------------------------------------------------------------------
# Panel routing
# ---------------------------------------------------------------------------

if not connected:
    st.error("## Neo4j is not reachable\n\nPlease start Neo4j and refresh the page.")
    st.stop()

if panel == "Ontology Explorer":
    panel_ontology.render(driver)
elif panel == "Rule Library":
    panel_rules.render(driver)
elif panel == "KG Foundation":
    panel_foundation.render(driver)
elif panel == "Scenario Loader":
    panel_loader.render(driver)
elif panel == "Findings Dashboard":
    panel_findings.render(driver)
