"""
6_Password_Maker.py — Customisable Password Generator
Integrated into the OSINT Investigator Platform multi-page app.
"""
from __future__ import annotations

import random
import secrets
import string
import streamlit as st

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

CHAR_SETS = {
    "uppercase": string.ascii_uppercase,          # A-Z
    "lowercase": string.ascii_lowercase,          # a-z
    "digits":    string.digits,                   # 0-9
    "symbols":   "!@#$%^&*()-_=+[]{}|;:,.<>?",   # common symbols
    "ambiguous": "Il1O0",                          # look-alike chars to optionally exclude
}

STRENGTH_THRESHOLDS = [
    (90, "🟢 Very Strong"),
    (70, "🟡 Strong"),
    (50, "🟠 Moderate"),
    (30, "🔴 Weak"),
    (0,  "🔴 Very Weak"),
]


def _entropy_bits(password: str) -> float:
    """Rough entropy estimate: log2(pool_size) * length."""
    pool = 0
    if any(c in string.ascii_lowercase for c in password):
        pool += 26
    if any(c in string.ascii_uppercase for c in password):
        pool += 26
    if any(c in string.digits for c in password):
        pool += 10
    if any(c not in string.ascii_letters + string.digits for c in password):
        pool += 32
    return (pool.bit_length() - 1) * len(password) if pool > 0 else 0


def _strength_score(password: str) -> int:
    """Return a 0-100 score reflecting password strength."""
    score = 0
    length = len(password)
    # Length bonus
    score += min(length * 3, 50)
    # Character-variety bonus
    has_lower = any(c in string.ascii_lowercase for c in password)
    has_upper = any(c in string.ascii_uppercase for c in password)
    has_digit = any(c in string.digits for c in password)
    has_sym   = any(c not in string.ascii_letters + string.digits for c in password)
    score += sum([has_lower, has_upper, has_digit, has_sym]) * 10
    # Entropy cap
    return min(score, 100)


def _strength_label(score: int) -> str:
    for threshold, label in STRENGTH_THRESHOLDS:
        if score >= threshold:
            return label
    return "🔴 Very Weak"


def _generate_password(
    length: int,
    use_upper: bool,
    use_lower: bool,
    use_digits: bool,
    use_symbols: bool,
    exclude_ambiguous: bool,
    custom_exclude: str,
    min_each: int,
) -> str:
    """Generate a cryptographically secure password based on user prefs."""
    pool = ""
    guaranteed: list[str] = []

    char_map = {
        "uppercase": use_upper,
        "lowercase": use_lower,
        "digits":    use_digits,
        "symbols":   use_symbols,
    }

    for key, enabled in char_map.items():
        if enabled:
            chars = CHAR_SETS[key]
            if exclude_ambiguous:
                chars = "".join(c for c in chars if c not in CHAR_SETS["ambiguous"])
            if custom_exclude:
                chars = "".join(c for c in chars if c not in custom_exclude)
            pool += chars
            if chars:
                for _ in range(min_each):
                    guaranteed.append(secrets.choice(chars))

    if not pool:
        st.error("⚠️ Select at least one character type.")
        return ""

    remaining_len = max(length - len(guaranteed), 0)
    remaining = [secrets.choice(pool) for _ in range(remaining_len)]
    all_chars = guaranteed + remaining
    secrets.SystemRandom().shuffle(all_chars)
    return "".join(all_chars[:length])


def _history_append(pwd: str) -> None:
    if "pw_history" not in st.session_state:
        st.session_state.pw_history = []
    if pwd and pwd not in st.session_state.pw_history:
        st.session_state.pw_history.insert(0, pwd)
        st.session_state.pw_history = st.session_state.pw_history[:10]


# ─────────────────────────────────────────────
#  Page layout
# ─────────────────────────────────────────────

st.title("🔑 Password Maker")
st.markdown(
    "Generate **cryptographically secure** passwords with full customisation. "
    "All generation happens client-side — nothing is sent to a server."
)

# ── Sidebar controls ──────────────────────────
with st.sidebar:
    st.header("⚙️ Generator Settings")

    length = st.slider("Password Length", min_value=4, max_value=128, value=16, step=1)

    st.markdown("**Character Sets**")
    use_upper   = st.checkbox("Uppercase (A-Z)",   value=True)
    use_lower   = st.checkbox("Lowercase (a-z)",   value=True)
    use_digits  = st.checkbox("Digits (0-9)",       value=True)
    use_symbols = st.checkbox("Symbols (!@#…)",     value=True)

    st.markdown("**Exclusions**")
    exclude_ambiguous = st.checkbox("Exclude ambiguous chars (I l 1 O 0)", value=False)
    custom_exclude    = st.text_input(
        "Also exclude these characters",
        value="",
        placeholder="e.g. @#$",
        help="Type any characters you want removed from the pool.",
    )

    st.markdown("**Minimum guarantees per set**")
    min_each = st.slider(
        "Min chars per enabled set",
        min_value=0, max_value=5, value=1,
        help="Ensures at least N characters from each enabled set appear.",
    )

    count = st.slider("How many to generate", min_value=1, max_value=20, value=1)

# ── Generate button ───────────────────────────
if st.button("✨ Generate Password(s)", use_container_width=True, type="primary"):
    st.session_state.generated = [
        _generate_password(
            length, use_upper, use_lower, use_digits, use_symbols,
            exclude_ambiguous, custom_exclude, min_each,
        )
        for _ in range(count)
    ]
    for p in st.session_state.generated:
        _history_append(p)

# ── Results ───────────────────────────────────
if "generated" in st.session_state and st.session_state.generated:
    st.markdown("---")
    st.subheader("🔐 Generated Password(s)")

    for i, pwd in enumerate(st.session_state.generated, 1):
        if not pwd:
            continue

        score  = _strength_score(pwd)
        label  = _strength_label(score)
        entropy = _entropy_bits(pwd)

        col_pw, col_copy = st.columns([5, 1])
        with col_pw:
            st.code(pwd, language=None)
        with col_copy:
            # Streamlit doesn't have a native clipboard button, so we use st.download_button
            st.download_button(
                label="⬇️",
                data=pwd,
                file_name=f"password_{i}.txt",
                mime="text/plain",
                key=f"dl_{i}_{pwd[:4]}",
                help="Download this password as a .txt file",
            )

        # Strength meter
        strength_col, entropy_col, len_col = st.columns(3)
        with strength_col:
            st.metric("Strength", label)
        with entropy_col:
            st.metric("~Entropy", f"{entropy:.0f} bits")
        with len_col:
            st.metric("Length", f"{len(pwd)} chars")

        st.progress(score / 100)

        if count > 1:
            st.markdown("---")

# ── Bulk export ───────────────────────────────
if (
    "generated" in st.session_state
    and len(st.session_state.generated) > 1
):
    all_passwords = "\n".join(p for p in st.session_state.generated if p)
    st.download_button(
        "📥 Download All Passwords",
        data=all_passwords,
        file_name="passwords.txt",
        mime="text/plain",
        use_container_width=True,
    )

# ── Tips ─────────────────────────────────────
with st.expander("💡 Password Tips"):
    st.markdown("""
    - **12+ characters** is the modern minimum for general accounts.  
    - **16–20 characters** is recommended for sensitive accounts (email, banking).  
    - Use a **password manager** (Bitwarden, 1Password) — don't re-use passwords.  
    - Enable **2-factor authentication** wherever possible.  
    - A mix of all four character types is the strongest combination.  
    - Entropy above **80 bits** is considered very strong against brute-force.
    """)

# ── History ───────────────────────────────────
if st.session_state.get("pw_history"):
    with st.expander(f"📋 Session History ({len(st.session_state.pw_history)} passwords)"):
        for idx, p in enumerate(st.session_state.pw_history, 1):
            col1, col2 = st.columns([6, 1])
            col1.code(p, language=None)
            col2.download_button(
                "⬇️",
                data=p,
                file_name=f"pw_{idx}.txt",
                mime="text/plain",
                key=f"hist_dl_{idx}_{p[:4]}",
            )

        if st.button("🗑️ Clear History"):
            st.session_state.pw_history = []
            st.rerun()
