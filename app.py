import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from campaign_review import (
    DEFAULT_INPUT,
    Rules,
    build_reconciliation,
    load_submissions,
    review_submissions,
    run_sensitivity,
    total_row,
)
from dashboard_helpers import (
    STATUS_LABELS,
    build_report_files,
    UNCHECKED_SHARE,
    data_quality_summary,
    filter_queue,
    queue_frame,
    unchecked_share,
)

# --- Page Config ---
# "auto" keeps the settings sidebar open on desktop and collapsed on a phone,
# so mobile visitors see the dashboard first and can open the settings when they want.
st.set_page_config(
    page_title="Lead Review | Admin Dashboard",
    layout="wide",
    initial_sidebar_state="auto",
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
    /* Hide the developer items (Deploy button, menu) but NOT the toolbar itself:
       it also holds the button that re-opens the settings sidebar on a phone. */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stAppDeployButton"],
    [data-testid="stToolbarActions"],
    [data-testid="stMainMenu"] {display: none !important;}
    div[data-testid="stDecoration"] {display: none;}

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

    /* Recommendation line */
    .recommendation {
        background: #f8fafc;
        border-left: 4px solid #5b86c5;
        border-radius: 4px;
        padding: 10px 16px;
        margin: 4px 0 14px 0;
        color: #0f172a;
    }
    .recommendation-label {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748b;
    }

    /* Section borders */
    .panel-title {
        font-size: 1rem;
        font-weight: 600;
        color: #0f172a;
        margin-bottom: 0.75rem;
    }
    @media (max-width: 640px) {
        .block-container { padding-top: 3.2rem !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def kpi_card(label: str, value, sub: str, tone: str) -> str:
    """HTML for one headline number. Only numbers and fixed text are inserted."""
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub sub-{tone}">{sub}</div>'
        f"</div>"
    )


def plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


# --- Left Sidebar ---
with st.sidebar:
    st.markdown("### LeadReview")
    st.caption("Campaign Data Admin")
    st.divider()

    st.markdown("**Data Input**")
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], label_visibility="collapsed")

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
    shared_sources_raw = st.text_input(
        "Exempt shared Wi-Fi",
        value="event_qr",
        key="shared",
        help="Comma-separated sources where many people legitimately share one IP, "
        "such as an in-person event. A shared IP there is noted but not held.",
    )
    default_region = st.text_input(
        "Phone region",
        value="ZW",
        key="default_region",
        help="Only ZW (Zimbabwe) numbers can be validated. Any other value switches the "
        "phone-sharing check off, and the page will say so.",
    )

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
# The default file is located relative to campaign_review.py, so the app works
# from any folder. Uploaded data is written to a temporary folder that is always
# deleted afterwards, even if processing fails.
if uploaded_file is not None:
    csv_bytes = uploaded_file.getvalue()
    active_filename = uploaded_file.name
elif DEFAULT_INPUT.exists():
    csv_bytes = DEFAULT_INPUT.read_bytes()
    active_filename = DEFAULT_INPUT.name
else:
    st.error("No CSV uploaded and the default 'campaign_submissions.csv' was not found.")
    st.stop()

try:
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "input.csv"
        csv_path.write_bytes(csv_bytes)
        records = review_submissions(load_submissions(csv_path, default_region), rules)
        recon = build_reconciliation(records)
        totals = total_row(recon)
        sensitivity_rows = run_sensitivity(csv_path, rules, default_region)
except Exception as exc:
    st.error(f"Could not process file: {exc}")
    st.stop()

if totals["raw"] == 0:
    st.warning("The file has column headings but no submissions, so there is nothing to review.")
    st.stop()

report_files = build_report_files(records, recon, sensitivity_rows)

# Build DataFrames
RENAME = {
    "source": "Source",
    "raw": "Raw",
    "provisional_count": "Count",
    "holds": "Held for Review",
    "duplicates": "Duplicates",
    "upper_bound": "Max Possible",
}
COLUMNS = ["Source", "Raw", "Count", "Held for Review", "Duplicates", "Max Possible"]
recon_df = pd.DataFrame(recon).rename(columns=RENAME)[COLUMNS]
recon_with_total = pd.DataFrame(recon + [totals]).rename(columns=RENAME)[COLUMNS]
queue_df = queue_frame(records)

# --- Top Header Bar ---
hdr_left, hdr_right = st.columns([3, 1])
with hdr_left:
    st.markdown("## Reports")
    st.caption(f"Active dataset: **{active_filename}** · {totals['raw']} total submissions")
with hdr_right:
    st.write("")
    st.download_button(
        "Export Report (CSV)",
        data=report_files["source_reconciliation.csv"],
        file_name="source_reconciliation.csv",
        mime="text/csv",
        width="stretch",
    )

# --- Data quality: problems that switch a rule off must never be silent ---
quality = data_quality_summary(records)
affected_rows = len(set(quality["bad_time"]) | set(quality["bad_phone"]))
checks_skipped = unchecked_share(records) >= UNCHECKED_SHARE

# --- What to tell the client ---
if checks_skipped:
    recommendation = (
        f"<b>{totals['provisional_count']}</b> is an unchecked figure: some checks could not run on "
        "this file (see the warning below). Fix the data and re-upload before reporting a number."
    )
elif totals["holds"]:
    recommendation = (
        f"Report <b>{totals['provisional_count']}</b> submissions to the client now. "
        f"This can rise to <b>{totals['upper_bound']}</b> once the {totals['holds']} held "
        f"{plural(totals['holds'], 'entry is', 'entries are')} checked."
    )
else:
    recommendation = (
        f"Report <b>{totals['provisional_count']}</b> submissions to the client. "
        "Nothing is held for review."
    )
if affected_rows and not checks_skipped:
    recommendation += (
        f" {affected_rows} {plural(affected_rows, 'row', 'rows')} could not be fully checked "
        "(see the warning below)."
    )
st.markdown(
    f'<div class="recommendation"><div class="recommendation-label">Recommendation</div>'
    f"{recommendation}</div>",
    unsafe_allow_html=True,
)

# --- Data-quality notices ---
shown_limit = 6


def id_text(ids: list[str]) -> str:
    text = ", ".join(ids[:shown_limit])
    return text + (f" and {len(ids) - shown_limit} more" if len(ids) > shown_limit else "")


if quality["bad_time"]:
    n = len(quality["bad_time"])
    st.warning(
        f"{n} of {totals['raw']} {plural(n, 'row has', 'rows have')} a time the tool cannot read "
        f"({id_text(quality['bad_time'])}). Times must look like 09:15:01. The time-based checks "
        "(shared phone bursts and shared networks) were skipped for these rows, so they may be "
        "counted when they should be held."
    )
if quality["bad_phone"]:
    n = len(quality["bad_phone"])
    st.warning(
        f"{n} {plural(n, 'phone number', 'phone numbers')} could not be validated "
        f"({id_text(quality['bad_phone'])}). Only Zimbabwean numbers are supported, so the "
        "phone-sharing check was skipped for these rows."
    )
if quality["missing_phone"] or quality["missing_other"]:
    parts = []
    if quality["missing_phone"]:
        parts.append(f"no phone number: {id_text(quality['missing_phone'])}")
    if quality["missing_other"]:
        parts.append(f"other missing details: {id_text(quality['missing_other'])}")
    st.info("Some entries are incomplete (" + "; ".join(parts) + "). Checks that need those details could not be applied to them.")

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
    max_pct = round((totals["upper_bound"] / raw_total) * 100)

    # Top KPI Row
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.markdown(kpi_card("Total Submissions", totals["raw"], "100% of raw export", "slate"), unsafe_allow_html=True)
    k2.markdown(kpi_card("Provisional Count", totals["provisional_count"], f"{count_pct}% of total", "green"), unsafe_allow_html=True)
    k3.markdown(kpi_card("Held for Review", totals["holds"], f"{hold_pct}% flagged for check", "amber"), unsafe_allow_html=True)
    k4.markdown(kpi_card("Duplicates Removed", totals["duplicates"], f"{dup_pct}% repeat entries", "slate"), unsafe_allow_html=True)
    k5.markdown(kpi_card("Maximum if Cleared", totals["upper_bound"], f"{max_pct}% if every hold is cleared", "slate"), unsafe_allow_html=True)

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
    search_query = f1.text_input(
        "Search by ID or email", placeholder="e.g. L03 or asha@example.com", key="queue_search"
    )
    all_sources = sorted(queue_df["Source"].unique().tolist())
    selected_sources = f2.multiselect("Source", options=all_sources, default=all_sources)
    decision_options = list(STATUS_LABELS.values())
    selected_statuses = f3.multiselect("Decision", options=decision_options, default=decision_options)

    filtered = filter_queue(queue_df, search_query, selected_sources, selected_statuses)

    st.dataframe(
        filtered,
        width="stretch",
        hide_index=True,
        column_config={
            "Reason": st.column_config.TextColumn("Reason", width="large"),
            "Review notes": st.column_config.TextColumn("Review notes", width="large"),
            "Data quality notes": st.column_config.TextColumn("Data quality notes", width="medium"),
        },
    )
    st.caption(f"Showing {len(filtered)} of {len(queue_df)} submissions.")

    d1, d2, _ = st.columns([1, 1, 2])
    d1.download_button(
        "Download Filtered Queue (CSV)",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="filtered_queue.csv",
        mime="text/csv",
    )
    d2.download_button(
        "Download All Decisions (CSV)",
        data=report_files["reviewed_submissions.csv"],
        file_name="reviewed_submissions.csv",
        mime="text/csv",
    )

# ==================== TAB 3: RULE SENSITIVITY ====================
with tab_sensitivity:
    st.markdown('<div class="panel-title">Impact of Changing Rule Thresholds</div>', unsafe_allow_html=True)
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
    st.caption(
        "Each scenario re-runs the full review on the same data with one setting changed. "
        "When a group sits right on a threshold, a small change moves it between held and counted."
    )
    st.download_button(
        "Download Sensitivity Report (CSV)",
        data=report_files["sensitivity_report.csv"],
        file_name="sensitivity_report.csv",
        mime="text/csv",
    )
