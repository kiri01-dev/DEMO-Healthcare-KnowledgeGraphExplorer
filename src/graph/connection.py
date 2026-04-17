"""
connection.py — Neo4j driver singleton and health check.

All other modules import get_driver() from here.
Never create a separate driver instance in another module.
"""

import os
from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, AuthError

load_dotenv()

_driver: Driver | None = None


def _get_secret(key: str, default: str = "") -> str:
    """Read from Streamlit secrets if available, else fall back to env vars."""
    try:
        import streamlit as st
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def get_driver() -> Driver:
    """Return a cached Neo4j driver. Creates on first call."""
    global _driver
    if _driver is None:
        uri      = _get_secret("NEO4J_URI",      "bolt://localhost:7687")
        user     = _get_secret("NEO4J_USER",     "neo4j")
        password = _get_secret("NEO4J_PASSWORD", "")
        _driver = GraphDatabase.driver(uri, auth=(user, password))
    return _driver


def check_connection(driver: Driver) -> bool:
    """Return True if Neo4j is reachable and credentials are valid."""
    try:
        driver.verify_connectivity()
        return True
    except (ServiceUnavailable, AuthError, Exception):
        return False


def close_driver():
    """Close the cached driver. Call on application shutdown."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def get_connection_info() -> dict:
    """Return connection parameters (no password)."""
    return {
        "uri":  _get_secret("NEO4J_URI",  "bolt://localhost:7687"),
        "user": _get_secret("NEO4J_USER", "neo4j"),
    }
