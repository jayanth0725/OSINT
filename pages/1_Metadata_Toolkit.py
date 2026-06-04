from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import streamlit as st

from modules.metadata import extract_metadata


@st.cache_data
def _load_css(path: str) -> str:
    """Load CSS from disk for theming."""
    with open(path, "r", encoding="utf-8") as file_handle:
        return file_handle.read()


@st.cache_data
def _cached_extract_metadata(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Cached wrapper around metadata extraction."""
    return extract_metadata(file_bytes, filename)


def _init_state() -> None:
    """Initialize session state keys used by the metadata page."""
    if "case_log" not in st.session_state:
        st.session_state["case_log"] = []
    if "metadata_results" not in st.session_state:
        st.session_state["metadata_results"] = []
    if "metadata_processed" not in st.session_state:
        st.session_state["metadata_processed"] = set()


def _fingerprint(content: bytes, filename: str) -> str:
    """Create a stable hash for uploaded files."""
    digest = hashlib.sha256(content + filename.encode("utf-8")).hexdigest()
    return digest


css = _load_css("assets/style.css")
st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

_init_state()

st.title("Metadata Extraction Toolkit")

uploads = st.file_uploader(
    "Upload files for metadata extraction",
    type=["jpg", "jpeg", "png", "tiff", "webp", "pdf", "mp4", "mov", "avi", "mkv"],
    accept_multiple_files=True,
)

results: List[Dict[str, Any]] = []
if uploads:
    for upload in uploads:
        file_bytes = upload.read()
        file_id = _fingerprint(file_bytes, upload.name)
        if file_id in st.session_state["metadata_processed"]:
            continue

        result = _cached_extract_metadata(file_bytes, upload.name)
        result_record = {
            "module": "Metadata Toolkit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "filename": upload.name,
            "result": result,
        }
        st.session_state["metadata_processed"].add(file_id)
        st.session_state["metadata_results"].append(result_record)
        st.session_state["case_log"].append(result_record)

    results = st.session_state["metadata_results"]

if results:
    for entry in results:
        filename = entry.get("filename", "Unknown")
        result = entry.get("result", {})
        flags = result.get("flags", {})
        data = result.get("data", {})
        with st.expander(f"{filename} ({result.get('file_type')})", expanded=False):
            st.json(result)
            if flags.get("gps_flag"):
                st.warning("GPS coordinates found - location may be exposed")
                if data.get("gps_latitude") is not None and data.get("gps_longitude") is not None:
                    st.map(
                        [{"lat": data.get("gps_latitude"), "lon": data.get("gps_longitude")}]
                    )
            if flags.get("identity_flag"):
                st.warning("Identity metadata found")

    summary_rows = []
    for entry in results:
        result = entry.get("result", {})
        summary_rows.append(
            {
                "filename": entry.get("filename"),
                "file_type": result.get("file_type"),
                "gps_flag": result.get("flags", {}).get("gps_flag"),
                "identity_flag": result.get("flags", {}).get("identity_flag"),
                "success": result.get("success"),
            }
        )
    st.subheader("Summary")
    st.dataframe(summary_rows, width="stretch")

download_payload = json.dumps(results or [], indent=2)
st.download_button(
    "Download Results JSON",
    data=download_payload,
    file_name="metadata_results.json",
    mime="application/json",
    disabled=not bool(results),
)
