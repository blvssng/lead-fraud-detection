"""Tests for the Streamlit dashboard (skipped if Streamlit is not installed).

The headline numbers are drawn as HTML cards, so these tests read the numbers
back out of the page rather than looking for Streamlit metric widgets.
"""

import re
import unittest
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # the command-line tool itself needs no third-party packages
    AppTest = None

APP = str(Path(__file__).resolve().parent / "app.py")
KPI = re.compile(r'kpi-label">([^<]+)</div><div class="kpi-value">(\d+)</div>')


def kpis(at):
    """Headline numbers shown on the page, as {label: value}."""
    return dict(KPI.findall(" ".join(element.value for element in at.markdown)))


def page_text(at):
    return " ".join(element.value for element in at.markdown)


def queue_table(at):
    """The Detailed Queue table as a DataFrame."""
    for element in at.dataframe:
        if "Review notes" in element.value.columns:
            return element.value
    raise AssertionError("Detailed Queue table not found on the page")


@unittest.skipIf(AppTest is None, "streamlit is not installed")
class DashboardTests(unittest.TestCase):
    def run_app(self):
        at = AppTest.from_file(APP, default_timeout=30).run()
        self.assertFalse(at.exception, at.exception)
        return at

    def test_sample_data_shows_the_expected_headline_numbers(self):
        self.assertEqual(
            kpis(self.run_app()),
            {
                "Total Submissions": "10",
                "Provisional Count": "6",
                "Held for Review": "3",
                "Duplicates Removed": "1",
                "Maximum if Cleared": "9",
            },
        )

    def test_recommendation_tells_the_client_what_to_report(self):
        text = page_text(self.run_app())
        self.assertIn("Report <b>6</b> submissions to the client now", text)
        self.assertIn("rise to <b>9</b>", text)

    def test_changing_a_threshold_in_the_sidebar_changes_the_report(self):
        at = self.run_app()
        at.sidebar.number_input(key="min_phone").set_value(4).run()
        self.assertFalse(at.exception)
        self.assertEqual(kpis(at)["Provisional Count"], "9")
        self.assertEqual(kpis(at)["Held for Review"], "0")
        self.assertIn("Nothing is held for review", page_text(at))

    def test_removing_the_event_wifi_exemption_holds_the_event_entries(self):
        at = self.run_app()
        at.sidebar.text_input(key="shared").set_value("").run()
        self.assertFalse(at.exception)
        self.assertEqual(kpis(at)["Provisional Count"], "3")

    def test_queue_shows_review_notes_and_data_quality_notes(self):
        table = queue_table(self.run_app()).set_index("ID")
        # L06 shares an IP at the event: counted, with the reason visible.
        self.assertEqual(table.loc["L06", "Reason"], "Counted (see review notes)")
        self.assertIn("shared-network source", table.loc["L06", "Review notes"])
        # L09 has no phone number.
        self.assertIn("Missing phone", table.loc["L09", "Data quality notes"])
        # A held entry keeps the tool's own reason and related IDs.
        self.assertIn("distinct emails share", table.loc["L03", "Reason"])
        self.assertEqual(table.loc["L03", "Related IDs"], "L04, L05")

    def test_search_box_accepts_characters_that_used_to_crash_it(self):
        at = self.run_app()
        for text in ("[", "(", "asha+promo@example.com", "L03"):
            at.text_input(key="queue_search").set_value(text).run()
            self.assertFalse(at.exception, f"search for {text!r} raised {at.exception}")

    def test_incomplete_entries_are_called_out_on_the_page(self):
        at = self.run_app()
        self.assertTrue(any("no phone number: L09" in info.value for info in at.info))

    def test_unsupported_phone_region_is_flagged_instead_of_silently_skipped(self):
        at = self.run_app()
        at.sidebar.text_input(key="default_region").set_value("ZA").run()
        self.assertFalse(at.exception)
        self.assertTrue(any("could not be validated" in w.value and "skipped" in w.value for w in at.warning))
        # Nine of ten rows lost their phone check, so no confident number is recommended.
        self.assertIn("is an unchecked figure", page_text(at))
        self.assertNotIn("Report <b>", page_text(at))


if __name__ == "__main__":
    unittest.main()
