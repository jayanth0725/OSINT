from __future__ import annotations

import email
import email.header
import email.policy
import re
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Header decoding helpers
# ---------------------------------------------------------------------------

def _decode_header(value: str) -> str:
    """Decode encoded email header strings (RFC 2047)."""
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded_parts = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
            except (LookupError, Exception):
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(str(part))
    return " ".join(decoded_parts).strip()


def _safe_get(msg: email.message.Message, header: str) -> Optional[str]:
    """Safely retrieve a decoded header value."""
    val = msg.get(header)
    if val is None:
        return None
    return _decode_header(str(val))


# ---------------------------------------------------------------------------
# IP extraction & geo helpers
# ---------------------------------------------------------------------------

_IP_PATTERN = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)

_PRIVATE_RANGES = [
    re.compile(r"^10\."),
    re.compile(r"^172\.(1[6-9]|2\d|3[01])\."),
    re.compile(r"^192\.168\."),
    re.compile(r"^127\."),
    re.compile(r"^::1$"),
    re.compile(r"^169\.254\."),
]


def _is_private_ip(ip: str) -> bool:
    return any(pat.match(ip) for pat in _PRIVATE_RANGES)


def _reverse_dns(ip: str) -> Optional[str]:
    """Attempt reverse DNS lookup."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Received-header parser
# ---------------------------------------------------------------------------

_FROM_BY_RE = re.compile(
    r"from\s+([\w\.\-\[\]]+)"
    r"(?:\s+\(([^)]*)\))?"
    r".*?by\s+([\w\.\-\[\]]+)"
    r"(?:\s+\(([^)]*)\))?",
    re.IGNORECASE | re.DOTALL,
)

_DATE_IN_RECEIVED_RE = re.compile(
    r";\s*(.+)$",
    re.DOTALL,
)


def _parse_received_header(received_raw: str) -> Dict[str, Any]:
    """Parse a single Received: header into structured fields."""
    hop: Dict[str, Any] = {
        "raw": received_raw.strip(),
        "from_host": None,
        "from_ip": None,
        "by_host": None,
        "timestamp": None,
        "delay_seconds": None,
        "is_private": None,
        "rdns": None,
    }

    m = _FROM_BY_RE.search(received_raw)
    if m:
        hop["from_host"] = m.group(1) or None
        from_detail = m.group(2) or ""
        ips_in_detail = _IP_PATTERN.findall(from_detail)
        hop["from_ip"] = ips_in_detail[0] if ips_in_detail else None
        hop["by_host"] = m.group(3) or None

    # Also scan full line for IPs if not found in detail
    if not hop["from_ip"]:
        all_ips = _IP_PATTERN.findall(received_raw)
        hop["from_ip"] = all_ips[0] if all_ips else None

    if hop["from_ip"]:
        hop["is_private"] = _is_private_ip(hop["from_ip"])
        if not hop["is_private"]:
            hop["rdns"] = _reverse_dns(hop["from_ip"])

    date_m = _DATE_IN_RECEIVED_RE.search(received_raw)
    if date_m:
        raw_date = date_m.group(1).strip()
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%d %b %Y %H:%M:%S %Z",
        ):
            try:
                hop["timestamp"] = datetime.strptime(raw_date[:31], fmt).isoformat()
                break
            except ValueError:
                continue

    return hop


# ---------------------------------------------------------------------------
# Authentication Results parser
# ---------------------------------------------------------------------------

def _parse_auth_results(auth_raw: str) -> Dict[str, Optional[str]]:
    """Parse Authentication-Results header."""
    result: Dict[str, Optional[str]] = {
        "spf": None,
        "dkim": None,
        "dmarc": None,
        "raw": auth_raw.strip(),
    }
    lower = auth_raw.lower()
    for proto in ("spf", "dkim", "dmarc"):
        pattern = re.compile(rf"{proto}=(\w+)", re.IGNORECASE)
        m = pattern.search(lower)
        if m:
            result[proto] = m.group(1)
    return result


# ---------------------------------------------------------------------------
# Main email header parser
# ---------------------------------------------------------------------------

def parse_email_headers(raw_email: str) -> Dict[str, Any]:
    """
    Parse raw email text (headers + optional body) and return structured
    intelligence including routing hops, IPs, authentication, and addresses.
    """
    output: Dict[str, Any] = {
        "success": False,
        "error": None,
        "basic": {},
        "routing": [],
        "authentication": {},
        "all_ips": [],
        "x_headers": {},
        "body_preview": None,
        "flags": {
            "spf_fail": False,
            "dkim_fail": False,
            "dmarc_fail": False,
            "suspicious_hops": False,
        },
    }

    try:
        msg = email.message_from_string(raw_email, policy=email.policy.compat32)
    except Exception as exc:
        output["error"] = f"Failed to parse email: {exc}"
        return output

    # --- Basic fields -------------------------------------------------------
    output["basic"] = {
        "From": _safe_get(msg, "From"),
        "To": _safe_get(msg, "To"),
        "CC": _safe_get(msg, "CC"),
        "BCC": _safe_get(msg, "BCC"),
        "Reply-To": _safe_get(msg, "Reply-To"),
        "Subject": _safe_get(msg, "Subject"),
        "Date": _safe_get(msg, "Date"),
        "Message-ID": _safe_get(msg, "Message-ID"),
        "MIME-Version": _safe_get(msg, "MIME-Version"),
        "Content-Type": _safe_get(msg, "Content-Type"),
        "Content-Transfer-Encoding": _safe_get(msg, "Content-Transfer-Encoding"),
        "X-Mailer": _safe_get(msg, "X-Mailer"),
        "User-Agent": _safe_get(msg, "User-Agent"),
        "Return-Path": _safe_get(msg, "Return-Path"),
        "Sender": _safe_get(msg, "Sender"),
        "List-Unsubscribe": _safe_get(msg, "List-Unsubscribe"),
    }

    # --- Routing hops (Received: headers) -----------------------------------
    received_headers = msg.get_all("Received") or []
    hops: List[Dict[str, Any]] = []
    for raw in received_headers:
        hop = _parse_received_header(str(raw))
        hops.append(hop)

    # Calculate delays between hops
    timestamps = []
    for hop in hops:
        if hop.get("timestamp"):
            try:
                timestamps.append(datetime.fromisoformat(hop["timestamp"]))
            except ValueError:
                timestamps.append(None)
        else:
            timestamps.append(None)

    for i in range(len(hops) - 1):
        t_curr = timestamps[i]
        t_next = timestamps[i + 1]
        if t_curr and t_next:
            try:
                delta = abs((t_curr - t_next).total_seconds())
                hops[i]["delay_seconds"] = round(delta)
            except Exception:
                pass

    output["routing"] = list(reversed(hops))  # chronological order

    # --- Authentication Results ---------------------------------------------
    auth_headers = msg.get_all("Authentication-Results") or []
    if auth_headers:
        combined_auth = " ".join(str(h) for h in auth_headers)
        output["authentication"] = _parse_auth_results(combined_auth)
    else:
        output["authentication"] = {
            "spf": None, "dkim": None, "dmarc": None, "raw": None
        }

    # DKIM-Signature presence
    output["authentication"]["dkim_signature_present"] = bool(msg.get("DKIM-Signature"))
    output["authentication"]["dkim_signature_raw"] = _safe_get(msg, "DKIM-Signature")

    # --- Collect all IPs from all headers -----------------------------------
    all_header_text = "\n".join(
        f"{k}: {v}" for k, v in msg.items()
    )
    all_ips_set: set[str] = set()
    for ip in _IP_PATTERN.findall(all_header_text):
        all_ips_set.add(ip)

    all_ip_list = []
    for ip in sorted(all_ips_set):
        entry: Dict[str, Any] = {
            "ip": ip,
            "is_private": _is_private_ip(ip),
            "rdns": None,
        }
        if not entry["is_private"]:
            entry["rdns"] = _reverse_dns(ip)
        all_ip_list.append(entry)

    output["all_ips"] = all_ip_list

    # --- X-headers (often reveal sender platform info) ----------------------
    x_headers: Dict[str, str] = {}
    for key in msg.keys():
        if key.lower().startswith("x-"):
            val = _safe_get(msg, key)
            if val:
                x_headers[key] = val
    output["x_headers"] = x_headers

    # --- Body preview (first 500 chars of plain text part) ------------------
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        text = payload.decode(charset, errors="replace")
                        output["body_preview"] = text[:500].strip()
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
                output["body_preview"] = text[:500].strip()
    except Exception:
        pass

    # --- Flags --------------------------------------------------------------
    auth = output["authentication"]
    output["flags"]["spf_fail"] = auth.get("spf") in ("fail", "softfail", "none")
    output["flags"]["dkim_fail"] = auth.get("dkim") in ("fail", "none")
    output["flags"]["dmarc_fail"] = auth.get("dmarc") in ("fail", "none")

    # Suspicious if From domain ≠ envelope Return-Path domain
    from_addr = str(output["basic"].get("From") or "")
    return_path = str(output["basic"].get("Return-Path") or "")
    from_domain_m = re.search(r"@([\w\.\-]+)", from_addr)
    return_domain_m = re.search(r"@([\w\.\-]+)", return_path)
    if from_domain_m and return_domain_m:
        if from_domain_m.group(1).lower() != return_domain_m.group(1).lower():
            output["flags"]["suspicious_hops"] = True

    # Many public IPs → suspicious
    public_ips = [i for i in output["all_ips"] if not i["is_private"]]
    if len(public_ips) > 5:
        output["flags"]["suspicious_hops"] = True

    output["success"] = True
    return output
