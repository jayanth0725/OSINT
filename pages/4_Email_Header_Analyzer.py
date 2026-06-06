from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

import streamlit as st

from modules.email_analyzer import parse_email_headers


@st.cache_data
def _load_css(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _badge(label: str, value: str | None, ok_values=("pass",), warn_values=("softfail", "none"), fail_values=("fail",)) -> str:
    """Return an HTML badge colored by authentication result."""
    if value is None:
        return f'<span style="background:#243042;color:#9aa4b2;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600">{label}: N/A</span>'
    low = value.lower()
    if low in ok_values:
        color, bg = "#1f8b4c", "rgba(31,139,76,0.15)"
    elif low in warn_values:
        color, bg = "#c69026", "rgba(198,144,38,0.15)"
    elif low in fail_values:
        color, bg = "#d43f3a", "rgba(212,63,58,0.15)"
    else:
        color, bg = "#1f6feb", "rgba(31,111,235,0.15)"
    return (
        f'<span style="background:{bg};color:{color};border:1px solid {color}33;'
        f'padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700">'
        f'{label}: {value.upper()}</span>'
    )


def _row(label: str, value: Any) -> None:
    """Render a key-value metadata row."""
    if value is None or value == "":
        return
    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown(f'<span style="color:#9aa4b2;font-size:13px">{label}</span>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<span style="color:#f2f4f8;font-size:13px;word-break:break-all">{value}</span>', unsafe_allow_html=True)


def _section_header(title: str, icon: str = "") -> None:
    st.markdown(
        f'<div style="margin:20px 0 8px 0;padding:8px 14px;background:#141922;'
        f'border-left:3px solid #1f6feb;border-radius:0 8px 8px 0">'
        f'<span style="color:#f2f4f8;font-weight:700;font-size:15px">{icon} {title}</span></div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
css = _load_css("assets/style.css")
st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

if "case_log" not in st.session_state:
    st.session_state["case_log"] = []

st.title("📧 Email Header Analyzer")
st.markdown(
    '<span style="color:#9aa4b2;font-size:14px">Paste a raw email (headers + body) '
    'to extract routing hops, IP addresses, authentication results, and sender intelligence.</span>',
    unsafe_allow_html=True,
)

raw_email = st.text_area(
    "Paste Raw Email / Headers",
    height=260,
    placeholder=(
        "Paste the full raw email here, including all headers.\n\n"
        "In Gmail: Open email → ⋮ menu → Show original\n"
        "In Outlook: File → Properties → Internet headers\n"
        "In Thunderbird: View → Message Source"
    ),
    key="raw_email_input",
)

analyze_btn = st.button("🔍 Analyze", type="primary", disabled=not bool(raw_email and raw_email.strip()))

if analyze_btn and raw_email.strip():
    with st.spinner("Analyzing email headers..."):
        result = parse_email_headers(raw_email)

    # Log to case log
    st.session_state["case_log"].append({
        "module": "Email Header Analyzer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "filename": "email_header",
        "result": {
            "success": result["success"],
            "flags": result["flags"],
            "subject": result["basic"].get("Subject"),
        },
    })

    if not result["success"]:
        st.error(f"Analysis failed: {result['error']}")
        st.stop()

    flags = result["flags"]

    # ── Top-level threat banner ──────────────────────────────────────────────
    any_flag = any(flags.values())
    if any_flag:
        flagged = []
        if flags["spf_fail"]:
            flagged.append("SPF Fail/Softfail")
        if flags["dkim_fail"]:
            flagged.append("DKIM Fail/None")
        if flags["dmarc_fail"]:
            flagged.append("DMARC Fail")
        if flags["suspicious_hops"]:
            flagged.append("Suspicious Routing")
        st.error(f"⚠️ **Suspicious signals detected:** {', '.join(flagged)}")
    else:
        st.success("✅ No major red flags detected in this email.")

    # ── Authentication badges ────────────────────────────────────────────────
    auth = result["authentication"]
    badges_html = " &nbsp; ".join([
        _badge("SPF", auth.get("spf")),
        _badge("DKIM", auth.get("dkim")),
        _badge("DMARC", auth.get("dmarc")),
    ])
    st.markdown(
        f'<div style="margin:12px 0;display:flex;gap:8px;flex-wrap:wrap">{badges_html}</div>',
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📋 Basic Info", "🛣️ Routing & IPs", "🔐 Authentication", "🏷️ X-Headers", "📄 Raw / Export"]
    )

    # ────────────────────────────────────────────────────────────────────────
    # Tab 1 – Basic Info
    # ────────────────────────────────────────────────────────────────────────
    with tab1:
        basic = result["basic"]
        _section_header("Sender & Recipients", "👤")
        _row("From", basic.get("From"))
        _row("To", basic.get("To"))
        _row("CC", basic.get("CC"))
        _row("BCC", basic.get("BCC"))
        _row("Reply-To", basic.get("Reply-To"))
        _row("Return-Path", basic.get("Return-Path"))
        _row("Sender", basic.get("Sender"))

        _section_header("Message Details", "📝")
        _row("Subject", basic.get("Subject"))
        _row("Date", basic.get("Date"))
        _row("Message-ID", basic.get("Message-ID"))
        _row("MIME-Version", basic.get("MIME-Version"))
        _row("Content-Type", basic.get("Content-Type"))
        _row("Content-Transfer-Encoding", basic.get("Content-Transfer-Encoding"))

        _section_header("Client Info", "💻")
        _row("X-Mailer", basic.get("X-Mailer"))
        _row("User-Agent", basic.get("User-Agent"))
        _row("List-Unsubscribe", basic.get("List-Unsubscribe"))

        if result.get("body_preview"):
            _section_header("Body Preview", "📖")
            st.code(result["body_preview"], language=None)

    # ────────────────────────────────────────────────────────────────────────
    # Tab 2 – Routing & IPs
    # ────────────────────────────────────────────────────────────────────────
    with tab2:
        routing = result["routing"]
        all_ips = result["all_ips"]

        if routing:
            _section_header(f"Email Routing Path ({len(routing)} hops)", "🛣️")
            for i, hop in enumerate(routing, 1):
                privacy_tag = ""
                if hop.get("from_ip"):
                    privacy_tag = (
                        ' <span style="color:#9aa4b2;font-size:11px">[Private]</span>'
                        if hop.get("is_private")
                        else ' <span style="color:#1f6feb;font-size:11px">[Public]</span>'
                    )

                with st.expander(
                    f"Hop {i}: {hop.get('from_host') or 'Unknown'} → {hop.get('by_host') or 'Unknown'}",
                    expanded=(i == 1),
                ):
                    col1, col2 = st.columns(2)
                    with col1:
                        _row("From Host", hop.get("from_host"))
                        _row("From IP", hop.get("from_ip"))
                        _row("Reverse DNS", hop.get("rdns"))
                        _row("Is Private IP", str(hop.get("is_private")) if hop.get("is_private") is not None else None)
                    with col2:
                        _row("Received By", hop.get("by_host"))
                        _row("Timestamp", hop.get("timestamp"))
                        _row("Delay", f"{hop.get('delay_seconds')}s" if hop.get("delay_seconds") is not None else None)
                    if hop.get("raw"):
                        st.markdown("**Raw header:**")
                        st.code(hop["raw"], language=None)
        else:
            st.info("No Received: headers found.")

        if all_ips:
            _section_header(f"All IP Addresses Found ({len(all_ips)})", "🌐")
            ip_rows = []
            for entry in all_ips:
                ip_rows.append({
                    "IP Address": entry["ip"],
                    "Type": "Private" if entry["is_private"] else "Public",
                    "Reverse DNS": entry.get("rdns") or "—",
                })
            st.dataframe(ip_rows, use_container_width=True)
        else:
            st.info("No IP addresses found in headers.")

    # ────────────────────────────────────────────────────────────────────────
    # Tab 3 – Authentication
    # ────────────────────────────────────────────────────────────────────────
    with tab3:
        _section_header("Authentication Results", "🔐")
        _row("SPF Result", auth.get("spf", "Not found"))
        _row("DKIM Result", auth.get("dkim", "Not found"))
        _row("DMARC Result", auth.get("dmarc", "Not found"))
        _row("DKIM Signature Present", "Yes" if auth.get("dkim_signature_present") else "No")

        if auth.get("raw"):
            st.markdown("**Raw Authentication-Results header:**")
            st.code(auth["raw"], language=None)

        if auth.get("dkim_signature_raw"):
            st.markdown("**DKIM-Signature header:**")
            st.code(auth["dkim_signature_raw"], language=None)

        _section_header("What These Mean", "ℹ️")
        st.markdown("""
| Result | SPF | DKIM | DMARC |
|--------|-----|------|-------|
| **pass** ✅ | Server authorized to send for domain | Signature valid & unmodified | Passes SPF + DKIM alignment |
| **fail** ❌ | Server NOT authorized | Signature invalid or tampered | SPF + DKIM both fail |
| **softfail** ⚠️ | Suspicious but not blocked | — | — |
| **none** ⬜ | No SPF record exists | No DKIM signature | No DMARC policy |
        """)

    # ────────────────────────────────────────────────────────────────────────
    # Tab 4 – X-Headers
    # ────────────────────────────────────────────────────────────────────────
    with tab4:
        x_headers = result["x_headers"]
        if x_headers:
            _section_header(f"Extended Headers ({len(x_headers)} found)", "🏷️")
            st.markdown(
                '<span style="color:#9aa4b2;font-size:13px">X-headers often reveal the mail platform, '
                'campaign tools, originating service, and internal tracking IDs.</span>',
                unsafe_allow_html=True,
            )
            for key, val in x_headers.items():
                _row(key, val)
        else:
            st.info("No X-headers found in this email.")

    # ────────────────────────────────────────────────────────────────────────
    # Tab 5 – Raw Export
    # ────────────────────────────────────────────────────────────────────────
    with tab5:
        _section_header("Full Parsed Data (JSON)", "📄")
        st.json(result)
        download_payload = json.dumps(result, indent=2, default=str)
        st.download_button(
            "⬇️ Download Analysis JSON",
            data=download_payload,
            file_name="email_analysis.json",
            mime="application/json",
        )
