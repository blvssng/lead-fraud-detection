"""Pure helper functions for the dashboard (no Streamlit imports).

Keeping these out of app.py means they can be unit-tested directly, and the
dashboard stays a thin layer over campaign_review.py.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from campaign_review import (
    write_reconciliation_report,
    write_sensitivity_report,
    write_submission_report,
)

# If at least this share of rows has an unreadable time or phone number, the review
# rules that depend on them barely ran, so the dashboard stops recommending a number.
# This is a judgement call, not a statistical rule.
UNCHECKED_SHARE = 0.2

STATUS_LABELS = {
    "count": "Count",
    "duplicate": "Duplicate",
    "hold_for_review": "Hold for Review",
}


def queue_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """One row per submission, with the notes a reviewer needs to understand each decision."""
    rows = []
    for r in records:
        if r["status"] == "count":
            # The tool's default reason ("no rule triggered") would be misleading for
            # entries that carry a review note, such as a shared network that was excused.
            reason = "Counted (see review notes)" if r["review_notes"] else "No review rule triggered"
        else:
            reason = r["reason"]
        rows.append(
            {
                "ID": r["id"],
                "Time": r["time"],
                "Source": r["source"] or "(missing)",
                "Decision": STATUS_LABELS.get(r["status"], r["status"]),
                "Reason": reason,
                "Related IDs": ", ".join(r["related_ids"]) or "-",
                "Review notes": "; ".join(r["review_notes"]) or "-",
                "Data quality notes": "; ".join(r["data_quality_notes"]) or "-",
                "Email": r["email"],
                "Phone": r["phone_normalised"] or r["phone"] or "-",
                "IP": r["ip"] or "-",
            }
        )
    return pd.DataFrame(rows)


def filter_queue(frame: pd.DataFrame, search: str, sources: list[str], decisions: list[str]) -> pd.DataFrame:
    """Filter by source, decision and a plain-text search on ID or email.

    The search is a literal text match (regex=False), so characters such as [ ( or +
    are safe to type and plus-tagged emails like asha+promo@example.com can be found.
    """
    mask = frame["Source"].isin(sources) & frame["Decision"].isin(decisions)
    query = (search or "").strip().lower()
    if query:
        mask &= (
            frame["ID"].str.lower().str.contains(query, regex=False)
            | frame["Email"].str.lower().str.contains(query, regex=False)
        )
    return frame[mask]


def data_quality_summary(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    """IDs of rows whose problems switch off, or weaken, one of the review rules."""

    def ids_with(text: str) -> list[str]:
        return [r["id"] for r in records if any(text in note for note in r["data_quality_notes"])]

    return {
        "bad_time": ids_with("Time could not be parsed"),
        "bad_phone": ids_with("Phone could not be validated"),
        "missing_phone": ids_with("Missing phone"),
        "missing_other": sorted(
            set(ids_with("Missing email")) | set(ids_with("Missing IP")) | set(ids_with("Missing source"))
        ),
    }


def unchecked_share(records: list[dict[str, Any]]) -> float:
    """Share of rows (0 to 1) where an unreadable time or phone stopped a rule from running."""
    if not records:
        return 0.0
    quality = data_quality_summary(records)
    affected = set(quality["bad_time"]) | set(quality["bad_phone"])
    return len(affected) / len(records)


def build_report_files(
    records: list[dict[str, Any]], reconciliation: list[dict[str, Any]], sensitivity: list[dict[str, Any]]
) -> dict[str, bytes]:
    """Create the three reports with the same writers the command-line tool uses.

    The downloads are therefore byte-for-byte identical to the CSV files the
    command-line tool produces, so a filename always means the same content.
    """
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        write_submission_report(records, folder / "reviewed_submissions.csv")
        write_reconciliation_report(reconciliation, folder / "source_reconciliation.csv")
        write_sensitivity_report(sensitivity, folder / "sensitivity_report.csv")
        return {path.name: path.read_bytes() for path in folder.iterdir()}
