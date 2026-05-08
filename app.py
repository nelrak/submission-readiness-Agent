import streamlit as st
import json
import re
import pandas as pd
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Submission Readiness Scorecard Agent",
    page_icon="📋",
    layout="wide",
)

# ── Custom CSS ──────────────────────────────────────────────────────────
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

# ── Demo dossier text ────────────────────────────────────────────────────────
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

# Helper function to normalize and fuzzy match column names
def find_column(df, keywords):
    """Find column by fuzzy matching keywords. Keywords is a list of possible names."""
    normalized_cols = {col: col.strip().replace('\n', ' ').replace('\r', ' ') for col in df.columns}
    normalized_cols = {' '.join(k.split()): v for k, v in normalized_cols.items()}

    for keyword in keywords:
        keyword_normalized = ' '.join(keyword.strip().replace('\n', ' ').replace('\r', ' ').split())
        if keyword_normalized in normalized_cols:
            return normalized_cols[keyword_normalized]

    # Fuzzy partial match
    for keyword in keywords:
        keyword_lower = keyword.lower()
        for normalized_col, original_col in normalized_cols.items():
            if keyword_lower in normalized_col.lower():
                return original_col

    return None


# ════════════════════════════════════════════════════════════════════════════
# RULE-BASED REGULATORY ANALYSIS ENGINE (replaces Anthropic API)
# ════════════════════════════════════════════════════════════════════════════
def analyze_dossier(content: str, region: str, product_type: str) -> dict:
    """
    Local rule-based analysis of NDA/MAA dossier content.
    Checks against ICH M4, Q1A, Q3D, M7, E11, FDA 21 CFR, EMA guidelines.
    Returns a JSON-shaped dict identical to the previous LLM output.
    """
    text = content.lower()

    def has_any(*keywords):
        return any(k.lower() in text for k in keywords)

    def mentions_missing(*keywords):
        """Detect if content says something is missing/not included/outstanding."""
        for k in keywords:
            k_low = k.lower()
            patterns = [
                rf"no\s+{re.escape(k_low)}",
                rf"not\s+(?:included|submitted|finalised|finalized|provided|available|complete)\b[^.]*\b{re.escape(k_low)}",
                rf"{re.escape(k_low)}[^.]*\b(?:not|outstanding|missing|absent|pending|drafted but)",
                rf"missing\s+{re.escape(k_low)}",
                rf"without\s+{re.escape(k_low)}",
            ]
            for p in patterns:
                if re.search(p, text):
                    return True
        return False

    critical = []
    warnings_list = []
    passed = []
    fix_list = []

    # ── Module 1 – Administrative ───────────────────────────────────────────
    m1_score = 100
    if has_any("cover letter"):
        passed.append({"title": "Cover letter present (Module 1)",
                       "comment": "Administrative cover letter found in dossier."})
    else:
        warnings_list.append({"title": "Cover letter not confirmed",
                              "guideline": "FDA 21 CFR 314.50 / EMA Notice to Applicants",
                              "comment": "Ensure a cover letter is included in Module 1."})
        m1_score -= 10

    if has_any("356h", "form fda 356h"):
        passed.append({"title": "Form FDA 356h completed",
                       "comment": "Application form present for FDA submission."})
    elif "FDA" in region:
        critical.append({"title": "Form FDA 356h status unclear",
                         "guideline": "FDA 21 CFR 314.50",
                         "comment": "Form FDA 356h is required for any NDA submission."})
        m1_score -= 20
        fix_list.append({"priority": "P1",
                         "action": "Complete and include Form FDA 356h",
                         "guideline": "FDA 21 CFR 314.50"})

    pip_missing = mentions_missing("paediatric investigation plan", "pip", "pediatric plan", "paediatric plan")
    if pip_missing or "no paediatric" in text or "no pediatric" in text:
        if "EMA" in region:
            critical.append({"title": "No Paediatric Investigation Plan (PIP)",
                             "guideline": "EU Regulation 1901/2006 / EMA PIP requirements",
                             "comment": "An agreed PIP (or waiver/deferral) is mandatory for EMA MAA submissions."})
            m1_score -= 25
            fix_list.append({"priority": "P1",
                             "action": "Submit agreed PIP, waiver, or deferral with PDCO",
                             "guideline": "EU Regulation 1901/2006"})
        if "FDA" in region:
            critical.append({"title": "No Pediatric Study Plan (PSP)",
                             "guideline": "FDA PREA / 21 USC 355c",
                             "comment": "An initial Pediatric Study Plan is required under PREA for most NDAs."})
            m1_score -= 20
            fix_list.append({"priority": "P1",
                             "action": "Submit initial Pediatric Study Plan (iPSP)",
                             "guideline": "FDA PREA / 21 USC 355c"})

    rmp_missing = mentions_missing("risk management plan", "rmp")
    if rmp_missing:
        if "EMA" in region:
            critical.append({"title": "Risk Management Plan (RMP) not included",
                             "guideline": "EMA GVP Module V (RMP)",
                             "comment": "An EU-RMP is mandatory for all EMA MAA submissions."})
            m1_score -= 20
            fix_list.append({"priority": "P1",
                             "action": "Prepare EU-RMP per GVP Module V template",
                             "guideline": "EMA GVP Module V"})
        else:
            warnings_list.append({"title": "Risk Management Plan not included",
                                  "guideline": "FDA REMS guidance / EMA GVP Module V",
                                  "comment": "Consider whether REMS (FDA) or RMP is needed for this product."})
            m1_score -= 10

    # ── Module 2 – Summaries ────────────────────────────────────────────────
    m2_score = 100
    if has_any("quality overall summary", "qos"):
        if "drafted but not final" in text or "not finalised" in text or "not finalized" in text:
            warnings_list.append({"title": "Quality Overall Summary (QOS) not finalised",
                                  "guideline": "ICH M4Q",
                                  "comment": "Finalise the QOS before submission. A draft QOS is not acceptable."})
            m2_score -= 15
            fix_list.append({"priority": "P2",
                             "action": "Finalise the Quality Overall Summary (QOS / Module 2.3)",
                             "guideline": "ICH M4Q"})
        else:
            passed.append({"title": "Quality Overall Summary (QOS) present",
                           "comment": "Module 2.3 drafted."})
    else:
        critical.append({"title": "Quality Overall Summary (QOS) status unclear",
                         "guideline": "ICH M4Q (Module 2.3)",
                         "comment": "QOS is a required CTD component."})
        m2_score -= 20

    if has_any("non-clinical overview", "nonclinical overview"):
        passed.append({"title": "Non-clinical overview complete",
                       "comment": "Module 2.4 present."})
    if has_any("clinical overview"):
        passed.append({"title": "Clinical overview complete",
                       "comment": "Module 2.5 present."})

    iss_missing = mentions_missing("integrated summary of safety", "iss") or "no integrated summary of safety" in text
    ise_missing = mentions_missing("integrated summary of efficacy", "ise") or "no integrated summary of efficacy" in text
    if iss_missing or ise_missing or "no integrated summary" in text:
        if "FDA" in region:
            critical.append({"title": "Integrated Summary of Safety/Efficacy (ISS/ISE) missing",
                             "guideline": "FDA 21 CFR 314.50(d)(5)",
                             "comment": "ISS and ISE are required for FDA NDA submissions."})
            m2_score -= 25
            fix_list.append({"priority": "P1",
                             "action": "Prepare Integrated Summary of Safety (ISS) and Efficacy (ISE)",
                             "guideline": "FDA 21 CFR 314.50(d)(5)"})

    # ── Module 3 – CMC ──────────────────────────────────────────────────────
    m3_score = 100
    if has_any("synthesis route", "synthesis described"):
        passed.append({"title": "Drug substance synthesis route described",
                       "comment": "Module 3.2.S.2 present."})

    # Stability check
    stability_match = re.search(r"stability[^.]*?(\d+)\s*month", text)
    if stability_match:
        months = int(stability_match.group(1))
        if months < 24:
            critical.append({"title": f"Stability data only {months} months",
                             "guideline": "ICH Q1A(R2)",
                             "comment": f"NDA/MAA requires 24 months long-term stability at minimum. Current dossier shows only {months} months."})
            m3_score -= 25
            fix_list.append({"priority": "P1",
                             "action": f"Generate at least {24-months} additional months of long-term stability data",
                             "guideline": "ICH Q1A(R2)"})
        else:
            passed.append({"title": f"Stability data {months} months — meets ICH Q1A",
                           "comment": "Long-term stability requirement met."})

    # Genotoxic impurities (ICH M7)
    if mentions_missing("genotoxic impurity assessment", "ich m7", "m7 assessment") or "no genotoxic" in text:
        critical.append({"title": "No genotoxic (mutagenic) impurity assessment",
                         "guideline": "ICH M7(R2)",
                         "comment": "Mutagenic impurity assessment per ICH M7 is required for small molecules."})
        m3_score -= 15
        fix_list.append({"priority": "P1",
                         "action": "Perform ICH M7 mutagenic impurity assessment ((Q)SAR + purge analysis)",
                         "guideline": "ICH M7(R2)"})

    # Elemental impurities (ICH Q3D)
    if mentions_missing("elemental impurities", "q3d", "elemental impurity") or "no elemental impurities" in text:
        critical.append({"title": "No elemental impurities assessment",
                         "guideline": "ICH Q3D(R2)",
                         "comment": "ICH Q3D risk assessment for elemental impurities is required for all NDAs/MAAs."})
        m3_score -= 15
        fix_list.append({"priority": "P1",
                         "action": "Conduct ICH Q3D elemental impurities risk assessment",
                         "guideline": "ICH Q3D(R2)"})

    if has_any("container closure"):
        passed.append({"title": "Container closure system described",
                       "comment": "Module 3.2.P.7 present."})
    if has_any("dissolution data"):
        passed.append({"title": "Dissolution profile data complete",
                       "comment": "Module 3.2.P.5 dissolution data included."})

    if mentions_missing("comparability protocol") or "no comparability protocol" in text:
        warnings_list.append({"title": "No comparability protocol for post-approval changes",
                              "guideline": "ICH Q5E / FDA Guidance on Comparability Protocols",
                              "comment": "Recommended to expedite future post-approval CMC changes."})
        m3_score -= 5
        fix_list.append({"priority": "P3",
                         "action": "Consider including a comparability protocol for likely post-approval changes",
                         "guideline": "ICH Q5E"})

    # Biologic-specific
    if "biologic" in product_type.lower() or "biosimilar" in product_type.lower():
        if not has_any("comparability"):
            warnings_list.append({"title": "Comparability data not confirmed (biologic)",
                                  "guideline": "ICH Q5E",
                                  "comment": "Biologics require comparability assessment between batches/process changes."})
            m3_score -= 10

    # ── Module 4 – Non-clinical ─────────────────────────────────────────────
    m4_score = 100
    if has_any("pharmacology", "toxicology") and ("complete" in text or "summarised" in text or "summarized" in text):
        passed.append({"title": "Non-clinical pharmacology/PK/tox studies complete",
                       "comment": "Module 4 study reports summarised."})
    else:
        warnings_list.append({"title": "Non-clinical study completeness unclear",
                              "guideline": "ICH M3(R2)",
                              "comment": "Confirm pharmacology, PK, and toxicology study reports are complete in Module 4."})
        m4_score -= 15

    if mentions_missing("juvenile animal study", "juvenile animal data") or "no juvenile animal" in text:
        warnings_list.append({"title": "No juvenile animal study data",
                              "guideline": "ICH S11 / EMA Guideline on Juvenile Animal Studies",
                              "comment": "Required if paediatric use is intended and no equivalent clinical data exists."})
        m4_score -= 10
        fix_list.append({"priority": "P2",
                         "action": "Provide juvenile animal study or scientific justification for waiver",
                         "guideline": "ICH S11"})

    # ── Module 5 – Clinical ─────────────────────────────────────────────────
    m5_score = 100
    if has_any("phase 3 csr", "pivotal phase 3", "phase iii csr"):
        passed.append({"title": "Pivotal Phase 3 CSR complete",
                       "comment": "Pivotal clinical study report present in Module 5."})
    if has_any("phase 1", "phase 2") and "complete" in text:
        passed.append({"title": "Phase 1/2 clinical data complete",
                       "comment": "Earlier-phase studies summarised."})

    if mentions_missing("120-day safety update", "120 day safety update") or "120-day safety update outstanding" in text:
        if "FDA" in region:
            critical.append({"title": "120-day safety update outstanding",
                             "guideline": "FDA 21 CFR 314.50(d)(5)(vi)(b)",
                             "comment": "Required for NDA submissions; must be submitted 120 days after initial submission."})
            m5_score -= 15
            fix_list.append({"priority": "P1",
                             "action": "Prepare 120-day safety update for submission",
                             "guideline": "FDA 21 CFR 314.50(d)(5)(vi)(b)"})

    if mentions_missing("hepatic impairment", "hepatic impairment pk study") or "no dedicated hepatic impairment" in text:
        warnings_list.append({"title": "No dedicated hepatic impairment PK study",
                              "guideline": "FDA Guidance — PK in Patients with Impaired Hepatic Function / EMA CHMP/EWP/2339/02",
                              "comment": "Recommended for small molecules cleared via hepatic metabolism."})
        m5_score -= 10
        fix_list.append({"priority": "P2",
                         "action": "Conduct or justify waiver for hepatic impairment PK study",
                         "guideline": "FDA/EMA hepatic impairment guidance"})

    if mentions_missing("paediatric clinical data", "pediatric clinical data") or "no paediatric clinical" in text or "no pediatric clinical" in text:
        warnings_list.append({"title": "No paediatric clinical data",
                              "guideline": "ICH E11(R1)",
                              "comment": "Address via PIP/PSP plan even if paediatric studies are deferred."})
        m5_score -= 10

    # ── Aggregate scoring ──────────────────────────────────────────────────
    module_scores = [
        ("Module 1 – Administrative", m1_score),
        ("Module 2 – Summaries",      m2_score),
        ("Module 3 – CMC",            m3_score),
        ("Module 4 – Non-clinical",   m4_score),
        ("Module 5 – Clinical",       m5_score),
    ]

    def status_for(s):
        if s >= 80: return "green"
        if s >= 60: return "amber"
        return "red"

    modules = [{"name": n, "score": max(0, s), "status": status_for(s)} for n, s in module_scores]
    overall = round(sum(max(0, s) for _, s in module_scores) / len(module_scores))

    if overall < 50:
        readiness_label = "Not ready"
        readiness_color = "red"
    elif overall < 65:
        readiness_label = "Needs significant work"
        readiness_color = "orange"
    elif overall < 80:
        readiness_label = "Needs work"
        readiness_color = "amber"
    elif overall < 92:
        readiness_label = "Nearly ready"
        readiness_color = "amber"
    else:
        readiness_label = "Ready to file"
        readiness_color = "green"

    # If no specific passes detected, add a generic one to avoid an empty list
    if not passed:
        passed.append({"title": "Dossier content received",
                       "comment": "Content provided for review."})

    # Default fix items if list is short
    if len(fix_list) < 3:
        fix_list.append({"priority": "P3",
                         "action": "Run a final eCTD validation (PDF specs, hyperlinks, granularity)",
                         "guideline": "ICH M2 eCTD specification"})
        fix_list.append({"priority": "P3",
                         "action": "Cross-check Module 1 regional metadata for FDA/EMA",
                         "guideline": "FDA eCTD Technical Conformance / EMA EU eCTD Module 1 spec"})

    return {
        "score": overall,
        "passed_count": len(passed),
        "critical_count": len(critical),
        "warning_count": len(warnings_list),
        "readiness_label": readiness_label,
        "readiness_color": readiness_color,
        "modules": modules,
        "critical": critical,
        "warnings": warnings_list,
        "passed": passed,
        "fix_list": fix_list,
    }


# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    st.success("✅ Running in offline mode — no API key required")
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

# ── Main layout ──────────────────────────────────────────────────────────
st.markdown('<p class="main-header">📋 Submission Readiness Scorecard Agent</p>',
            unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">NDA / MAA · Full CTD dossier · '
    'ICH M4 · FDA · EMA · Instant pass/fail + prioritised fix list</p>',
    unsafe_allow_html=True,
)

# ── Main tabs: Dossier & Timeline ───────────────────────────────────────
main_tab1, main_tab2 = st.tabs(["📄 Dossier Readiness", "📅 Submission Timeline"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1: DOSSIER READINESS SCORECARD
# ════════════════════════════════════════════════════════════════════════════
with main_tab1:
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

    # ── Run agent (local rule-based) ─────────────────────────────────────
    if content_to_run:
        with st.spinner("Analysing dossier against ICH guidelines and regional requirements..."):
            try:
                result = analyze_dossier(content_to_run, region, product_type)
            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

        # ── Render results ──────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("## 📊 Dossier Scorecard Results")

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
            "✅ Dossier scorecard complete. Take a screenshot and post it on LinkedIn! "
            "Tag it #RegulatoryAI #Veeva #eCTD"
        )

# ════════════════════════════════════════════════════════════════════════════
# TAB 2: SUBMISSION TIMELINE & PLAN COMPLETION
# ════════════════════════════════════════════════════════════════════════════
with main_tab2:
    st.markdown("### 📅 Upload and track document submission progress")
    st.markdown(
        "Upload an Excel file with your module documents. "
        "The system tracks completion % per module based on Document IDs submitted. "
        "A missing Document ID counts as a 'miss' (incomplete submission)."
    )

    st.markdown("---")
    st.markdown("**Expected Excel format (headers can be in any column order):**")
    st.markdown(
        """
    | Module Name | Module Title | Document ID | LCM (Lifecycle Mgmt) | File Name of Document | Planned Start Date | Planned Finish Date |
    |-------------|--------------|-------------|---------------------|----------------------|-------------------|-------------------|
    | Module 1 | Administrative | MOD1-001 | Draft | Cover_Letter.pdf | 2026-04-01 | 2026-05-15 |
    | Module 1 | Administrative | MOD1-002 | Final | Form_FDA_356h.pdf | 2026-04-05 | 2026-05-15 |
    | Module 3 | CMC | MOD3-001 | Draft | Drug_Substance.pdf | 2026-04-15 | 2026-07-30 |
    """
    )

    uploaded_file = st.file_uploader(
        "📤 Upload Excel submission tracking",
        type=["xlsx", "xls"],
        help="File must contain: Module Name, Module Title, Document ID, Planned Start Date, Planned Finish Date"
    )

    if uploaded_file is not None:
        try:
            # Read Excel file
            df = pd.read_excel(uploaded_file)

            # Show detected columns
            st.info(f"**✅ Detected columns:** {', '.join(df.columns)}")

            # Use fuzzy matching to find required columns
            module_name_col = find_column(df, ["Module Name", "Module"])
            module_title_col = find_column(df, ["Module Title", "Title"])
            doc_id_col = find_column(df, ["Document ID", "DocID", "ID"])
            start_date_col = find_column(df, ["Planned Start Date", "Planned Start", "Start Date"])
            finish_date_col = find_column(df, ["Planned Finish Date", "Planned Finish", "Finish Date"])

            # Check if all required columns were found
            missing = []
            if not module_name_col:
                missing.append("Module Name")
            if not module_title_col:
                missing.append("Module Title")
            if not doc_id_col:
                missing.append("Document ID")
            if not start_date_col:
                missing.append("Planned Start Date")
            if not finish_date_col:
                missing.append("Planned Finish Date")

            if missing:
                st.error(f"❌ Missing required columns: {', '.join(missing)}\n\nYour columns: {', '.join(df.columns)}")
                st.stop()

            # Rename columns to standard names for processing
            df = df.rename(columns={
                module_name_col: "Module Name",
                module_title_col: "Module Title",
                doc_id_col: "Document ID",
                start_date_col: "Planned Start Date",
                finish_date_col: "Planned Finish Date"
            })

            st.success(f"✅ Matched columns: Module Name, Module Title, Document ID, Planned Start Date, Planned Finish Date")

            # Handle optional columns
            lcm_col = find_column(df, ["LCM", "Lifecycle"])
            file_col = find_column(df, ["File Name", "Document Name"])

            if lcm_col and lcm_col not in ["LCM (Lifecycle Mgmt)"]:
                df = df.rename(columns={lcm_col: "LCM (Lifecycle Mgmt)"})
            elif "LCM (Lifecycle Mgmt)" not in df.columns:
                df["LCM (Lifecycle Mgmt)"] = "—"

            if file_col and file_col not in ["File Name of Document"]:
                df = df.rename(columns={file_col: "File Name of Document"})
            elif "File Name of Document" not in df.columns:
                df["File Name of Document"] = "—"

            # Convert date columns to datetime
            df["Planned Start Date"] = pd.to_datetime(df["Planned Start Date"], errors="coerce")
            df["Planned Finish Date"] = pd.to_datetime(df["Planned Finish Date"], errors="coerce")

            # Calculate timeline metrics
            today = pd.Timestamp(datetime.now().date())

            # Mark documents with missing Document IDs as "Miss"
            df["Status"] = df["Document ID"].apply(
                lambda x: "❌ MISS (No Doc ID)" if pd.isna(x) or (isinstance(x, str) and x.strip() == "") else "✅ Submitted"
            )

            # Calculate days elapsed for each document
            df["Days Planned"] = (df["Planned Finish Date"] - df["Planned Start Date"]).dt.days + 1
            df["Days Elapsed"] = (today - df["Planned Start Date"]).dt.days
            df["Plan Progress %"] = (df["Days Elapsed"] / df["Days Planned"] * 100).clip(0, 100)

            # Document completion (either submitted or missing)
            df["Document Status %"] = df["Status"].apply(lambda x: 100 if "Submitted" in x else 0)

            # Combined completion: average of plan progress and document status
            df["Completion %"] = (df["Plan Progress %"] + df["Document Status %"]) / 2
            df["Completion %"] = df["Completion %"].round(1)

            # Group by Module Name to calculate module-level completion
            module_summary = df.groupby("Module Name").agg({
                "Module Title": "first",
                "Completion %": "mean",
                "Document ID": "count",
                "Status": lambda x: (x == "✅ Submitted").sum()
            }).round(1)
            module_summary.columns = ["Module Title", "Module Completion %", "Total Docs", "Submitted Docs"]
            module_summary["Missing Docs"] = module_summary["Total Docs"] - module_summary["Submitted Docs"]

            # Overall completion
            overall_completion = df["Completion %"].mean().round(1)
            total_docs = len(df)
            submitted_docs = len(df[df["Status"] == "✅ Submitted"])
            missed_docs = total_docs - submitted_docs

            completion_color = (
                "#d32f2f" if overall_completion < 30
                else "#e07b00" if overall_completion < 70
                else "#2e7d32"
            )

            # Readiness label
            if overall_completion < 30:
                readiness_status = "🔴 Early Stage"
            elif overall_completion < 50:
                readiness_status = "🟡 In Progress"
            elif overall_completion < 85:
                readiness_status = "🟠 On Track"
            else:
                readiness_status = "🟢 Near Completion"

            # Display overall metrics
            st.markdown("---")
            st.markdown("## 📊 Document Submission Status")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-label">Overall Completion</div>'
                    f'<div class="metric-value" style="color:{completion_color}">{overall_completion}%</div>'
                    f'</div>', unsafe_allow_html=True
                )
            with col2:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-label">Documents Submitted</div>'
                    f'<div class="metric-value" style="color:#2e7d32">{submitted_docs}/{total_docs}</div>'
                    f'</div>', unsafe_allow_html=True
                )
            with col3:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-label">Missing Documents</div>'
                    f'<div class="metric-value" style="color:#d32f2f">{missed_docs}</div>'
                    f'</div>', unsafe_allow_html=True
                )
            with col4:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-label">Readiness Status</div>'
                    f'<div class="metric-value" style="font-size:1.1rem">{readiness_status}</div>'
                    f'</div>', unsafe_allow_html=True
                )

            st.markdown("<br>", unsafe_allow_html=True)

            # Module-level summary
            st.markdown("#### 📋 Module-level completion")

            for module_name in module_summary.index:
                completion_pct = module_summary.loc[module_name, "Module Completion %"]
                submitted = int(module_summary.loc[module_name, "Submitted Docs"])
                total = int(module_summary.loc[module_name, "Total Docs"])
                missing = int(module_summary.loc[module_name, "Missing Docs"])

                col_a, col_b, col_c = st.columns([2, 1, 2])
                with col_a:
                    st.progress(
                        min(completion_pct / 100, 1.0),
                        text=f"{module_name} ({submitted}/{total} docs)"
                    )
                with col_b:
                    st.markdown(
                        f'<p style="font-weight:600;margin-top:6px">{completion_pct:.1f}%</p>',
                        unsafe_allow_html=True
                    )
                with col_c:
                    if missing > 0:
                        st.markdown(
                            f'<p style="color:#d32f2f;font-weight:600;margin-top:6px">⚠️ {missing} miss</p>',
                            unsafe_allow_html=True
                        )

            st.markdown("---")

            # Document-level detail
            st.markdown("#### 📄 Document-level detail")

            display_df = df[[
                "Module Name", "Module Title", "Document ID",
                "File Name of Document", "Planned Start Date", "Planned Finish Date",
                "Status", "Completion %"
            ]].copy()

            display_df["Planned Start Date"] = display_df["Planned Start Date"].dt.strftime("%Y-%m-%d")
            display_df["Planned Finish Date"] = display_df["Planned Finish Date"].dt.strftime("%Y-%m-%d")
            display_df["Completion %"] = display_df["Completion %"].round(1)

            st.dataframe(display_df, use_container_width=True)

            st.markdown("---")

            # Missing documents summary
            missing_docs_df = df[df["Status"] == "❌ MISS (No Doc ID)"]
            if len(missing_docs_df) > 0:
                st.markdown("#### ❌ Missing Document IDs (Submission Gaps)")
                for idx, row in missing_docs_df.iterrows():
                    st.warning(
                        f"**{row['Module Name']} - {row['Module Title']}** | "
                        f"Due: {row['Planned Finish Date'].strftime('%Y-%m-%d')} | "
                        f"No Document ID assigned"
                    )

            st.markdown("---")

            # Export summary
            st.markdown("#### 📥 Export results")

            summary_data = {
                "Metric": [
                    "Overall Completion %",
                    "Total Documents",
                    "Documents Submitted",
                    "Missing Document IDs",
                    "Readiness Status"
                ],
                "Value": [
                    f"{overall_completion}%",
                    str(total_docs),
                    str(submitted_docs),
                    str(missed_docs),
                    readiness_status
                ]
            }
            summary_df = pd.DataFrame(summary_data)

            csv_buffer = summary_df.to_csv(index=False)
            st.download_button(
                label="📥 Download summary as CSV",
                data=csv_buffer,
                file_name="submission_document_summary.csv",
                mime="text/csv"
            )

            st.success("✅ Document submission tracking complete!")

        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
