import streamlit as st
import anthropic
import json
import re

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Submission Readiness Scorecard Agent",
    page_icon="📋",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        font-size: 1.8rem;
        font-weight: 600;
        color: #1a1a2e;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #666;
        margin-bottom: 1.5rem;
    }
    .score-big {
        font-size: 3rem;
        font-weight: 700;
        text-align: center;
    }
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
        border: 1px solid #e0e0e0;
    }
    .metric-label {
        font-size: 0.78rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 600;
        color: #1a1a2e;
    }
    .check-pass  { color: #1a9e5f; font-weight: 500; }
    .check-warn  { color: #e07b00; font-weight: 500; }
    .check-fail  { color: #d32f2f; font-weight: 500; }
    .badge-p1 { background:#fdecea; color:#c62828; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }
    .badge-p2 { background:#fff3e0; color:#e65100; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }
    .badge-p3 { background:#e8f5e9; color:#2e7d32; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }
    .section-divider { border-top: 1px solid #e0e0e0; margin: 1.2rem 0; }
    .stProgress > div > div > div > div { border-radius: 4px; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Demo dossier text ─────────────────────────────────────────────────────────
DEMO_DOSSIER = """
NDA submission for a small molecule oral tablet (twice daily dosing).

Module 1 – Administrative:
Cover letter present. Form FDA 356h completed. No paediatric investigation plan (PIP) submitted.
Risk Management Plan (RMP) not included.

Module 2 – Summaries:
Quality Overall Summary (QOS) drafted but not finalised. Non-clinical overview complete.
Clinical overview complete. No integrated summary of safety (ISS) or efficacy (ISE).

Module 3 – CMC:
Drug Substance: synthesis route described, specifications set, 3 batches of analytical data present.
Stability data available for 12 months only (ICH Q1A requires 24 months for NDA).
Container closure system described. No genotoxic impurity assessment (ICH M7).

Drug Product: composition and formulation described, manufacturing process validated,
finished product specifications set, dissolution data complete.
No comparability protocol for post-approval changes. No elemental impurities assessment (ICH Q3D).

Module 4 – Non-clinical:
All pharmacology, PK, and toxicology studies complete and summarised.
No juvenile animal study data included.

Module 5 – Clinical:
Pivotal Phase 3 CSR complete. Phase 1/2 data complete.
120-day safety update outstanding. No dedicated hepatic impairment PK study.
No paediatric clinical data.
"""

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    api_key = st.text_input("Anthropic API Key", type="password",
                            help="Get your key at console.anthropic.com")
    st.markdown("---")
    region = st.selectbox("Target Region",
                          ["FDA + EMA (both)", "FDA only", "EMA only"])
    product_type = st.selectbox("Product Type",
                                ["Small molecule", "Biologic / biosimilar",
                                 "ATMP / gene therapy", "Fixed-dose combination"])
    st.markdown("---")
    st.markdown("**About this agent**")
    st.caption(
        "Built by a regulatory AI specialist. "
        "Checks NDA/MAA dossiers against ICH M4, Q1A, Q3D, M7, "
        "FDA 21 CFR, and EMA guidelines. "
        "Returns pass/fail checks, a readiness score, "
        "and a prioritised fix list."
    )
    st.markdown("---")
    st.caption("🔗 Follow on LinkedIn for weekly regulatory AI tools")

# ── Main layout ───────────────────────────────────────────────────────────────
st.markdown('<p class="main-header">📋 Submission Readiness Scorecard Agent</p>',
            unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">NDA / MAA · Full CTD dossier · '
    'ICH M4 · FDA · EMA · Instant pass/fail + prioritised fix list</p>',
    unsafe_allow_html=True,
)

tab_paste, tab_describe, tab_demo = st.tabs(
    ["📄 Paste dossier content", "✍️ Describe your submission", "🎯 Run demo"]
)

with tab_paste:
    user_content = st.text_area(
        "Paste any part of your dossier — TOC, summaries, status notes",
        height=220,
        placeholder=(
            "Module 1: Cover letter present, Form FDA 356h complete...\n"
            "Module 3: Drug substance synthesis described, stability 24 months...\n"
            "Module 5: Pivotal Phase 3 CSR included..."
        ),
    )
    run_paste = st.button("▶ Run Scorecard", key="run_paste", type="primary",
                          use_container_width=True)

with tab_describe:
    user_describe = st.text_area(
        "Describe your submission status in plain language",
        height=220,
        placeholder=(
            "e.g. Small molecule NDA for FDA. Module 3 mostly complete "
            "but stability only 12 months. Module 2 QOS drafted. "
            "Clinical modules complete. No paediatric plan yet."
        ),
    )
    run_describe = st.button("▶ Run Scorecard", key="run_describe", type="primary",
                             use_container_width=True)

with tab_demo:
    st.info(
        "Pre-filled NDA example with common gaps: missing paediatric plan, "
        "12-month stability only, no RMP, no elemental impurities assessment."
    )
    with st.expander("View demo dossier content"):
        st.text(DEMO_DOSSIER)
    run_demo = st.button("▶ Run Demo Scorecard", key="run_demo", type="primary",
                         use_container_width=True)

# ── Determine what to run ─────────────────────────────────────────────────────
content_to_run = None
if run_paste and user_content.strip():
    content_to_run = user_content.strip()
elif run_paste and not user_content.strip():
    st.warning("Please paste some dossier content first.")
elif run_describe and user_describe.strip():
    content_to_run = user_describe.strip()
elif run_describe and not user_describe.strip():
    st.warning("Please describe your submission first.")
elif run_demo:
    content_to_run = DEMO_DOSSIER

# ── Run agent ─────────────────────────────────────────────────────────────────
if content_to_run:
    if not api_key:
        st.error("Please enter your Anthropic API key in the sidebar.")
        st.stop()

    SYSTEM_PROMPT = """You are a senior regulatory affairs expert with 20+ years of experience 
reviewing NDA and MAA submissions for FDA and EMA. You check dossiers against:
- ICH M4 (CTD structure and completeness)
- ICH Q1A (stability requirements)
- ICH Q3D (elemental impurities)
- ICH M7 (genotoxic impurities)
- ICH E11 (paediatric studies)
- FDA 21 CFR Part 314 (NDA requirements)
- EMA Module 1 requirements and RMP guidelines

You MUST respond ONLY with a valid JSON object. No markdown, no backticks, no preamble.
The JSON must follow this exact schema:
{
  "score": <integer 0-100>,
  "passed_count": <integer>,
  "critical_count": <integer>,
  "warning_count": <integer>,
  "readiness_label": "<Not ready | Needs significant work | Needs work | Nearly ready | Ready to file>",
  "readiness_color": "<red | orange | amber | green>",
  "modules": [
    {"name": "Module 1 – Administrative", "score": <0-100>, "status": "<green|amber|red>"},
    {"name": "Module 2 – Summaries",      "score": <0-100>, "status": "<green|amber|red>"},
    {"name": "Module 3 – CMC",            "score": <0-100>, "status": "<green|amber|red>"},
    {"name": "Module 4 – Non-clinical",   "score": <0-100>, "status": "<green|amber|red>"},
    {"name": "Module 5 – Clinical",       "score": <0-100>, "status": "<green|amber|red>"}
  ],
  "critical": [
    {"title": "<issue>", "guideline": "<e.g. ICH Q1A(R2)>", "comment": "<specific regulatory comment>"}
  ],
  "warnings": [
    {"title": "<issue>", "guideline": "<guideline ref>", "comment": "<comment>"}
  ],
  "passed": [
    {"title": "<what passed>", "comment": "<brief note>"}
  ],
  "fix_list": [
    {"priority": "P1", "action": "<specific action>", "guideline": "<ref>"},
    {"priority": "P2", "action": "<specific action>", "guideline": "<ref>"},
    {"priority": "P3", "action": "<specific action>", "guideline": "<ref>"}
  ]
}
Include 3-7 critical issues, 2-5 warnings, 3-8 passed checks, 5-10 fix list items.
Be specific. Reference real guidelines. P1 = submission blocker, P2 = strongly recommended, P3 = best practice."""

    user_prompt = f"""Please evaluate this NDA/MAA submission for readiness.
Target region: {region}
Product type: {product_type}

Dossier content:
{content_to_run}

Return the JSON scorecard."""

    with st.spinner("Analysing dossier against ICH guidelines and regional requirements..."):
        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            result = json.loads(raw)
        except json.JSONDecodeError:
            st.error("Could not parse agent response. Try again.")
            st.code(raw, language="text")
            st.stop()
        except anthropic.AuthenticationError:
            st.error("Invalid API key. Check your key in the sidebar.")
            st.stop()
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

    # ── Render results ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 📊 Scorecard Results")

    # Score colour
    score = result.get("score", 0)
    score_color = (
        "#d32f2f" if score < 50
        else "#e07b00" if score < 70
        else "#2e7d32"
    )

    # Top metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(
            f'<div class="metric-card">'
            f'<div class="metric-label">Overall score</div>'
            f'<div class="metric-value" style="color:{score_color}">{score}%</div>'
            f'</div>', unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f'<div class="metric-card">'
            f'<div class="metric-label">Checks passed</div>'
            f'<div class="metric-value" style="color:#2e7d32">{result.get("passed_count","—")}</div>'
            f'</div>', unsafe_allow_html=True
        )
    with col3:
        st.markdown(
            f'<div class="metric-card">'
            f'<div class="metric-label">Critical gaps</div>'
            f'<div class="metric-value" style="color:#d32f2f">{result.get("critical_count","—")}</div>'
            f'</div>', unsafe_allow_html=True
        )
    with col4:
        label = result.get("readiness_label", "—")
        label_color = (
            "#d32f2f" if "Not ready" in label
            else "#e07b00" if "work" in label.lower()
            else "#2e7d32"
        )
        st.markdown(
            f'<div class="metric-card">'
            f'<div class="metric-label">Readiness</div>'
            f'<div class="metric-value" style="color:{label_color};font-size:1.1rem">{label}</div>'
            f'</div>', unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Module scores
    st.markdown("#### Module-by-module scores")
    status_colors = {"green": "#2e7d32", "amber": "#e07b00", "red": "#d32f2f"}
    for mod in result.get("modules", []):
        ms = mod.get("score", 0)
        mstatus = mod.get("status", "amber")
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.progress(ms / 100, text=mod["name"])
        with col_b:
            st.markdown(
                f'<p style="color:{status_colors.get(mstatus,"#333")};'
                f'font-weight:600;margin-top:6px">{ms}%</p>',
                unsafe_allow_html=True
            )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # Three columns: critical | warnings | passed
    col_c, col_w, col_p = st.columns(3)

    with col_c:
        st.markdown("#### 🔴 Critical gaps")
        for item in result.get("critical", []):
            with st.expander(f"**{item['title']}**"):
                st.caption(f"Guideline: `{item.get('guideline','—')}`")
                st.write(item.get("comment", ""))

    with col_w:
        st.markdown("#### 🟡 Warnings")
        for item in result.get("warnings", []):
            with st.expander(f"**{item['title']}**"):
                st.caption(f"Guideline: `{item.get('guideline','—')}`")
                st.write(item.get("comment", ""))

    with col_p:
        st.markdown("#### ✅ Passed checks")
        for item in result.get("passed", []):
            with st.expander(f"**{item['title']}**"):
                st.write(item.get("comment", ""))

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # Prioritised fix list
    st.markdown("#### 🛠️ Prioritised fix list")
    badge_map = {"P1": "badge-p1", "P2": "badge-p2", "P3": "badge-p3"}
    label_map = {"P1": "P1 — Blocker", "P2": "P2 — Recommended", "P3": "P3 — Best practice"}
    for i, fix in enumerate(result.get("fix_list", []), 1):
        p = fix.get("priority", "P3")
        badge_cls = badge_map.get(p, "badge-p3")
        badge_lbl = label_map.get(p, p)
        col_n, col_fix = st.columns([1, 10])
        with col_n:
            st.markdown(f"**{i}**")
        with col_fix:
            st.markdown(
                f'<span class="{badge_cls}">{badge_lbl}</span> '
                f'&nbsp; {fix["action"]} '
                f'<span style="color:#999;font-size:0.8rem">[{fix.get("guideline","—")}]</span>',
                unsafe_allow_html=True,
            )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # Raw JSON expander
    with st.expander("🔍 View raw JSON response"):
        st.json(result)

    st.success(
        "✅ Scorecard complete. Take a screenshot and post it on LinkedIn! "
        "Tag it #RegulatoryAI #Veeva #eCTD"
    )
