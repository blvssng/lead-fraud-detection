"""Tests for the dashboard's pure helper functions (no Streamlit needed, pandas required)."""

import tempfile
import unittest
from pathlib import Path

try:
    import pandas  # noqa: F401
except ImportError:
    pandas = None

from campaign_review import (
    DEFAULT_INPUT,
    Rules,
    build_reconciliation,
    load_submissions,
    review_submissions,
    run_sensitivity,
    total_row,
)

ROOT = Path(__file__).resolve().parent
HEADER = "id,time,email,phone,ip,source\n"


def write_csv(folder, text):
    path = Path(folder) / "input.csv"
    path.write_text(HEADER + text)
    return path


def reviewed(path, region="ZW"):
    return review_submissions(load_submissions(path, region), Rules())


@unittest.skipIf(pandas is None, "pandas is not installed")
class HelperTests(unittest.TestCase):
    def setUp(self):
        from dashboard_helpers import (
            build_report_files,
            data_quality_summary,
            filter_queue,
            queue_frame,
        )

        self.build_report_files = build_report_files
        self.data_quality_summary = data_quality_summary
        self.filter_queue = filter_queue
        self.queue_frame = queue_frame
        self.sample = reviewed(DEFAULT_INPUT)

    # --- search -----------------------------------------------------------

    def filtered(self, text, frame=None):
        frame = self.queue_frame(self.sample) if frame is None else frame
        return self.filter_queue(frame, text, sorted(frame["Source"].unique()), sorted(frame["Decision"].unique()))

    def test_search_treats_brackets_and_parentheses_as_plain_text(self):
        for text in ("[", "(", "*", "\\"):
            self.assertEqual(len(self.filtered(text)), 0, text)

    def test_search_finds_ids_and_emails_case_insensitively(self):
        self.assertEqual(list(self.filtered("l03")["ID"]), ["L03"])
        self.assertEqual(list(self.filtered("NYASHA")["ID"]), ["L09"])
        # Search is a substring match, so "asha@" also matches nyasha@example.com.
        self.assertEqual(list(self.filtered("ASHA@")["ID"]), ["L01", "L02", "L09"])

    def test_search_finds_plus_tagged_emails_literally(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, "A1,09:00:00,asha+promo@example.com,0771000001,1.1.1.1,web\n"
                                  "A2,09:05:00,ashaa@example.com,0771000002,1.1.1.2,web\n")
            frame = self.queue_frame(reviewed(path))
            self.assertEqual(list(self.filtered("asha+promo", frame)["ID"]), ["A1"])

    # --- queue table ------------------------------------------------------

    def test_counted_entry_with_a_review_note_does_not_claim_no_rule_triggered(self):
        table = self.queue_frame(self.sample).set_index("ID")
        self.assertEqual(table.loc["L06", "Reason"], "Counted (see review notes)")
        self.assertEqual(table.loc["L10", "Reason"], "No review rule triggered")
        self.assertIn("Missing phone", table.loc["L09", "Data quality notes"])

    # --- data quality -----------------------------------------------------

    def test_sample_data_only_has_a_missing_phone(self):
        quality = self.data_quality_summary(self.sample)
        self.assertEqual(quality["missing_phone"], ["L09"])
        self.assertEqual(quality["bad_time"], [])
        self.assertEqual(quality["bad_phone"], [])

    def test_full_date_times_are_reported_because_they_switch_off_the_burst_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, "".join(
                f"L0{i},2026-11-20 09:15:0{i},entry0{i}@example.com,0771000100,192.0.2.2{i},partner_a\n"
                for i in (1, 3, 5)
            ))
            records = reviewed(path)
            # Documents the silent failure: nothing is held, so the notice is essential.
            self.assertEqual({r["status"] for r in records}, {"count"})
            self.assertEqual(self.data_quality_summary(records)["bad_time"], ["L01", "L03", "L05"])

    def test_phone_numbers_from_another_region_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, "A1,09:00:00,a@x.com,0821234567,1.1.1.1,web\n")
            self.assertEqual(self.data_quality_summary(reviewed(path, "ZA"))["bad_phone"], ["A1"])

    def test_unchecked_share_separates_a_stray_typo_from_a_file_that_mostly_could_not_be_checked(self):
        from dashboard_helpers import UNCHECKED_SHARE, unchecked_share

        self.assertEqual(unchecked_share(self.sample), 0.0)
        with tempfile.TemporaryDirectory() as tmp:
            rows = "".join(f"A{i},09:0{i}:00,p{i}@x.com,07710000{i:02d},1.1.1.{i},web\n" for i in range(1, 10))
            rows += "A10,09:30:00,p10@x.com,not-a-phone,1.1.1.10,web\n"
            one_typo = unchecked_share(reviewed(write_csv(tmp, rows)))
            self.assertEqual(one_typo, 0.1)
            self.assertLess(one_typo, UNCHECKED_SHARE)
        with tempfile.TemporaryDirectory() as tmp:
            dated = "".join(f"A{i},2026-11-20 09:0{i}:00,p{i}@x.com,,1.1.1.{i},web\n" for i in range(1, 6))
            self.assertEqual(unchecked_share(reviewed(write_csv(tmp, dated))), 1.0)
        self.assertEqual(unchecked_share([]), 0.0)

    # --- empty file -------------------------------------------------------

    def test_a_file_with_only_headings_reconciles_to_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = reviewed(write_csv(tmp, ""))
            self.assertEqual(records, [])
            self.assertEqual(total_row(build_reconciliation(records))["raw"], 0)

    # --- downloads --------------------------------------------------------

    def test_downloads_are_identical_to_the_files_the_command_line_tool_writes(self):
        recon = build_reconciliation(self.sample)
        files = self.build_report_files(self.sample, recon, run_sensitivity(DEFAULT_INPUT, Rules()))
        self.assertEqual(set(files), {"reviewed_submissions.csv", "source_reconciliation.csv", "sensitivity_report.csv"})
        for name, content in files.items():
            committed = (ROOT / name).read_bytes()
            self.assertEqual(content.replace(b"\r\n", b"\n"), committed.replace(b"\r\n", b"\n"), name)


if __name__ == "__main__":
    unittest.main()
