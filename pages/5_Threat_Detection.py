"""Page wrapper that embeds Threat.py inside the multi-page Cyber Trident app."""
from __future__ import annotations

import sys
import unittest.mock
import streamlit as st

# Threat.py calls st.set_page_config() inside ThreatDetectionApp.run().
# In a multi-page app the config is already set by app.py, so we patch it
# out to a no-op to avoid a StreamlitAPIException.
st.set_page_config = lambda **kwargs: None  # noqa: E731

# Now it's safe to import from Threat.py
sys.path.insert(0, ".")
from Threat import ThreatDetectionApp  # noqa: E402

app = ThreatDetectionApp()
app.run()
