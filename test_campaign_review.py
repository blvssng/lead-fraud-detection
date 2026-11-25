import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from campaign_review import (
    Rules, build_reconciliation, load_submissions, normalise_email,
    normalise_phone, review_submissions, run_sensitivity, total_row,
)


ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "campaign_submissions.csv"


class CampaignReviewTests(unittest.TestCase):
    def reviewed(self, path=SAMPLE, rules=None):
        return review_submissions(load_submissions(path), rules)

    def test_duplicate_email_is_normalised_and_later_row_excluded(self):
        records = self.reviewed()
        by_id = {row["id"]: row for row in records}
        self.assertEqual(by_id["L01"]["status"], "count")
        self.assertEqual(by_id["L02"]["status"], "duplicate")
        self.assertEqual(by_id["L02"]["related_ids"], ["L01"])

    def test_three_shared_phones_in_ten_seconds_are_held(self):
        records = self.reviewed()
        by_id = {row["id"]: row for row in records}
        for submission_id in ("L03", "L04", "L05"):
            self.assertEqual(by_id[submission_id]["status"], "hold_for_review")
        self.assertEqual(set(by_id["L03"]["related_ids"]), {"L04", "L05"})

    def test_event_wifi_shared_ip_is_not_held(self):
        records = self.reviewed()
        by_id = {row["id"]: row for row in records}
        for submission_id in ("L06", "L07", "L08"):
            self.assertEqual(by_id[submission_id]["status"], "count")
            self.assertTrue(by_id[submission_id]["review_notes"])

    def test_missing_phone_does_not_crash_or_create_phone_cluster(self):
        records = self.reviewed()
        by_id = {row["id"]: row for row in records}
        self.assertEqual(by_id["L09"]["status"], "count")
        self.assertIn("Missing phone", by_id["L09"]["data_quality_notes"])

    def test_reconciliation_balances_and_expected_totals(self):
        records = self.reviewed()
        rows = build_reconciliation(records)
        total = total_row(rows)
        self.assertEqual(
            (total["raw"], total["duplicates"], total["holds"], total["provisional_count"]),
            (10, 1, 3, 6),
        )
        self.assertEqual(total["raw"], total["duplicates"] + total["holds"] + total["provisional_count"])

    def test_threshold_change_changes_client_count(self):
        rows = run_sensitivity(SAMPLE, Rules(), "ZW")
        totals = {row["scenario"]: row for row in rows if row["source"] == "TOTAL"}
        self.assertEqual(totals["baseline"]["provisional_count"], 6)
        self.assertEqual(totals["min_shared_phone_entries=4"]["provisional_count"], 9)
        self.assertEqual(totals["burst_window_seconds=5"]["provisional_count"], 9)
        self.assertEqual(totals["no_shared_network_exemption"]["provisional_count"], 3)

    def test_email_normalisation(self):
        self.assertEqual(normalise_email(" Asha@Example.com "), "asha@example.com")

    def test_zw_phone_formats_normalise_to_same_e164(self):
        self.assertEqual(normalise_phone("+263771000001"), normalise_phone("0771000001"))

    def test_cli_default_input_works_outside_repository_directory(self):
        with tempfile.TemporaryDirectory() as working_dir:
            output_dir = Path(working_dir) / "reports"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "campaign_review.py"),
                    "--output-dir",
                    str(output_dir),
                    "--sensitivity",
                ],
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("Reviewed 10 submissions.", result.stdout)
            self.assertTrue((output_dir / "reviewed_submissions.csv").is_file())
            self.assertTrue((output_dir / "source_reconciliation.csv").is_file())
            self.assertTrue((output_dir / "sensitivity_report.csv").is_file())


if __name__ == "__main__":
    unittest.main()
