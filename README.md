# Submission Readiness Scorecard Agent 🧬

An AI-powered tool that checks your NDA/MAA dossier for submission readiness against ICH M4, FDA 21 CFR, and EMA guidelines.

## What it does
- Analyses your dossier content (pasted text or plain description)
- Checks all 5 CTD modules (M1–M5)
- Returns: Pass/Fail per check, % readiness score per module, and a prioritised fix list
- Supports FDA, EMA, or both as target regions
- Works for small molecules, biologics, and ATMPs

## Built with
- [Streamlit](https://streamlit.io) — UI
- [Anthropic Claude](https://anthropic.com) — AI reasoning engine

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Add your API key to `.streamlit/secrets.toml`:
```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

## Deploy on Streamlit Cloud
See deployment guide in the repo or follow the step-by-step instructions.

---
Built as part of a weekly AI agent series for regulatory affairs professionals.
