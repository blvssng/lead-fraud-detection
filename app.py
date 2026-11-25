from pathlib import Path
import tempfile
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from campaign_review import (
    Rules,
    build_reconciliation,
    load_submissions,
    review_submissions,
    run_sensitivity,
    total_row,
)

# --- Page Config ---
st.set_page_config(
    page_title="Lead Review | Admin Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Clean SaaS Admin Styling ---
st.markdown(
    """
    <style>
    /* Main background and typography */
    .stApp {
        background-color: #ffffff;
        color: #1e293b;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }
    /* Hide default Streamlit header clutter */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* KPI Card styling */
    .kpi-card {
        padding: 12px 4px;
    }
    .kpi-label {
        font-size: 0.82rem;
        color: #64748b;
        font-weight: 500;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 2rem;
        font-weight: 700;
        color: #0f172a;
        line-height: 1.1;
    }
    .kpi-sub {
        font-size: 0.78rem;
        margin-top: 6px;
        font-weight: 500;
    }
    .sub-green { color: #16a34a; }
    .sub-amber { color: #d97706; }
    .sub-slate { color: #64748b; }

    /* Section borders */
    .panel-title {
        font-size: 1rem;
        font-weight: 600;
        color: #0f172a;
        margin-bottom: 0.75rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

STATUS_LABELS = {
    "count": "Count",
    "duplicate": "Duplicate",
    "hold_for_review": "Hold for Review",
}

# --- Left Sidebar ---
with st.sidebar:
    st.markdown("### LeadReview")
    st.caption("Campaign Data Admin")
    st.divider()

    st.markdown("**Data Input**")
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], label_visibility="collapsed")
    default_csv = Path("campaign_submissions.csv")

    st.divider()
    st.markdown("**Rule Settings**")
    burst_seconds = st.number_input(
        "Phone burst window (sec)", min_value=0, max_value=300, value=10, key="burst_seconds"
    )
    min_phone = st.number_input(
        "Min emails (shared phone)", min_value=2, max_value=10, value=3, key="min_phone"
    )
    ip_seconds = st.number_input(
        "IP cluster window (sec)", min_value=0, max_value=300, value=10, key="ip_seconds"
    )
    min_ip = st.number_input(
        "Min emails (shared IP)", min_value=2, max_value=10, value=3, key="min_ip"
    )
    shared_sources_raw = st.text_input("Exempt shared Wi-Fi", value="event_qr", key="shared")
    default_region = st.text_input("Phone region", value="ZW", key="default_region")

rules = Rules(
    burst_window_seconds=int(burst_seconds),
    min_shared_phone_entries=int(min_phone),
    ip_window_seconds=int(ip_seconds),
    min_shared_ip_entries=int(min_ip),
    shared_network_sources=frozenset(
        s.strip() for s in shared_sources_raw.split(",") if s.strip()
    ),
)

# --- Load & Evaluate Data ---
temp_path = None
if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(uploaded_file.getvalue())
        temp_path = Path(tmp.name)
    csv_path = temp_path
    active_filename = uploaded_file.name
elif default_csv.exists():
    csv_path = default_csv
    active_filename = default_csv.name
else:
    st.error("No CSV uploaded and default 'campaign_submissions.csv' was not found.")
    st.stop()

try:
    records = review_submissions(load_submissions(csv_path, default_region), rules)
    recon = build_reconciliation(records)
    totals = total_row(recon)
except Exception as exc:
    st.error(f"Could not process file: {exc}")
    st.stop()

# Build DataFrames
recon_df = pd.DataFrame(recon).rename(
    columns={
        "source": "Source",
        "raw": "Raw",
        "provisional_count": "Count",
        "holds": "Held for Review",
        "duplicates": "Duplicates",
        "upper_bound": "Max Possible",
    }
)[["Source", "Raw", "Count", "Held for Review", "Duplicates", "Max Possible"]]

recon_with_total = pd.DataFrame(recon + [totals]).rename(
    columns={
        "source": "Source",
        "raw": "Raw",
        "provisional_count": "Count",
        "holds": "Held for Review",
        "duplicates": "Duplicates",
        "upper_bound": "Max Possible",
    }
)[["Source", "Raw", "Count", "Held for Review", "Duplicates", "Max Possible"]]

queue_rows = [
    {
        "ID": r["id"],
        "Time": r["time"],
        "Source": r["source"] or "(missing)",
        "Email": r["email"],
        "Phone": r["phone_normalised"] or r["phone"] or "—",
        "Decision": STATUS_LABELS.get(r["status"], r["status"]),
        "Reason": r["reason"],
        "Related IDs": ", ".join(r["related_ids"]) or "—",
    }
    for r in records
]
queue_df = pd.DataFrame(queue_rows)

# --- Top Header Bar ---
hdr_left, hdr_right = st.columns([3, 1])
with hdr_left:
    st.markdown("## Reports")
    st.caption(f"Active dataset: **{active_filename}** · {totals['raw']} total submissions")
with hdr_right:
    st.write("")
    st.download_button(
        "Export Report (CSV)",
        data=recon_with_total.to_csv(index=False).encode("utf-8"),
        file_name="source_reconciliation.csv",
        mime="text/csv",
        width="stretch",
    )

# --- Top Navigation Tabs ---
tab_summary, tab_detailed, tab_sensitivity = st.tabs(
    ["Summary", "Detailed Queue", "Rule Sensitivity"]
)

# ==================== TAB 1: SUMMARY ====================
with tab_summary:
    raw_total = max(totals["raw"], 1)
    count_pct = round((totals["provisional_count"] / raw_total) * 100)
    hold_pct = round((totals["holds"] / raw_total) * 100)
    dup_pct = round((totals["duplicates"] / raw_total) * 100)

    # Top KPI Row
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(
        f"""<div class="kpi-card">
            <div class="kpi-label">Total Submissions</div>
            <div class="kpi-value">{totals['raw']}</div>
            <div class="kpi-sub sub-slate">100% of raw export</div>
        </div>""",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"""<div class="kpi-card">
            <div class="kpi-label">Ready to Report (Count)</div>
            <div class="kpi-value">{totals['provisional_count']}</div>
            <div class="kpi-sub sub-green">{count_pct}% of total</div>
        </div>""",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"""<div class="kpi-card">
            <div class="kpi-label">Held for Review</div>
            <div class="kpi-value">{totals['holds']}</div>
            <div class="kpi-sub sub-amber">{hold_pct}% flagged for check</div>
        </div>""",
        unsafe_allow_html=True,
    )
    k4.markdown(
        f"""<div class="kpi-card">
            <div class="kpi-label">Duplicates Removed</div>
            <div class="kpi-value">{totals['duplicates']}</div>
            <div class="kpi-sub sub-slate">{dup_pct}% repeat entries</div>
        </div>""",
        unsafe_allow_html=True,
    )

    st.divider()

    # Main Grouped Bar Chart (Clean SaaS style)
    st.markdown('<div class="panel-title">Submissions by Source</div>', unsafe_allow_html=True)
    melted = recon_df.melt(
        id_vars="Source",
        value_vars=["Count", "Held for Review", "Duplicates"],
        var_name="Status",
        value_name="Submissions",
    )
    bar_fig = px.bar(
        melted,
        x="Source",
        y="Submissions",
        color="Status",
        barmode="group",
        color_discrete_map={
            "Count": "#5b86c5",
            "Held for Review": "#f08070",
            "Duplicates": "#93b096",
        },
        height=300,
    )
    bar_fig.update_layout(
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=None),
        xaxis=dict(title=None, showgrid=False),
        yaxis=dict(title=None, gridcolor="#f1f5f9", dtick=1),
        bargap=0.35,
        bargroupgap=0.12,
    )
    bar_fig.update_traces(marker_line_width=0, width=0.22)
    st.plotly_chart(bar_fig, width="stretch")

    st.divider()

    # Bottom Split: Source Table (Left) + Donut Chart (Right)
    left_col, right_col = st.columns([1.6, 1])

    with left_col:
        st.markdown('<div class="panel-title">Reconciled Report by Source</div>', unsafe_allow_html=True)
        st.dataframe(recon_with_total, width="stretch", hide_index=True)

    with right_col:
        st.markdown('<div class="panel-title">Decision Share</div>', unsafe_allow_html=True)
        donut_fig = go.Figure(
            data=[
                go.Pie(
                    labels=["Count", "Held for Review", "Duplicates"],
                    values=[
                        totals["provisional_count"],
                        totals["holds"],
                        totals["duplicates"],
                    ],
                    hole=0.62,
                    marker_colors=["#5b86c5", "#f08070", "#93b096"],
                    textinfo="percent",
                    hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
                )
            ]
        )
        donut_fig.update_layout(
            height=260,
            margin=dict(l=10, r=10, t=10, b=10),
            showlegend=True,
            legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5),
            paper_bgcolor="#ffffff",
        )
        st.plotly_chart(donut_fig, width="stretch")

# ==================== TAB 2: DETAILED QUEUE ====================
with tab_detailed:
    f1, f2, f3 = st.columns([2, 1, 1])
    search_query = f1.text_input("Search by ID or email", placeholder="e.g. L03 or asha@example.com")
    all_sources = sorted(queue_df["Source"].unique().tolist())
    selected_sources = f2.multiselect("Source", options=all_sources, default=all_sources)
    selected_statuses = f3.multiselect(
        "Decision",
        options=["Count", "Hold for Review", "Duplicate"],
        default=["Count", "Hold for Review", "Duplicate"],
    )

    filtered = queue_df[
        queue_df["Source"].isin(selected_sources) & queue_df["Decision"].isin(selected_statuses)
    ]
    if search_query.strip():
        q = search_query.strip().lower()
        filtered = filtered[
            filtered["ID"].str.lower().str.contains(q)
            | filtered["Email"].str.lower().str.contains(q)
        ]

    st.dataframe(filtered, width="stretch", hide_index=True)

    st.download_button(
        "Download Filtered Queue (CSV)",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="reviewed_submissions.csv",
        mime="text/csv",
    )

# ==================== TAB 3: RULE SENSITIVITY ====================
with tab_sensitivity:
    st.markdown('<div class="panel-title">Impact of Changing Rule Thresholds</div>', unsafe_allow_html=True)
    sensitivity_rows = run_sensitivity(csv_path, rules, default_region)
    sens_df = pd.DataFrame(
        [
            {
                "Scenario": row["setting"],
                "Count": row["provisional_count"],
                "Held for Review": row["holds"],
                "Change vs Baseline": f"{row['provisional_vs_baseline']:+d}",
                "Affected IDs": row["rows_changed"] or "None",
            }
            for row in sensitivity_rows
            if row["source"] == "TOTAL"
        ]
    )
    st.dataframe(sens_df, width="stretch", hide_index=True)

if temp_path and temp_path.exists():
    temp_path.unlink(missing_ok=True)