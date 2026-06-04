# OSINT Investigator Platform

![Screenshot Placeholder](docs/screenshot-placeholder.png)

## Overview
OSINT Investigator Platform is a production-ready, multi-page Streamlit application that unifies metadata extraction, QR fraud detection, and social media intelligence into a single investigative dashboard. It is designed for cybersecurity analysts and OSINT practitioners who need fast, repeatable workflows and structured reporting.

## Prerequisites
- Python 3.10+
- ffprobe installed (part of ffmpeg)

## Setup
1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the Streamlit secrets template:
   ```bash
   copy .streamlit\secrets.toml.example .streamlit\secrets.toml
   ```
4. Open `.streamlit/secrets.toml` and fill in the API keys

## API Keys (Streamlit Secrets)
Add the following keys to `.streamlit/secrets.toml` for local runs, or set them in the Streamlit Cloud app settings under **Secrets** when deploying:

```toml
VT_API_KEY = ""
URLSCAN_API_KEY = ""
TWITTER_BEARER_TOKEN = ""
TW_API_KEY = ""
TW_API_SECRET = ""
TW_ACCESS_TOKEN = ""
TW_ACCESS_SECRET = ""
```

Key sources:
- VirusTotal: https://www.virustotal.com/ (API key in your profile)
- URLScan.io: https://urlscan.io/ (API key in your settings)
- Twitter Developer Portal: https://developer.twitter.com/ (create an app and generate tokens)

## Run the App
```bash
streamlit run app.py
```

## Modules
- **Metadata Extraction Toolkit**: Parses EXIF data, PDF metadata, and video container metadata (ffprobe).
- **QR Code Fraud Detection**: Decodes QR content, analyzes URLs, and computes risk scores using WHOIS, VirusTotal, and URLScan.
- **Social Media Intelligence**: Username discovery (Sherlock), keyword monitoring (Twitter API v2), and trend insights (Twitter API v1.1).

## Known Limitations
- External API usage requires valid keys and adheres to provider rate limits.
- QR decoding accuracy depends on input image quality.
- Sherlock results depend on platform availability and response time.

## Ethical Use Disclaimer
This toolkit is intended for lawful, ethical OSINT investigations. Ensure you have authorization and comply with applicable laws, terms of service, and privacy regulations.
