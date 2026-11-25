"""Streamlit interface for the campaign lead review tool.

Run with:  streamlit run app.py

This file only handles the screen. Every rule, threshold and report comes from
campaign_review.py in this repository, and the sample data is the repository's
own campaign_submissions.csv, so the web app and the command-line tool always
give identical answers.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from campaign_review import (
    DEFAULT_INPUT,
    Rules,
    build_reconciliation,
    load_submissions,
    review_submissions,
    run_sensitivity,
    total_row,
    write_reconciliation_report,
    write_sensitivity_report,
    write_submission_report,
)

DECISION_LABEL = {"count": "count", "duplicate": "duplicate", "hold_for_review": "hold for review"}
DECISION_COLOUR = {"count": "#E2F0D9", "duplicate": "#FBE5D6", "hold for review": "#FFF2CC"}

st.set_page_config(page_title="Campaign lead review", page_icon="🔎", layout="wide")


# --------------------------------------------------------------------------
# Analysis (cached so moving around the page does not re-run the review)
# --------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def analyse(csv_bytes: bytes, burst_s: int, min_phone: int, ip_s: int, min_ip: int, shared: tuple[str, ...]):
    """Run the repository's own review and write its own CSV reports to a temp folder."""
    rules = Rules(
        burst_window_seconds=burst_s,
        min_shared_phone_entries=min_phone,
        ip_window_seconds=ip_s,
        min_shared_ip_entries=min_ip,
        shared_network_sources=frozenset(shared),
    )
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        source = folder / "input.csv"
        source.write_bytes(csv_bytes)

        records = review_submissions(load_submissions(source), rules)
        reconciliation = build_reconciliation(records)
        sensitivity = run_sensitivity(source, rules)

        # Same writers the command-line tool uses, so downloads match its output exactly.
        out = folder / "out"
        write_submission_report(records, out / "reviewed_submissions.csv")
        write_reconciliation_report(reconciliation, out / "source_reconciliation.csv")
        write_sensitivity_report(sensitivity, out / "sensitivity_report.csv")
        files = {path.name: path.read_bytes() for path in out.iterdir()}

    return records, reconciliation, sensitivity, files


def decisions_frame(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ID": r["id"],
            "Time": r["time"],
            "Email": r["email"],
            "Phone": r["phone"] or "(missing)",
            "IP": r["ip"],
            "Source": r["source"],
            "Decision": DECISION_LABEL[r["status"]],
            "Related IDs": ", ".join(r["related_ids"]) or "-",
            "Reason": r["reason"],
            "Review notes": "; ".join(r["review_notes"]) or "-",
            "Data quality": "; ".join(r["data_quality_notes"]) or "-",
        }
        for r in records
    )


def colour_rows(row: pd.Series) -> list[str]:
    return [f"background-color: {DECISION_COLOUR[row['Decision']]}; color: #000000"] * len(row)


# --------------------------------------------------------------------------
# Sidebar: data and rules
# --------------------------------------------------------------------------

st.title("Campaign lead review")
st.caption(
    "Rule-based screening of campaign submissions. **Hold for review means uncertain, "
    "not fraudulent**: there are no confirmed fraud labels, so nothing here proves fraud."
)

with st.sidebar:
    st.header("1. Data")
    choice = st.radio("Input", ["Sample data", "Upload a CSV"], label_visibility="collapsed")
    csv_bytes = None
    if choice == "Sample data":
        if DEFAULT_INPUT.exists():
            csv_bytes = DEFAULT_INPUT.read_bytes()
        else:
            st.error(f"Sample file not found at {DEFAULT_INPUT}")
    else:
        uploaded = st.file_uploader("CSV with columns id, time, email, phone, ip, source", type="csv")
        if uploaded is not None:
            csv_bytes = uploaded.getvalue()

    st.header("2. Rules")
    st.caption("Change a setting and the whole report updates.")
    burst_s = st.number_input("Phone burst window (seconds)", min_value=0, value=10, step=1, key="burst_s")
    min_phone = st.number_input("Emails sharing a phone to hold", min_value=2, value=3, step=1, key="min_phone")
    ip_s = st.number_input("IP cluster window (seconds)", min_value=0, value=10, step=1, key="ip_s")
    min_ip = st.number_input("Emails sharing an IP to hold", min_value=2, value=3, step=1, key="min_ip")
    shared_text = st.text_input(
        "Shared-network sources (comma-separated)",
        value="event_qr",
        key="shared",
        help="Sources where many people legitimately share one IP, such as event Wi-Fi. "
        "A shared IP there is noted but not held.",
    )

if csv_bytes is None:
    st.info("Choose the sample data or upload a CSV in the sidebar to start.")
    st.stop()

shared = tuple(sorted(s.strip() for s in shared_text.split(",") if s.strip()))

try:
    records, reconciliation, sensitivity, files = analyse(
        csv_bytes, int(burst_s), int(min_phone), int(ip_s), int(min_ip), shared
    )
except ValueError as error:
    st.error(f"Could not read this file: {error}")
    st.stop()

total = total_row(reconciliation)

# --------------------------------------------------------------------------
# Headline numbers
# --------------------------------------------------------------------------

st.success(
    f"Share **{total['provisional_count']}** with the client as the provisional count. "
    f"It could rise to **{total['upper_bound']}** if the {total['holds']} held submission(s) are cleared."
    if total["holds"]
    else f"Provisional count: **{total['provisional_count']}**. Nothing is held for review."
)

columns = st.columns(5)
columns[0].metric("Raw submissions", total["raw"])
columns[1].metric("Duplicates", total["duplicates"])
columns[2].metric("Held for review", total["holds"])
columns[3].metric("Provisional count", total["provisional_count"], help="Conservative figure to share with the client.")
columns[4].metric("Upper bound", total["upper_bound"], help="The figure if every held submission is later cleared.")

tab_decisions, tab_sources, tab_change, tab_rules = st.tabs(
    ["Decisions", "Report by source", "Change a rule", "How the rules work"]
)

# --------------------------------------------------------------------------
# Decisions
# --------------------------------------------------------------------------

with tab_decisions:
    frame = decisions_frame(records)
    left, right = st.columns(2)
    wanted_decisions = left.multiselect("Decision", list(DECISION_LABEL.values()), default=list(DECISION_LABEL.values()))
    wanted_sources = right.multiselect("Source", sorted(frame["Source"].unique()), default=sorted(frame["Source"].unique()))

    shown = frame[frame["Decision"].isin(wanted_decisions) & frame["Source"].isin(wanted_sources)]
    st.dataframe(shown.style.apply(colour_rows, axis=1), hide_index=True)
    st.caption(f"Showing {len(shown)} of {len(frame)} submissions. Duplicates link to the earliest matching entry.")

    st.download_button(
        "Download decisions (CSV)", files["reviewed_submissions.csv"], "reviewed_submissions.csv", "text/csv"
    )

# --------------------------------------------------------------------------
# Report by source
# --------------------------------------------------------------------------

with tab_sources:
    report = pd.DataFrame(reconciliation + [total]).rename(
        columns={
            "source": "Source", "raw": "Raw", "duplicates": "Duplicates", "holds": "Held for review",
            "provisional_count": "Provisional count", "upper_bound": "Upper bound",
        }
    )
    st.dataframe(report, hide_index=True)
    st.caption("Every source reconciles: raw = duplicates + held for review + provisional count.")

    chart = report[report["Source"] != "TOTAL"].set_index("Source")[["Provisional count", "Held for review", "Duplicates"]]
    st.bar_chart(chart)

    st.download_button(
        "Download report by source (CSV)", files["source_reconciliation.csv"], "source_reconciliation.csv", "text/csv"
    )

# --------------------------------------------------------------------------
# Change a rule
# --------------------------------------------------------------------------

with tab_change:
    st.write(
        "The same data re-run with one threshold or rule changed, compared with the rules in the sidebar. "
        "This shows how much the client's number depends on the choices made."
    )
    totals = pd.DataFrame([r for r in sensitivity if r["source"] == "TOTAL"])
    view = totals[["scenario", "provisional_count", "holds", "provisional_vs_baseline", "rows_changed", "setting"]].rename(
        columns={
            "scenario": "Scenario", "setting": "What changed", "provisional_count": "Provisional count",
            "holds": "Held", "provisional_vs_baseline": "Change vs baseline", "rows_changed": "Rows that moved",
        }
    )
    st.dataframe(view, hide_index=True)
    st.bar_chart(view.set_index("Scenario")["Provisional count"])
    st.caption(
        "A burst that sits right on a threshold flips from held to counted with a small change, "
        "and removing the event Wi-Fi exemption holds every legitimate event entry."
    )

    st.download_button(
        "Download sensitivity report (CSV)", files["sensitivity_report.csv"], "sensitivity_report.csv", "text/csv"
    )

# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

with tab_rules:
    st.markdown(
        """
Each submission gets exactly one decision, in this order of precedence.

| # | Rule | Decision |
|---|---|---|
| 1 | Same email (trimmed, lowercased) as an earlier submission | **duplicate**, linked to the earliest |
| 2 | Several different emails share one phone number, from one source, within the burst window | **hold for review** |
| 3 | Several different emails share one IP, from one source, within the window, unless the source is a shared network | **hold for review** |
| 4 | Shared IP inside a shared-network source such as event Wi-Fi | **count**, with a review note |
| 5 | Anything else | **count** |

Zimbabwean phone numbers are standardised, so `+263771000001` and `0771000001` are the same number.
A blank phone is missing data and never matches anything. A hold is reversible: it means
"look at this before reporting it", not "this is fraud".
"""
    )
