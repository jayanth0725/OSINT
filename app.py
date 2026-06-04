from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

import streamlit as st


st.set_page_config(page_title="OSINT Investigator", layout="wide", page_icon="🔍")


@st.cache_data
def _load_css(path: str) -> str:
    """Load CSS from the assets folder."""
    with open(path, "r", encoding="utf-8") as file_handle:
        return file_handle.read()


def _init_case_log() -> None:
    """Initialize session state for case logging."""
    if "case_log" not in st.session_state:
        st.session_state["case_log"] = []


def _is_threat(entry: Dict[str, Any]) -> bool:
    """Detect whether a case log entry indicates a potential threat."""
    result = entry.get("result", {})
    flags = result.get("flags") or {}
    risk_level = result.get("risk_level")
    if risk_level in {"HIGH", "CRITICAL"}:
        return True
    if flags.get("gps_flag") or flags.get("identity_flag"):
        return True
    vt = result.get("vt_result") or {}
    if vt.get("malicious", 0) > 0:
        return True
    return False


def _count_profiles(case_log: List[Dict[str, Any]]) -> int:
    """Count social profiles searched within the case log."""
    count = 0
    for entry in case_log:
        module = str(entry.get("module", "")).lower()
        if "social" in module or "username" in module:
            count += 1
    return count


css = _load_css("assets/style.css")
st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

_init_case_log()
case_log: List[Dict[str, Any]] = st.session_state["case_log"]

st.title("OSINT Investigator Platform")
st.write("Unified cybersecurity investigation toolkit for metadata, QR, and social intelligence.")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Analyses Run", len(case_log))
with col2:
    threats_detected = sum(1 for entry in case_log if _is_threat(entry))
    st.metric("Threats Detected", threats_detected)
with col3:
    st.metric("Profiles Searched", _count_profiles(case_log))

if case_log:
    st.subheader("Case Log")
    st.dataframe(case_log, width="stretch")

if st.button("Clear Session"):
    st.session_state["case_log"] = []
    st.success("Session cleared.")
