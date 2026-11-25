#!/usr/bin/env python3
"""Review campaign submissions using transparent, deterministic rules.

Decision precedence:
1. duplicate: same normalised email as an earlier submission
2. hold_for_review: part of a qualifying shared-phone or shared-IP cluster
3. count: everything else

A hold means uncertainty, not fraud. The export contains no confirmed fraud labels.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import re

REQUIRED_COLUMNS = {"id", "time", "email", "phone", "ip", "source"}
DEFAULT_INPUT = Path(__file__).resolve().parent / "campaign_submissions.csv"


@dataclass(frozen=True)
class Rules:
    burst_window_seconds: int = 10
    min_shared_phone_entries: int = 3
    ip_window_seconds: int = 10
    min_shared_ip_entries: int = 3
    shared_network_sources: frozenset[str] = frozenset({"event_qr"})


def normalise_email(value: str | None) -> str:
    """Trim whitespace and lowercase; preserve dots and plus tags."""
    return (value or "").strip().lower()


def normalise_phone(value: str | None, default_region: str = "ZW") -> str:
    """Normalise Zimbabwean mobile numbers to E.164 using the standard library.

    Accepts +263771000001, 263771000001, 0771000001 and 771000001.
    This assessment supplies Zimbabwean numbers; other regions are not guessed.
    """
    raw = (value or "").strip()
    if not raw or default_region.upper() != "ZW":
        return ""
    digits = re.sub(r"[\s().-]", "", raw)
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("00263"):
        digits = digits[5:]
    elif digits.startswith("263"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"7\d{8}", digits):
        return ""
    return "+263" + digits


def parse_time(value: str) -> datetime | None:
    """Parse time-only values; the assessment states all rows are on one day."""
    try:
        return datetime.strptime(value.strip(), "%H:%M:%S")
    except (AttributeError, ValueError):
        return None


def load_submissions(csv_path: Path, default_region: str = "ZW") -> list[dict[str, Any]]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

        records: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            record = {key: (value or "").strip() for key, value in row.items() if key}
            submission_id = record["id"]
            if not submission_id:
                raise ValueError(f"Missing submission ID on CSV line {line_number}")
            if submission_id in seen_ids:
                raise ValueError(f"Duplicate submission ID {submission_id!r} on line {line_number}")
            seen_ids.add(submission_id)

            email_norm = normalise_email(record["email"])
            phone_norm = normalise_phone(record["phone"], default_region)
            timestamp = parse_time(record["time"])
            notes: list[str] = []
            if not email_norm:
                notes.append("Missing email")
            if not record["phone"]:
                notes.append("Missing phone")
            elif not phone_norm:
                notes.append("Phone could not be validated/normalised")
            if timestamp is None:
                notes.append("Time could not be parsed; excluded from time-window rules")
            if not record["ip"]:
                notes.append("Missing IP address")
            if not record["source"]:
                notes.append("Missing source")

            record.update(
                email_normalised=email_norm,
                phone_normalised=phone_norm,
                time_parsed=timestamp,
                status="count",
                reason="No configured review rule triggered",
                related_ids=[],
                review_notes=[],
                data_quality_notes=notes,
            )
            records.append(record)
    return records


def mark_duplicate_emails(records: list[dict[str, Any]]) -> None:
    """Keep the earliest row per normalised email; mark later rows duplicate."""
    by_email: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["email_normalised"]:
            by_email[record["email_normalised"]].append(record)

    for group in by_email.values():
        group.sort(key=lambda r: (r["time_parsed"] is None, r["time_parsed"] or datetime.max))
        keeper = group[0]
        for duplicate in group[1:]:
            duplicate["status"] = "duplicate"
            duplicate["reason"] = (
                f"Email matches earlier submission {keeper['id']} "
                "after trimming whitespace and lowercasing"
            )
            duplicate["related_ids"] = [keeper["id"]]


def _add_hold(record: dict[str, Any], reason: str, related: list[str]) -> None:
    if record["status"] == "duplicate":
        return
    if record["status"] == "hold_for_review":
        record["reason"] += "; " + reason
    else:
        record["status"] = "hold_for_review"
        record["reason"] = reason
    record["related_ids"] = sorted(set(record["related_ids"]) | set(related))


def _group(records: list[dict[str, Any]], key_field: str) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group eligible non-duplicates by signal and source."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["status"] == "duplicate":
            continue
        key = record[key_field]
        if key and record["time_parsed"] is not None and record["source"] and record["email_normalised"]:
            groups[(key, record["source"])].append(record)
    return groups


def _window_clusters(
    group: list[dict[str, Any]], window_seconds: int, min_entries: int
) -> tuple[dict[str, set[str]], dict[str, int]]:
    """Find qualifying sliding windows and return related IDs and max cluster size."""
    ordered = sorted(group, key=lambda r: (r["time_parsed"], r["id"]))
    related: dict[str, set[str]] = defaultdict(set)
    strength: dict[str, int] = {}
    for start, first in enumerate(ordered):
        window = []
        for candidate in ordered[start:]:
            if (candidate["time_parsed"] - first["time_parsed"]).total_seconds() > window_seconds:
                break
            window.append(candidate)
        distinct = {r["email_normalised"] for r in window}
        if len(window) >= min_entries and len(distinct) >= min_entries:
            ids = {r["id"] for r in window}
            for record in window:
                related[record["id"]] |= ids - {record["id"]}
                strength[record["id"]] = max(strength.get(record["id"], 0), len(distinct))
    return related, strength


def find_phone_bursts(records: list[dict[str, Any]], rules: Rules) -> None:
    for (_, source), group in _group(records, "phone_normalised").items():
        related, strength = _window_clusters(
            group, rules.burst_window_seconds, rules.min_shared_phone_entries
        )
        for record in group:
            if record["id"] in related:
                _add_hold(
                    record,
                    f"{strength[record['id']]} distinct emails share a normalised phone number "
                    f"from source {source!r} within {rules.burst_window_seconds} seconds",
                    sorted(related[record["id"]]),
                )
        # Sub-threshold sharing is noted but does not change the count.
        for record in group:
            if record["status"] == "hold_for_review":
                continue
            others = sorted(
                o["id"] for o in group
                if o["email_normalised"] != record["email_normalised"]
            )
            if others:
                record["review_notes"].append(
                    f"Phone also used with a different email on {', '.join(others)} "
                    "(below the hold threshold)"
                )


def find_ip_clusters(records: list[dict[str, Any]], rules: Rules) -> None:
    for (ip, source), group in _group(records, "ip").items():
        related, strength = _window_clusters(
            group, rules.ip_window_seconds, rules.min_shared_ip_entries
        )
        for record in group:
            ids = sorted(related.get(record["id"], ()))
            if not ids:
                continue
            if source in rules.shared_network_sources:
                record["review_notes"].append(
                    f"Shares IP {ip} with {', '.join(ids)} within {rules.ip_window_seconds}s; "
                    f"source {source!r} is a configured shared-network source, so not held"
                )
            else:
                _add_hold(
                    record,
                    f"{strength[record['id']]} distinct emails share IP {ip} from source "
                    f"{source!r} within {rules.ip_window_seconds} seconds",
                    ids,
                )


def review_submissions(
    records: list[dict[str, Any]], rules: Rules | None = None
) -> list[dict[str, Any]]:
    rules = rules or Rules()
    mark_duplicate_emails(records)
    find_phone_bursts(records, rules)
    find_ip_clusters(records, rules)
    return records


RECON_FIELDS = ["source", "raw", "duplicates", "holds", "provisional_count", "upper_bound"]


def build_reconciliation(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"raw": 0, "duplicates": 0, "holds": 0, "provisional_count": 0}
    )
    for record in records:
        bucket = totals[record["source"] or "(missing source)"]
        bucket["raw"] += 1
        if record["status"] == "duplicate":
            bucket["duplicates"] += 1
        elif record["status"] == "hold_for_review":
            bucket["holds"] += 1
        elif record["status"] == "count":
            bucket["provisional_count"] += 1
        else:
            raise ValueError(f"Unknown status {record['status']!r} on submission {record['id']}")

    rows = []
    for source in sorted(totals):
        values = totals[source]
        if values["raw"] != values["duplicates"] + values["holds"] + values["provisional_count"]:
            raise AssertionError(f"Reconciliation does not balance for source {source!r}")
        rows.append({
            "source": source,
            **values,
            "upper_bound": values["provisional_count"] + values["holds"],
        })
    return rows


def total_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "source": "TOTAL",
        **{key: sum(row[key] for row in rows) for key in RECON_FIELDS[1:]},
    }


def write_submission_report(records: list[dict[str, Any]], output_path: Path) -> None:
    fields = [
        "id", "time", "email", "phone", "ip", "source",
        "email_normalised", "phone_normalised", "status", "reason",
        "related_ids", "review_notes", "data_quality_notes",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["related_ids"] = ";".join(record["related_ids"])
            row["review_notes"] = "; ".join(record["review_notes"])
            row["data_quality_notes"] = "; ".join(record["data_quality_notes"])
            writer.writerow({field: row.get(field, "") for field in fields})


def write_reconciliation_report(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RECON_FIELDS)
        writer.writeheader()
        writer.writerows(rows + [total_row(rows)])


SCENARIOS: list[tuple[str, str, dict[str, Any]]] = [
    ("baseline", "Default rules", {}),
    ("min_shared_phone_entries=4",
     "Require 4 distinct emails instead of 3 for a shared-phone hold",
     {"min_shared_phone_entries": 4}),
    ("burst_window_seconds=5",
     "Use a 5-second shared-phone window instead of 10 seconds",
     {"burst_window_seconds": 5}),
    ("no_shared_network_exemption",
     "Apply the shared-IP hold rule to event_qr as well",
     {"shared_network_sources": frozenset()}),
]
SENSITIVITY_FIELDS = [
    "scenario", "setting", "source", "raw", "duplicates", "holds",
    "provisional_count", "upper_bound", "provisional_vs_baseline", "rows_changed",
]


def run_sensitivity(
    input_path: Path, base_rules: Rules, default_region: str = "ZW"
) -> list[dict[str, Any]]:
    baseline_decisions: dict[str, str] = {}
    baseline_by_source: dict[str, int] = {}
    output: list[dict[str, Any]] = []
    for index, (name, description, overrides) in enumerate(SCENARIOS):
        rules = replace(base_rules, **overrides)
        records = review_submissions(load_submissions(input_path, default_region), rules)
        recon = build_reconciliation(records)
        rows = recon + [total_row(recon)]
        decisions = {record["id"]: record["status"] for record in records}
        if index == 0:
            baseline_decisions = decisions
            baseline_by_source = {row["source"]: row["provisional_count"] for row in rows}
        changed = "; ".join(
            f"{rid}: {baseline_decisions[rid]}->{status}"
            for rid, status in decisions.items()
            if status != baseline_decisions[rid]
        )
        for row in rows:
            output.append({
                "scenario": name,
                "setting": description,
                **row,
                "provisional_vs_baseline": (
                    row["provisional_count"] - baseline_by_source.get(row["source"], 0)
                ),
                "rows_changed": changed if row["source"] == "TOTAL" else "",
            })
    return output


def write_sensitivity_report(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SENSITIVITY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _print_table(rows: list[dict[str, Any]]) -> None:
    print(f"{'source':<12}{'raw':>5}{'dups':>6}{'holds':>7}{'count':>7}{'upper':>7}")
    for row in rows:
        print(
            f"{row['source']:<12}{row['raw']:>5}{row['duplicates']:>6}"
            f"{row['holds']:>7}{row['provisional_count']:>7}{row['upper_bound']:>7}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review campaign submissions using deterministic, explainable rules."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--burst-seconds", type=int, default=10)
    parser.add_argument("--min-shared-phone-entries", type=int, default=3)
    parser.add_argument("--ip-window-seconds", type=int, default=10)
    parser.add_argument("--min-shared-ip-entries", type=int, default=3)
    parser.add_argument("--shared-network-sources", default="event_qr")
    parser.add_argument("--default-region", default="ZW")
    parser.add_argument("--sensitivity", action="store_true")
    args = parser.parse_args()

    if args.burst_seconds < 0 or args.ip_window_seconds < 0:
        parser.error("window values must be zero or greater")
    if args.min_shared_phone_entries < 2 or args.min_shared_ip_entries < 2:
        parser.error("minimum shared entries must be at least 2")

    rules = Rules(
        burst_window_seconds=args.burst_seconds,
        min_shared_phone_entries=args.min_shared_phone_entries,
        ip_window_seconds=args.ip_window_seconds,
        min_shared_ip_entries=args.min_shared_ip_entries,
        shared_network_sources=frozenset(
            item.strip() for item in args.shared_network_sources.split(",") if item.strip()
        ),
    )
    records = review_submissions(load_submissions(args.input, args.default_region), rules)
    reconciliation = build_reconciliation(records)
    write_submission_report(records, args.output_dir / "reviewed_submissions.csv")
    write_reconciliation_report(reconciliation, args.output_dir / "source_reconciliation.csv")

    print(f"Reviewed {len(records)} submissions.\n")
    _print_table(reconciliation + [total_row(reconciliation)])
    print(f"\nSubmission report: {args.output_dir / 'reviewed_submissions.csv'}")
    print(f"Reconciliation:    {args.output_dir / 'source_reconciliation.csv'}")

    if args.sensitivity:
        sensitivity = run_sensitivity(args.input, rules, args.default_region)
        write_sensitivity_report(sensitivity, args.output_dir / "sensitivity_report.csv")
        print(f"Sensitivity:       {args.output_dir / 'sensitivity_report.csv'}\n")
        for row in (item for item in sensitivity if item["source"] == "TOTAL"):
            print(
                f"  {row['scenario']:<30} provisional={row['provisional_count']:<3} "
                f"holds={row['holds']:<3} change={row['provisional_vs_baseline']:+d}"
            )


if __name__ == "__main__":
    main()
