"""Smoke tests for the Streamlit interface (skipped if Streamlit is not installed)."""

import unittest
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # the command-line tool itself needs no third-party packages
    AppTest = None

APP = str(Path(__file__).resolve().parent / "app.py")


def metrics(at):
    return {m.label: m.value for m in at.metric}


@unittest.skipIf(AppTest is None, "streamlit is not installed")
class AppTests(unittest.TestCase):
    def run_app(self):
        return AppTest.from_file(APP, default_timeout=30).run()

    def test_sample_data_shows_the_expected_headline_numbers(self):
        at = self.run_app()
        self.assertFalse(at.exception)
        self.assertEqual(
            metrics(at),
            {
                "Raw submissions": "10",
                "Duplicates": "1",
                "Held for review": "3",
                "Provisional count": "6",
                "Upper bound": "9",
            },
        )

    def test_changing_a_threshold_in_the_sidebar_changes_the_report(self):
        at = self.run_app()
        at.sidebar.number_input(key="min_phone").set_value(4).run()
        self.assertFalse(at.exception)
        self.assertEqual(metrics(at)["Provisional count"], "9")
        self.assertEqual(metrics(at)["Held for review"], "0")

    def test_removing_the_event_wifi_exemption_holds_the_event_entries(self):
        at = self.run_app()
        at.sidebar.text_input(key="shared").set_value("").run()
        self.assertFalse(at.exception)
        self.assertEqual(metrics(at)["Provisional count"], "3")


if __name__ == "__main__":
    unittest.main()
