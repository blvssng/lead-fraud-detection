# Campaign Lead Review

A small, deterministic Python tool for reviewing campaign landing-page submissions. It assigns each row exactly one status: `count`, `duplicate`, or `hold_for_review`. It can be used from the command line or through a simple web interface.

**Important:** a hold means "uncertain / investigate", not "fraud". The supplied export has no confirmed fraud labels.

**Live app:** [Open the Campaign Lead Review interface](https://expert-halibut-v6pj4grr5j57cxq57-8501.app.github.dev/)

## Requirements

- Python 3.10+
- The command-line tool (`campaign_review.py`) uses only Python's standard library.
- The web interface (`app.py`) additionally needs `streamlit` and `pandas`, listed in `requirements.txt`.

## Project structure

```text
lead-fraud-detection/
├── campaign_review.py          # all review rules, reports and the command-line tool
├── app.py                      # web interface (no rules of its own; imports campaign_review.py)
├── campaign_submissions.csv    # synthetic input data
├── reviewed_submissions.csv    # generated: one decision per submission
├── source_reconciliation.csv   # generated: counts by source
├── sensitivity_report.csv      # generated: effect of changing a rule or threshold
├── test_campaign_review.py     # tests for the review logic and the command-line tool
├── test_app.py                 # tests for the web interface
├── requirements.txt
├── .gitignore
├── README.md
└── INVESTIGATION_NOTE.md
```

## Setup

From the project root:

```bash
python -m venv .venv
```

Activate it:

- macOS/Linux: `source .venv/bin/activate`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`

Then install the dependencies. This is only needed for the web interface and its tests; the command-line tool runs without it:

```bash
pip install -r requirements.txt
```

## Run: command line

The default input file is resolved relative to `campaign_review.py`, so it works regardless of the current working directory. By default, output files are written to `outputs/` relative to the current working directory.

Baseline review:

```bash
python campaign_review.py
```

Baseline plus threshold/rule sensitivity analysis:

```bash
python campaign_review.py --sensitivity
```

To provide an explicit input or output directory, relative paths are interpreted from your current working directory:

```bash
python campaign_review.py --input campaign_submissions.csv --output-dir reports --sensitivity
```

The supplied synthetic numbers are Zimbabwean. The built-in normaliser intentionally validates only Zimbabwean mobile formats; other regions are left unvalidated rather than guessed:

```bash
python campaign_review.py --default-region ZW --sensitivity
```

To use another input file or output directory:

```bash
python campaign_review.py --input path/to/submissions.csv --output-dir path/to/reports
```

## Run: web interface

**Live interface:** [Open Campaign Lead Review](https://expert-halibut-v6pj4grr5j57cxq57-8501.app.github.dev/)

Run the interface locally:

```bash
streamlit run app.py
```

This opens `http://localhost:8501`. In GitHub Codespaces, no browser opens by itself: click **Open in Browser** on the pop-up, or use the **Ports** tab and open port 8501.

The interface runs the same code as the command-line tool. `app.py` contains no review rules of its own: it imports everything from `campaign_review.py`, and its sample data is the repository's own `campaign_submissions.csv`. The two therefore cannot give different answers.

What it offers:

- **Data:** use the sample data, or upload a CSV with the columns `id, time, email, phone, ip, source`. A file with missing columns or duplicate IDs shows a clear error message instead of failing.
- **Rules:** the phone burst window, the number of emails sharing a phone or an IP needed to hold, the IP window, and the list of shared-network sources are all adjustable in the sidebar. The whole report updates when one changes.
- **Decisions tab:** every submission with its decision, reason, related IDs and review notes, colour-coded and filterable by decision and source.
- **Report by source tab:** the reconciled table (raw, duplicates, held, provisional count, upper bound) with a chart.
- **Change a rule tab:** the same data re-run with one threshold or rule changed, showing the effect on the provisional count and which rows moved. This is the same analysis as `--sensitivity`.
- **Downloads:** the decisions, the report by source and the sensitivity report as CSV. They are produced by the same writer functions as the command-line tool, so the files are identical to its output.
- **Mobile:** the layout adapts to narrow screens; the rules move into a collapsible sidebar.

Interface limitations: there is no login and no saved history (each session starts fresh), the upload must use the six columns above, and times are time-of-day values on a single day, as stated in the brief.

## Outputs

The repository snapshot includes these generated files at the project root:

- `reviewed_submissions.csv`: one decision per submission, reason, related IDs, normalised values and data-quality/review notes.
- `source_reconciliation.csv`: raw, duplicate, held and provisional counts by source, plus an upper bound (`provisional_count + holds`).
- `sensitivity_report.csv`: generated only with `--sensitivity`; compares the baseline with alternative settings.

Baseline totals in the checked repository snapshot are:

- `TOTAL`: raw=10, duplicates=1, holds=3, provisional_count=6, upper_bound=9
- by source:
  - `event_qr`: raw=3, duplicates=0, holds=0, provisional_count=3, upper_bound=3
  - `partner_a`: raw=5, duplicates=0, holds=3, provisional_count=2, upper_bound=5
  - `website`: raw=2, duplicates=1, holds=0, provisional_count=1, upper_bound=1

The reconciliation is designed to balance for every source:

`raw = duplicates + holds + provisional_count`

The provisional client figure excludes duplicates and held rows. The upper bound shows the count if every held row is later cleared.

## Tests

Run the automated tests from the project root:

```bash
python -m unittest test_campaign_review.py test_app.py -v
```

There are 12 tests:

- **`test_campaign_review.py` (9 tests):** duplicate normalisation, shared-phone burst detection, the event-Wi-Fi exemption, missing phone data, reconciliation arithmetic, sensitivity effects, and running the command-line tool from outside the repository directory. These need no third-party packages: `python -m unittest test_campaign_review.py` works on its own.
- **`test_app.py` (3 tests):** the interface runs headlessly (Streamlit's `AppTest`) and shows the expected headline numbers (10 / 1 / 3 / 6 / 9), and changing a sidebar threshold or removing the event Wi-Fi exemption changes the report as expected. These tests are skipped automatically if Streamlit is not installed.

## Verifying from a clean clone

The tests and the command-line tool depend only on committed files, and none of them depend on the current working directory:

- `campaign_submissions.csv` is committed to the repository.
- The command-line tool resolves its default input relative to `campaign_review.py`, and the tests resolve it relative to their own file, using `Path(__file__)`.
- One test runs the command-line tool from a temporary directory outside the repository.

To check this from scratch, in a folder outside the project:

```bash
git clone https://github.com/blvssng/lead-fraud-detection check
cd check
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m unittest test_campaign_review.py test_app.py -v
python campaign_review.py --sensitivity
```

Expected: `Ran 12 tests` followed by `OK`, then a reconciliation table ending in `TOTAL 10 1 3 6 9` and four sensitivity scenarios (baseline 6, phone burst needing 4 emails 9, 5-second window 9, no event Wi-Fi exemption 3).

## Rules and assumptions

1. Duplicate email has precedence over all other rules. The earliest parseable timestamp is retained; equal or unparseable times preserve input order.
2. A shared phone is held when at least 3 distinct normalised emails share it within 10 seconds, within the same source.
3. A shared IP is held at 3 distinct emails within 10 seconds, within the same source, except sources configured as shared networks. `event_qr` is exempt because the brief says attendees used shared Wi-Fi.
4. Smaller phone sharing is noted for review but does not change the count.
5. Missing/invalid data is recorded as a data-quality note. Missing phone numbers cannot trigger phone-based rules.
6. The brief states that all timestamps are on the same day and in the same time zone; the parser therefore uses time-of-day values.

These are triage rules, not proof of manipulation. A real deployment should validate thresholds against campaign context and obtain corroborating evidence before excluding leads.

## Investigation note and AI use

`INVESTIGATION_NOTE.md` explains which pattern to investigate first, how the rules could affect legitimate entrants, what evidence to request before calling anything fraud, and how I used AI tools.
