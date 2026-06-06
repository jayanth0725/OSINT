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


# ─────────────────────────────────────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────────────────────────────────────

def _section_header(title: str, icon: str = "") -> None:
    st.markdown(
        f'<div style="margin:18px 0 8px 0;padding:8px 14px;background:#141922;'
        f'border-left:3px solid #1f6feb;border-radius:0 8px 8px 0">'
        f'<span style="color:#f2f4f8;font-weight:700;font-size:14px">{icon}&nbsp;{title}</span></div>',
        unsafe_allow_html=True,
    )


def _row(label: str, value: Any) -> None:
    """Render a single metadata key-value row; skip if value is empty."""
    if value is None or value == "" or value == [] or value == {}:
        return
    # Format lists nicely
    if isinstance(value, list):
        display = ", ".join(str(v) for v in value)
    elif isinstance(value, dict):
        display = json.dumps(value, default=str)
    else:
        display = str(value)
    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown(
            f'<span style="color:#9aa4b2;font-size:12px;font-weight:600">{label}</span>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<span style="color:#f2f4f8;font-size:13px;word-break:break-all">{display}</span>',
            unsafe_allow_html=True,
        )


def _flag_badge(label: str, active: bool, severity: str = "warning") -> str:
    colors = {
        "warning": ("#c69026", "rgba(198,144,38,0.15)"),
        "error":   ("#d43f3a", "rgba(212,63,58,0.15)"),
        "info":    ("#1f6feb", "rgba(31,111,235,0.15)"),
    }
    color, bg = colors.get(severity, colors["info"])
    if not active:
        return ""
    return (
        f'<span style="background:{bg};color:{color};border:1px solid {color}44;'
        f'padding:3px 12px;border-radius:20px;font-size:12px;font-weight:700;margin:2px">{label}</span>'
    )


def _render_expanded_metadata(expanded: Dict[str, Any]) -> None:
    """Render the expanded metadata dict in organized sections."""

    # ── Analysis ──────────────────────────────────────────────────────────────
    _section_header("Analysis", "🔬")
    _row("ELA Score", expanded.get("ELA"))
    _row("Hidden Pixels", expanded.get("Hidden Pixels"))
    _row("ICC Profile Present", expanded.get("ICC"))
    _row("JPEG %", expanded.get("JPEG %"))

    # ── File Info ─────────────────────────────────────────────────────────────
    _section_header("File", "📁")
    _row("File", expanded.get("File"))
    _row("File Type", expanded.get("File Type"))
    _row("File Type Extension", expanded.get("File Type Extension"))
    _row("MIME Type", expanded.get("MIME Type"))

    # ── JFIF / EXIF basics ────────────────────────────────────────────────────
    _section_header("JFIF / EXIF", "🖼️")
    _row("Exif Byte Order", expanded.get("Exif Byte Order"))
    _row("Current IPTC Digest", expanded.get("Current IPTC Digest"))
    _row("Image Width", expanded.get("Image Width"))
    _row("Image Height", expanded.get("Image Height"))
    _row("Image Size", expanded.get("Image Size"))
    _row("Megapixels", expanded.get("Megapixels"))
    _row("Encoding Process", expanded.get("Encoding Process"))
    _row("Bits Per Sample", expanded.get("Bits Per Sample"))
    _row("Color Components", expanded.get("Color Components"))
    _row("Y Cb Cr Sub Sampling", expanded.get("Y Cb Cr Sub Sampling"))
    _row("JFIF", expanded.get("JFIF"))
    _row("JFIF Version", expanded.get("JFIF Version"))
    _row("EXIF", expanded.get("EXIF"))
    _row("Image Description", expanded.get("Image Description"))
    _row("Camera Model Name", expanded.get("Camera Model Name"))
    _row("Orientation", expanded.get("Orientation"))
    _row("X Resolution", expanded.get("X Resolution"))
    _row("Y Resolution", expanded.get("Y Resolution"))
    _row("Resolution Unit", expanded.get("Resolution Unit"))
    _row("Artist", expanded.get("Artist"))
    _row("Y Cb Cr Positioning", expanded.get("Y Cb Cr Positioning"))
    _row("Copyright", expanded.get("Copyright"))
    _row("Date/Time Created", expanded.get("Date/Time Created"))
    _row("Date/Time Original", expanded.get("Date/Time Original"))

    # ── ICC Profile ───────────────────────────────────────────────────────────
    _section_header("ICC Profile", "🎨")
    _row("ICC Profile Name", expanded.get("ICC_Profile"))
    _row("Profile CMM Type", expanded.get("Profile CMM Type"))
    _row("Profile Version", expanded.get("Profile Version"))
    _row("Profile Class", expanded.get("Profile Class"))
    _row("Color Space Data", expanded.get("Color Space Data"))
    _row("Profile Connection Space", expanded.get("Profile Connection Space"))
    _row("Profile Date Time", expanded.get("Profile Date Time"))
    _row("Profile File Signature", expanded.get("Profile File Signature"))
    _row("Primary Platform", expanded.get("Primary Platform"))
    _row("CMM Flags", expanded.get("CMM Flags"))
    _row("Device Manufacturer", expanded.get("Device Manufacturer"))
    _row("Device Model", expanded.get("Device Model"))
    _row("Device Attributes", expanded.get("Device Attributes"))
    _row("Rendering Intent", expanded.get("Rendering Intent"))
    _row("Connection Space Illuminant", expanded.get("Connection Space Illuminant"))
    _row("Profile Creator", expanded.get("Profile Creator"))
    _row("Profile ID", expanded.get("Profile ID"))
    _row("Profile Copyright", expanded.get("Profile Copyright"))
    _row("Profile Description", expanded.get("Profile Description"))
    _row("Media White Point", expanded.get("Media White Point"))
    _row("Media Black Point", expanded.get("Media Black Point"))
    _row("Red Tone Reproduction Curve", expanded.get("Red Tone Reproduction Curve"))
    _row("Green Tone Reproduction Curve", expanded.get("Green Tone Reproduction Curve"))
    _row("Blue Tone Reproduction Curve", expanded.get("Blue Tone Reproduction Curve"))
    _row("Red Matrix Column", expanded.get("Red Matrix Column"))
    _row("Green Matrix Column", expanded.get("Green Matrix Column"))
    _row("Blue Matrix Column", expanded.get("Blue Matrix Column"))

    # ── IPTC ──────────────────────────────────────────────────────────────────
    _section_header("IPTC", "📰")
    _row("IPTC", expanded.get("IPTC"))
    _row("Application Record Version", expanded.get("Application Record Version"))
    _row("Object Name", expanded.get("Object Name"))
    _row("Supplemental Categories", expanded.get("Supplemental Categories"))
    _row("Keywords", expanded.get("Keywords"))
    _row("Special Instructions", expanded.get("Special Instructions"))
    _row("Date Created", expanded.get("Date Created"))
    _row("Time Created", expanded.get("Time Created"))
    _row("By-line", expanded.get("By-line"))
    _row("By-line Title", expanded.get("By-line Title"))
    _row("City", expanded.get("City"))
    _row("Province-State", expanded.get("Province-State"))
    _row("Country-Primary Location Code", expanded.get("Country-Primary Location Code"))
    _row("Country-Primary Location Name", expanded.get("Country-Primary Location Name"))
    _row("Job Identifier", expanded.get("Job Identifier"))
    _row("Headline", expanded.get("Headline"))
    _row("Credit", expanded.get("Credit"))
    _row("Source", expanded.get("Source"))
    _row("Copyright Notice", expanded.get("Copyright Notice"))
    _row("Caption-Abstract", expanded.get("Caption-Abstract"))

    # ── XMP ───────────────────────────────────────────────────────────────────
    _section_header("XMP", "🏷️")
    _row("XMP", expanded.get("XMP"))
    _row("XMP Toolkit", expanded.get("XMP Toolkit"))
    _row("Creator", expanded.get("Creator"))
    _row("Description", expanded.get("Description"))
    _row("Rights", expanded.get("Rights"))
    _row("Title", expanded.get("Title"))
    _row("Authors Position", expanded.get("Authors Position"))
    _row("Marked", expanded.get("Marked"))
    _row("Composite", expanded.get("Composite"))

    # ── Emails ────────────────────────────────────────────────────────────────
    emails = expanded.get("Emails")
    if emails:
        _section_header("Email Addresses Found", "📧")
        for addr in (emails if isinstance(emails, list) else [emails]):
            st.markdown(
                f'<span style="background:rgba(31,111,235,0.15);color:#1f6feb;border:1px solid #1f6feb44;'
                f'padding:3px 12px;border-radius:20px;font-size:13px;font-family:monospace">{addr}</span>',
                unsafe_allow_html=True,
            )
        st.markdown("")  # spacing


def _render_result(entry: Dict[str, Any]) -> None:
    """Render a single file result inside its expander."""
    filename = entry.get("filename", "Unknown")
    result = entry.get("result", {})
    flags = result.get("flags", {})
    data = result.get("data", {})
    expanded = data.get("expanded_metadata", {})
    file_type = result.get("file_type", "unknown")

    # Header badges
    badges_html = " ".join(filter(None, [
        _flag_badge("📍 GPS Exposed", flags.get("gps_flag", False), "error"),
        _flag_badge("👤 Identity Metadata", flags.get("identity_flag", False), "warning"),
        _flag_badge("❌ Error", not result.get("success", True), "error"),
    ]))
    if badges_html:
        st.markdown(f'<div style="margin-bottom:10px">{badges_html}</div>', unsafe_allow_html=True)

    # GPS map
    if flags.get("gps_flag"):
        lat = data.get("gps_latitude")
        lon = data.get("gps_longitude")
        if lat is not None and lon is not None:
            st.warning(f"📍 GPS coordinates: {lat}, {lon}")
            st.map([{"lat": lat, "lon": lon}])

    if not result.get("success"):
        st.error(f"Extraction error: {result.get('error')}")
        return

    # Tabs: Structured | Raw JSON
    tab_struct, tab_raw = st.tabs(["📊 Structured View", "📄 Raw JSON"])

    with tab_struct:
        # Core file-level fields
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("File Type", file_type.upper())
        with col2:
            st.metric("Width", str(expanded.get("Image Width") or data.get("image_width") or "—"))
        with col3:
            st.metric("Height", str(expanded.get("Image Height") or data.get("image_height") or "—"))

        # Hashes
        hashes = data.get("hashes", {})
        if hashes:
            _section_header("File Hashes", "🔒")
            _row("MD5", hashes.get("md5"))
            _row("SHA-256", hashes.get("sha256"))

        # All the metadata sections
        _render_expanded_metadata(expanded)

        # PDF / Video specific
        if file_type == "pdf":
            _section_header("PDF Metadata", "📄")
            _row("Author", data.get("author"))
            _row("Creator", data.get("creator"))
            _row("Producer", data.get("producer"))
            _row("Creation Date", data.get("creation_date"))
            _row("Modification Date", data.get("modification_date"))
            _row("Subject", data.get("subject"))
            _row("Keywords", data.get("keywords"))
            _row("Page Count", data.get("page_count"))
            _row("Encrypted", data.get("encrypted"))

        elif file_type == "video":
            _section_header("Video Metadata", "🎬")
            _row("Duration (s)", data.get("duration"))
            _row("Bitrate", data.get("bitrate"))
            _row("Codec", data.get("codec"))
            _row("Resolution", data.get("resolution"))
            _row("Frame Rate", data.get("frame_rate"))
            _row("Creation Time", data.get("creation_time"))

        elif file_type == "image":
            _section_header("Image Core Fields", "📷")
            _row("Camera Make", data.get("camera_make"))
            _row("Camera Model", data.get("camera_model"))
            _row("DateTime", data.get("datetime"))
            _row("Software", data.get("software"))
            _row("Author", data.get("author"))
            _row("Orientation", data.get("orientation"))

    with tab_raw:
        st.json(result)


# ─────────────────────────────────────────────────────────────────────────────
# Page bootstrap
# ─────────────────────────────────────────────────────────────────────────────

css = _load_css("assets/style.css")
st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

_init_state()

st.title("🔍 Metadata Extraction Toolkit")
st.markdown(
    '<span style="color:#9aa4b2;font-size:14px">Upload images, PDFs, or videos to extract '
    'comprehensive metadata including EXIF, IPTC, XMP, ICC profiles, ELA scores, and more.</span>',
    unsafe_allow_html=True,
)

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

        with st.spinner(f"Extracting metadata from {upload.name}…"):
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
        file_type = result.get("file_type", "unknown")
        success_icon = "✅" if result.get("success") else "❌"

        with st.expander(f"{success_icon} {filename} — {file_type.upper()}", expanded=True):
            _render_result(entry)

    # ── Summary table ──────────────────────────────────────────────────────
    st.subheader("Summary")
    summary_rows = []
    for entry in results:
        result = entry.get("result", {})
        exp = result.get("data", {}).get("expanded_metadata", {})
        summary_rows.append({
            "Filename": entry.get("filename"),
            "Type": result.get("file_type", "—").upper(),
            "Size": f"{exp.get('Image Width') or '?'} × {exp.get('Image Height') or '?'}",
            "GPS": "⚠️ Yes" if result.get("flags", {}).get("gps_flag") else "No",
            "Identity": "⚠️ Yes" if result.get("flags", {}).get("identity_flag") else "No",
            "ELA": str(exp.get("ELA") or "—"),
            "Emails": ", ".join(exp.get("Emails") or []) or "—",
            "Success": "✅" if result.get("success") else "❌",
        })
    st.dataframe(summary_rows, use_container_width=True)

download_payload = json.dumps(results or [], indent=2, default=str)
st.download_button(
    "⬇️ Download Results JSON",
    data=download_payload,
    file_name="metadata_results.json",
    mime="application/json",
    disabled=not bool(results),
)

if results and st.button("🗑️ Clear Results"):
    st.session_state["metadata_results"] = []
    st.session_state["metadata_processed"] = set()
    st.rerun()
