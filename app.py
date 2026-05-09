"""
CTD Submission Scorecard — Planning + Publishing dashboard.

Upload your CTD_Submission_Plan.xlsx and the app produces two creative,
visual scorecards:

  • Planning Scorecard  — based on the "Plan Status" column
                          (Ongoing / Completed / Delayed)
  • Publishing Scorecard — based on the "Publishing Complete" column
                          (Yes / No)

Designed to be deployed to Streamlit Community Cloud so you can
share a public URL with reviewers and management.
"""

import io
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Page config ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CTD Submission Scorecard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #1F3864, #2E7D32);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #666;
        margin-bottom: 1.5rem;
    }
    .scorecard {
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
        border-radius: 16px;
        padding: 1.5rem;
        text-align: center;
        border: 1px solid #e0e0e0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        margin-bottom: 1rem;
    }
    .scorecard-big {
        font-size: 3.5rem;
        font-weight: 800;
        line-height: 1;
        margin: 0.4rem 0;
    }
    .scorecard-label {
        font-size: 0.75rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 600;
    }
    .scorecard-sub {
        font-size: 0.85rem;
        color: #555;
        margin-top: 0.4rem;
    }
    .grade-A  { color: #1a9e5f; }
    .grade-B  { color: #3aa859; }
    .grade-C  { color: #e07b00; }
    .grade-D  { color: #c84d2f; }
    .grade-F  { color: #c62828; }

    .module-card {
        background: white;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        border-left: 4px solid #1F3864;
        margin-bottom: 0.6rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }

    .pill-green  { background:#e8f5e9; color:#1a9e5f; padding:3px 10px; border-radius:14px; font-size:0.78rem; font-weight:600; }
    .pill-amber  { background:#fff3e0; color:#e07b00; padding:3px 10px; border-radius:14px; font-size:0.78rem; font-weight:600; }
    .pill-red    { background:#fdecea; color:#c62828; padding:3px 10px; border-radius:14px; font-size:0.78rem; font-weight:600; }

    .share-box {
        background: #eef5ff;
        border: 1px dashed #4a7bc7;
        border-radius: 10px;
        padding: 0.9rem 1.1rem;
        margin: 0.6rem 0;
        font-size: 0.9rem;
        color: #1F3864;
    }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ─────────────────────────────────────────────────────────────
def grade_from_score(score: float) -> str:
    if score >= 90: return "A"
    if score >= 75: return "B"
    if score >= 60: return "C"
    if score >= 40: return "D"
    return "F"


def grade_class(grade: str) -> str:
    return f"grade-{grade}"


def grade_message(grade: str, kind: str) -> str:
    msgs = {
        ("A", "planning"):   "Outstanding — submission is on track ✨",
        ("B", "planning"):   "Strong progress — minor catch-up needed",
        ("C", "planning"):   "Some risk — focus on delayed items",
        ("D", "planning"):   "Significant delays — escalation recommended",
        ("F", "planning"):   "Critical — submission timeline at risk",
        ("A", "publishing"): "eCTD-ready — most assets published",
        ("B", "publishing"): "Publishing is well advanced",
        ("C", "publishing"): "Mid-stream — keep momentum on publishing",
        ("D", "publishing"): "Publishing lagging — assign more bandwidth",
        ("F", "publishing"): "Publishing has barely started",
    }
    return msgs.get((grade, kind), "—")


@st.cache_data(show_spinner=False)
def load_plan(file_bytes: bytes) -> pd.DataFrame:
    """Read the Submission Plan sheet and return only the deliverable (file)
    rows — i.e. rows where File Name is populated. Folder and module-band
    rows are excluded because they don't represent deliverables."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    sheet_name = "Submission Plan" if "Submission Plan" in xl.sheet_names else xl.sheet_names[0]
    # Header is on row 4 (zero-indexed 3) in the generated workbook
    df = pd.read_excel(xl, sheet_name=sheet_name, header=3)
    df.columns = [str(c).strip() for c in df.columns]

    file_col = next((c for c in df.columns if c.lower().strip() == "file name"), None)
    if file_col is None:
        st.error(f"❌ Could not find a 'File Name' column. Found: {list(df.columns)}")
        st.stop()
    df = df[df[file_col].notna() & (df[file_col].astype(str).str.strip() != "")].copy()

    for col in ("Plan Start Date", "Plan Finish Date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    if "Module" in df.columns:
        df["Module Digit"] = df["Module"].astype(str).str.extract(r"^(\d)", expand=False)
        df["Module Label"] = df["Module Digit"].map({
            "1": "M1 — Administrative",
            "2": "M2 — Summaries",
            "3": "M3 — Quality",
            "4": "M4 — Non-clinical",
            "5": "M5 — Clinical",
        })
    return df


# ── Sidebar ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📊 CTD Submission Scorecard")
    st.caption("Upload your `CTD_Submission_Plan.xlsx` to see live scorecards.")
    st.markdown("---")

    uploaded = st.file_uploader(
        "📤 Upload Submission Plan (.xlsx)",
        type=["xlsx", "xls"],
        help="Use the workbook produced by the CTD plan builder.",
    )

    st.markdown("---")
    st.markdown("**🔗 Share this dashboard**")
    st.markdown(
        '<div class="share-box">'
        "After deploying to Streamlit Cloud, share the public URL "
        "(see <code>README_DEPLOY.md</code> in this repo)."
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.caption(
        "Built for regulatory PMO teams. "
        "Looks at Plan Status (Ongoing/Completed/Delayed) and "
        "Publishing Complete (Yes/No)."
    )


# ── Main header ─────────────────────────────────────────────────────────
st.markdown('<p class="main-header">📊 CTD Submission Scorecard</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Planning + Publishing health-check · '
    "Module-level breakdown · Share-ready visual report</p>",
    unsafe_allow_html=True,
)


# ── If no upload yet ────────────────────────────────────────────────────
if uploaded is None:
    st.info(
        "👈 Upload your `CTD_Submission_Plan.xlsx` from the sidebar to "
        "generate the live scorecards.\n\n"
        "**Expected sheet:** `Submission Plan` with header row on row 4 and "
        "columns: *Module · Name of Section · File Name · Document ID · LCM · "
        "Plan Start Date · Plan Finish Date · Plan Status · Comments · "
        "Publishing Complete*."
    )

    with st.expander("ℹ️  What does each scorecard tell you?"):
        st.markdown("""
**Planning Scorecard** — How the *authoring* timeline is going.
Calculated from the **Plan Status** column:
- ✅ Completed — credit 100%
- 🟡 Ongoing — credit 50%
- 🔴 Delayed — credit 0%

**Publishing Scorecard** — How the *eCTD publishing* is going.
Calculated from the **Publishing Complete** column:
- ✅ Yes — credit 100%
- 🔴 No — credit 0%

A grade A–F is assigned to each scorecard, plus a per-module breakdown
so you can see exactly where the bottleneck is.
""")
    st.stop()


# ── Load + compute ──────────────────────────────────────────────────────
df = load_plan(uploaded.getvalue())

if df.empty:
    st.warning("No deliverable rows were found in the uploaded file.")
    st.stop()

total = len(df)

plan_completed = int((df["Plan Status"] == "Completed").sum())
plan_ongoing   = int((df["Plan Status"] == "Ongoing").sum())
plan_delayed   = int((df["Plan Status"] == "Delayed").sum())
plan_score = round(
    100.0 * (plan_completed * 1.0 + plan_ongoing * 0.5 + plan_delayed * 0.0) / total, 1
)
plan_grade = grade_from_score(plan_score)

pub_yes = int((df["Publishing Complete"] == "Yes").sum())
pub_no  = int((df["Publishing Complete"] == "No").sum())
pub_score = round(100.0 * pub_yes / total, 1)
pub_grade = grade_from_score(pub_score)

last_updated = datetime.now().strftime("%d %b %Y, %H:%M")


# ── Top-line scorecards ─────────────────────────────────────────────────
st.markdown(f"<p style='color:#888;font-size:0.85rem'>Last refreshed: {last_updated} · "
            f"{total} deliverable PDFs across {df['Module Label'].nunique()} modules</p>",
            unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        f"""
        <div class="scorecard">
          <div class="scorecard-label">📝 Planning Scorecard</div>
          <div class="scorecard-big {grade_class(plan_grade)}">{plan_grade}</div>
          <div style="font-size:1.5rem;font-weight:600;color:#444">{plan_score}%</div>
          <div class="scorecard-sub">{grade_message(plan_grade, "planning")}</div>
          <div style="margin-top:0.8rem">
            <span class="pill-green">✅ {plan_completed} Completed</span>
            <span class="pill-amber">🟡 {plan_ongoing} Ongoing</span>
            <span class="pill-red">🔴 {plan_delayed} Delayed</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        f"""
        <div class="scorecard">
          <div class="scorecard-label">📦 Publishing Scorecard</div>
          <div class="scorecard-big {grade_class(pub_grade)}">{pub_grade}</div>
          <div style="font-size:1.5rem;font-weight:600;color:#444">{pub_score}%</div>
          <div class="scorecard-sub">{grade_message(pub_grade, "publishing")}</div>
          <div style="margin-top:0.8rem">
            <span class="pill-green">✅ {pub_yes} Published</span>
            <span class="pill-red">🔴 {pub_no} Not yet</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Visual breakdowns (gauge + donuts) ──────────────────────────────────
st.markdown("### 🎯 Visual breakdown")
gcol1, gcol2, gcol3 = st.columns([1.2, 1, 1])

with gcol1:
    combined = round((plan_score + pub_score) / 2, 1)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=combined,
        number={"suffix": "%", "font": {"size": 40, "color": "#1F3864"}},
        title={"text": "<b>Overall Submission Health</b><br><span style='font-size:0.75em;color:#888'>average of planning + publishing</span>",
               "font": {"size": 14}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#bbb"},
            "bar": {"color": "#1F3864", "thickness": 0.25},
            "bgcolor": "white",
            "borderwidth": 1,
            "bordercolor": "#e0e0e0",
            "steps": [
                {"range": [0, 40],  "color": "#fdecea"},
                {"range": [40, 60], "color": "#fff3e0"},
                {"range": [60, 75], "color": "#fff8d6"},
                {"range": [75, 90], "color": "#e8f5e9"},
                {"range": [90, 100],"color": "#c6efce"},
            ],
            "threshold": {"line": {"color": "red", "width": 3}, "thickness": 0.8, "value": combined},
        },
    ))
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)

with gcol2:
    plan_df = pd.DataFrame({
        "Status": ["Completed", "Ongoing", "Delayed"],
        "Count":  [plan_completed, plan_ongoing, plan_delayed],
    })
    fig = px.pie(plan_df, values="Count", names="Status", hole=0.55,
                 color="Status",
                 color_discrete_map={"Completed": "#1a9e5f",
                                     "Ongoing":   "#e0a000",
                                     "Delayed":   "#c62828"},
                 title="<b>Planning Status</b>")
    fig.update_traces(textposition="inside", textinfo="value+percent")
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=50, b=10),
                      title_font_size=14, showlegend=True,
                      legend=dict(orientation="h", yanchor="bottom", y=-0.15))
    st.plotly_chart(fig, use_container_width=True)

with gcol3:
    pub_df = pd.DataFrame({
        "Published": ["Yes", "No"],
        "Count":     [pub_yes, pub_no],
    })
    fig = px.pie(pub_df, values="Count", names="Published", hole=0.55,
                 color="Published",
                 color_discrete_map={"Yes": "#1a9e5f", "No": "#c62828"},
                 title="<b>Publishing Status</b>")
    fig.update_traces(textposition="inside", textinfo="value+percent")
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=50, b=10),
                      title_font_size=14, showlegend=True,
                      legend=dict(orientation="h", yanchor="bottom", y=-0.15))
    st.plotly_chart(fig, use_container_width=True)


# ── Module-level breakdown ──────────────────────────────────────────────
st.markdown("### 📚 Module-by-module breakdown")

module_summary = (
    df.groupby("Module Label")
      .apply(lambda g: pd.Series({
          "Total":          len(g),
          "Plan Completed": (g["Plan Status"] == "Completed").sum(),
          "Plan Ongoing":   (g["Plan Status"] == "Ongoing").sum(),
          "Plan Delayed":   (g["Plan Status"] == "Delayed").sum(),
          "Pub Yes":        (g["Publishing Complete"] == "Yes").sum(),
          "Pub No":         (g["Publishing Complete"] == "No").sum(),
      }), include_groups=False)
      .reset_index()
)
module_summary["Plan Score"] = (
    100.0 * (module_summary["Plan Completed"] * 1.0
             + module_summary["Plan Ongoing"] * 0.5)
    / module_summary["Total"].replace(0, 1)
).round(1)
module_summary["Pub Score"] = (
    100.0 * module_summary["Pub Yes"] / module_summary["Total"].replace(0, 1)
).round(1)

mcol1, mcol2 = st.columns(2)

with mcol1:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Completed", y=module_summary["Module Label"],
        x=module_summary["Plan Completed"], orientation="h",
        marker=dict(color="#1a9e5f"),
        text=module_summary["Plan Completed"], textposition="inside",
    ))
    fig.add_trace(go.Bar(
        name="Ongoing", y=module_summary["Module Label"],
        x=module_summary["Plan Ongoing"], orientation="h",
        marker=dict(color="#e0a000"),
        text=module_summary["Plan Ongoing"], textposition="inside",
    ))
    fig.add_trace(go.Bar(
        name="Delayed", y=module_summary["Module Label"],
        x=module_summary["Plan Delayed"], orientation="h",
        marker=dict(color="#c62828"),
        text=module_summary["Plan Delayed"], textposition="inside",
    ))
    fig.update_layout(
        barmode="stack",
        title="<b>📝 Planning by Module</b>",
        height=350, margin=dict(l=10, r=10, t=50, b=10),
        xaxis_title="# Deliverables",
        legend=dict(orientation="h", yanchor="bottom", y=-0.25),
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)

with mcol2:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Published",     y=module_summary["Module Label"],
        x=module_summary["Pub Yes"], orientation="h",
        marker=dict(color="#1a9e5f"),
        text=module_summary["Pub Yes"], textposition="inside",
    ))
    fig.add_trace(go.Bar(
        name="Not Published", y=module_summary["Module Label"],
        x=module_summary["Pub No"], orientation="h",
        marker=dict(color="#c62828"),
        text=module_summary["Pub No"], textposition="inside",
    ))
    fig.update_layout(
        barmode="stack",
        title="<b>📦 Publishing by Module</b>",
        height=350, margin=dict(l=10, r=10, t=50, b=10),
        xaxis_title="# Deliverables",
        legend=dict(orientation="h", yanchor="bottom", y=-0.25),
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Module score-cards strip ────────────────────────────────────────────
st.markdown("### 🏆 Module scorecards")
score_cols = st.columns(len(module_summary))
for i, (_, row) in enumerate(module_summary.iterrows()):
    with score_cols[i]:
        plan_g = grade_from_score(row["Plan Score"])
        pub_g  = grade_from_score(row["Pub Score"])
        bar_color = {"1": "#1F4E79", "2": "#2E7D32", "3": "#B7472A",
                     "4": "#6A4C93", "5": "#00838F"}.get(
            str(row["Module Label"])[1:2], "#1F3864"
        )
        st.markdown(
            f"""
            <div class="module-card" style="border-left-color:{bar_color}">
              <div style="font-weight:700;color:{bar_color};font-size:0.95rem">
                {row['Module Label']}
              </div>
              <div style="display:flex;justify-content:space-between;margin-top:0.6rem">
                <div style="text-align:center;flex:1">
                  <div style="font-size:0.7rem;color:#888;text-transform:uppercase">Plan</div>
                  <div style="font-size:1.6rem;font-weight:700"
                       class="{grade_class(plan_g)}">{plan_g}</div>
                  <div style="font-size:0.78rem;color:#666">{row['Plan Score']:.0f}%</div>
                </div>
                <div style="text-align:center;flex:1;border-left:1px solid #eee">
                  <div style="font-size:0.7rem;color:#888;text-transform:uppercase">Publish</div>
                  <div style="font-size:1.6rem;font-weight:700"
                       class="{grade_class(pub_g)}">{pub_g}</div>
                  <div style="font-size:0.78rem;color:#666">{row['Pub Score']:.0f}%</div>
                </div>
              </div>
              <div style="font-size:0.72rem;color:#999;margin-top:0.5rem;text-align:center">
                {int(row['Total'])} deliverables
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── Delayed items watch-list ────────────────────────────────────────────
st.markdown("### 🚨 Delayed items watch-list")
delayed_df = df[df["Plan Status"] == "Delayed"][
    ["Module", "Name of Section", "File Name", "Document ID",
     "Plan Start Date", "Plan Finish Date", "Publishing Complete"]
].copy()

if delayed_df.empty:
    st.success("🎉 No delayed deliverables. Excellent.")
else:
    delayed_df = delayed_df.sort_values("Plan Finish Date").reset_index(drop=True)
    delayed_df["Plan Start Date"]  = delayed_df["Plan Start Date"].dt.strftime("%Y-%m-%d")
    delayed_df["Plan Finish Date"] = delayed_df["Plan Finish Date"].dt.strftime("%Y-%m-%d")
    delayed_df["Name of Section"] = delayed_df["Name of Section"].astype(str).str.strip()
    st.dataframe(delayed_df, use_container_width=True, hide_index=True)
    st.caption(f"⏱️ {len(delayed_df)} delayed deliverables — sorted by earliest planned finish date.")


# ── Timeline (Gantt) ────────────────────────────────────────────────────
st.markdown("### 📅 Submission timeline (Gantt)")
gantt_df = df[df["Plan Start Date"].notna() & df["Plan Finish Date"].notna()].copy()
if not gantt_df.empty:
    gantt_df = gantt_df.sort_values("Plan Start Date")
    fig = px.timeline(
        gantt_df,
        x_start="Plan Start Date",
        x_end="Plan Finish Date",
        y="Module Label",
        color="Plan Status",
        color_discrete_map={"Completed": "#1a9e5f",
                            "Ongoing":   "#e0a000",
                            "Delayed":   "#c62828"},
        hover_data=["Document ID", "File Name", "Name of Section"],
    )
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_layout(
        height=380, margin=dict(l=10, r=10, t=20, b=10),
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=-0.18),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Raw data + downloadable summary ─────────────────────────────────────
st.markdown("### 📄 Underlying data & exports")
tab_summary, tab_raw = st.tabs(["📊 Module summary table", "📋 Full deliverable list"])

with tab_summary:
    display_summary = module_summary.copy()
    display_summary["Plan Score"]  = display_summary["Plan Score"].astype(str) + "%"
    display_summary["Pub Score"]   = display_summary["Pub Score"].astype(str) + "%"
    st.dataframe(display_summary, use_container_width=True, hide_index=True)

    csv = module_summary.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Download module summary (CSV)",
        data=csv,
        file_name=f"submission_scorecard_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

with tab_raw:
    show_cols = [c for c in
                 ["Module", "Name of Section", "File Name", "Document ID", "LCM",
                  "Plan Start Date", "Plan Finish Date", "Plan Status",
                  "Publishing Complete"]
                 if c in df.columns]
    raw_view = df[show_cols].copy()
    raw_view["Name of Section"] = raw_view["Name of Section"].astype(str).str.strip()
    for c in ("Plan Start Date", "Plan Finish Date"):
        if c in raw_view.columns:
            raw_view[c] = raw_view[c].dt.strftime("%Y-%m-%d")
    st.dataframe(raw_view, use_container_width=True, hide_index=True)


# ── Footer / share ──────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#888;font-size:0.85rem'>"
    "🔗 Deploy to Streamlit Community Cloud to share a public link · "
    "See <code>README_DEPLOY.md</code></p>",
    unsafe_allow_html=True,
)
