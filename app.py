import streamlit as st
import anthropic
import json

st.set_page_config(
    page_title="Submission Readiness Scorecard Agent",
    page_icon="🧬",
    layout="wide"
)

st.title("🧬 Submission Readiness Scorecard Agent")
st.caption("NDA / MAA full dossier checker — powered by Claude AI")

# ── Sidebar inputs ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Configuration")

    region = st.selectbox(
        "Target region",
        ["FDA + EMA (both)", "FDA only", "EMA only"]
    )

    product_type = st.selectbox(
        "Product type",
        ["Small molecule", "Biologic / Biosimilar", "ATMP / Gene therapy"]
    )

    st.divider()
    st.markdown("**About this agent**")
    st.markdown(
        "Checks your NDA/MAA dossier against ICH M4, "
        "ICH Q1A, FDA 21 CFR, and EMA guidelines. "
        "Returns pass/fail, a % readiness score, and a prioritised fix list."
    )
    st.markdown("Built by a regulatory AI builder 🔬")

# ── Demo content ─────────────────────────────────────────────────────────────
DEMO_CONTENT = """NDA submission for small molecule oral tablet (twice daily dosing).
Module 1: Cover letter present. Form FDA 356h complete. No paediatric investigation plan submitted. Risk Management Plan (RMP) not included.
Module 2: Quality Overall Summary drafted but not finalised. Non-clinical overview complete. Clinical overview complete.
Module 3: Drug substance - synthesis route described, specifications set, 3 batches analytical data present. Stability data available for 12 months only (ICH requires 24 months for NDA). Container closure system described.
Drug product - composition and formulation described, manufacturing process validated, finished product specifications set, dissolution data complete.
Module 4: All non-clinical studies (pharmacology, PK, tox) complete and summarised.
Module 5: Pivotal Phase 3 CSR complete. Phase 1/2 data complete. No 120-day safety update. No hepatic impairment PK study."""

# ── Input area ────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📋 Paste dossier content", "✍️ Describe your submission", "🚀 Run demo"])

with tab1:
    paste_input = st.text_area(
        "Paste a summary, table of contents, or available content from your dossier",
        height=200,
        placeholder="e.g. Module 1: Administrative — cover letter present...\nModule 3: CMC — drug substance synthesis described..."
    )

with tab2:
    describe_input = st.text_area(
        "Describe your submission in plain language",
        height=200,
        placeholder="e.g. We have a small molecule NDA targeting FDA. Module 3 is mostly complete but stability data only covers 12 months..."
    )

with tab3:
    st.info("Runs a pre-filled example: small molecule NDA with common gaps — missing paediatric data, 12-month stability only, no RMP.")
    st.code(DEMO_CONTENT, language=None)

run_demo = st.button("▶ Run demo", type="secondary")
run_custom = st.button("🔍 Run scorecard agent", type="primary")

# ── Determine content to analyse ─────────────────────────────────────────────
content_to_run = None
if run_demo:
    content_to_run = DEMO_CONTENT
elif run_custom:
    content_to_run = paste_input.strip() or describe_input.strip()
    if not content_to_run:
        st.warning("Please enter some dossier content in one of the tabs above.")

# ── Run agent ─────────────────────────────────────────────────────────────────
if content_to_run:
    prompt = f"""You are a senior regulatory affairs expert reviewing an NDA/MAA submission dossier for readiness.
Region: {region}.
Product type: {product_type}.

Dossier content provided:
{content_to_run}

Evaluate submission readiness and respond ONLY with a JSON object (no markdown, no backticks) in this exact format:
{{
  "score": <integer 0-100>,
  "passed": <integer>,
  "critical_count": <integer>,
  "readiness_label": "<Not ready | Needs work | Nearly ready | Ready to file>",
  "modules": [
    {{"name": "Module 1", "score": <0-100>, "color": "<green|amber|red>"}},
    {{"name": "Module 2", "score": <0-100>, "color": "<green|amber|red>"}},
    {{"name": "Module 3 CMC", "score": <0-100>, "color": "<green|amber|red>"}},
    {{"name": "Module 4", "score": <0-100>, "color": "<green|amber|red>"}},
    {{"name": "Module 5", "score": <0-100>, "color": "<green|amber|red>"}}
  ],
  "critical": [
    {{"title": "<issue title>", "comment": "<specific regulatory comment referencing ICH/FDA/EMA guideline>"}}
  ],
  "warnings": [
    {{"title": "<issue title>", "comment": "<specific comment>"}}
  ],
  "passed_checks": [
    {{"title": "<what passed>", "comment": "<brief note>"}}
  ],
  "fix_list": [
    {{"priority": "P1", "action": "<specific action to take>"}},
    {{"priority": "P2", "action": "<specific action>"}},
    {{"priority": "P3", "action": "<specific action>"}}
  ]
}}
Be specific and reference real guidelines (ICH M4, ICH Q1A, FDA 21 CFR, EMA guidelines).
Critical issues are blockers. Warnings are recommended. Return 3-6 critical issues, 2-5 warnings, 3-8 passed checks, and 4-8 fix list items."""

    with st.spinner("Analysing dossier against ICH M4 structure..."):
        try:
            client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)
        except json.JSONDecodeError:
            st.error("Could not parse agent response. Please try again.")
            st.stop()
        except Exception as e:
            st.error(f"API error: {e}")
            st.stop()

    # ── Render results ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📊 Scorecard Results")

    # Summary metrics
    score = result.get("score", 0)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Overall score", f"{score}%")
    col2.metric("Checks passed", result.get("passed", 0))
    col3.metric("Critical gaps", result.get("critical_count", 0))
    col4.metric("Readiness", result.get("readiness_label", "—"))

    # Module scores
    st.subheader("📁 Module scores")
    color_map = {"green": "🟢", "amber": "🟡", "red": "🔴"}
    cols = st.columns(5)
    for i, mod in enumerate(result.get("modules", [])):
        with cols[i]:
            icon = color_map.get(mod["color"], "⚪")
            st.metric(f"{icon} {mod['name']}", f"{mod['score']}%")

    # Critical gaps
    st.subheader("🔴 Critical gaps — fix before filing")
    for item in result.get("critical", []):
        with st.expander(f"❌ {item['title']}"):
            st.write(item["comment"])

    # Warnings
    st.subheader("🟡 Warnings — review recommended")
    for item in result.get("warnings", []):
        with st.expander(f"⚠️ {item['title']}"):
            st.write(item["comment"])

    # Passed checks
    st.subheader("🟢 Passed checks")
    for item in result.get("passed_checks", []):
        with st.expander(f"✅ {item['title']}"):
            st.write(item["comment"])

    # Fix list
    st.subheader("📋 Prioritised fix list")
    priority_colors = {"P1": "🔴", "P2": "🟡", "P3": "🟢"}
    for i, fix in enumerate(result.get("fix_list", []), 1):
        icon = priority_colors.get(fix["priority"], "⚪")
        st.markdown(f"**{i}. {icon} [{fix['priority']}]** {fix['action']}")
