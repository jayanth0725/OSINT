from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fpdf import FPDF


def _summarize_entry(entry: Dict[str, Any]) -> List[str]:
    """Summarize a case log entry into human-readable bullets."""
    summary = []
    result = entry.get("result", {})
    flags = result.get("flags") or {}
    risk_level = result.get("risk_level")
    if risk_level:
        summary.append(f"Risk level: {risk_level}")
    if flags.get("gps_flag"):
        summary.append("GPS metadata found")
    if flags.get("identity_flag"):
        summary.append("Identity metadata found")
    if result.get("domain_age_days") is not None:
        summary.append(f"Domain age: {result.get('domain_age_days')} days")
    if result.get("total") is not None:
        summary.append(f"Total results: {result.get('total')}")
    return summary or ["No key findings recorded"]


def generate_pdf_report(case_log: List[Dict[str, Any]], filename: str) -> bytes:
    """Generate a PDF report for the provided case log."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "Cyber Trident - Case Report", ln=True)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, f"Generated: {datetime.now(timezone.utc).isoformat()} UTC", ln=True)
    pdf.cell(0, 10, f"Total findings: {len(case_log)}", ln=True)

    for entry in case_log:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, entry.get("module", "Unknown Module"), ln=True)
        pdf.set_font("Helvetica", "", 11)
        timestamp = entry.get("timestamp")
        pdf.cell(0, 8, f"Timestamp: {timestamp}", ln=True)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Key Findings:", ln=True)
        pdf.set_font("Helvetica", "", 11)
        for line in _summarize_entry(entry):
            pdf.multi_cell(0, 6, f"- {line}")

    output = pdf.output(dest="S")
    return output.encode("latin-1")
