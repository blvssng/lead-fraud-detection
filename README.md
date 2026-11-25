# Campaign Lead Review

A small, deterministic Python tool for reviewing campaign landing-page submissions. It assigns each row exactly one status: `count`, `duplicate`, or `hold_for_review`.

**Important:** a hold means "uncertain / investigate", not "fraud". The supplied export has no confirmed fraud labels.

## Requirements

- Python 3.10+
- No third-party packages; the tool uses Python's standard library.

## Project structure

```text
lead-fraud-detection/
├── campaign_review.py
├── campaign_submissions.csv
├── reviewed_submissions.csv
├── source_reconciliation.csv
├── sensitivity_report.csv
├── test_campaign_review.py
├── requirements.txt
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
- Windows PowerShell: `.venv\\Scripts\\Activate.ps1`

There are no third-party dependencies. You can run the script directly with Python 3.10 or newer.

## Run

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
python -m unittest test_campaign_review.py -v
```

The tests cover duplicate normalisation, shared-phone burst detection, the event-Wi-Fi exemption, missing phone data, reconciliation arithmetic, sensitivity effects, and running the CLI from outside the repository directory.

## Rules and assumptions

1. Duplicate email has precedence over all other rules. The earliest parseable timestamp is retained; equal or unparseable times preserve input order.
2. A shared phone is held when at least 3 distinct normalised emails share it within 10 seconds, within the same source.
3. A shared IP is held at 3 distinct emails within 10 seconds, within the same source, except sources configured as shared networks. `event_qr` is exempt because the brief says attendees used shared Wi-Fi.
4. Smaller phone sharing is noted for review but does not change the count.
5. Missing/invalid data is recorded as a data-quality note. Missing phone numbers cannot trigger phone-based rules.
6. The brief states that all timestamps are on the same day and in the same time zone; the parser therefore uses time-of-day values.

These are triage rules, not proof of manipulation. A real deployment should validate thresholds against campaign context and obtain corroborating evidence before excluding leads.
