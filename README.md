# Campaign Lead Fraud Review Tool

A small Python tool for reviewing prize-campaign submissions for potential duplicates and suspicious patterns.

## Project overview

The tool helps campaign operators identify submissions that may need to be excluded from provisional counts or reviewed further. It applies configured rules to submission data and assigns each record a reporting status.

The tool does not determine whether a person has committed fraud. Its classifications are intended to support reporting and human review:

- **Count** — No configured rule has identified a reason to provisionally exclude the submission.
- **Duplicate** — The submission matches an earlier submission under the configured duplicate rule.
- **Hold for review** — The submission has a pattern that warrants further investigation.

A **Hold for review** status is not proof of fraud. Decisions about submissions should be made through appropriate human review.

## Project structure

The project is organised as follows:

```text
campaign-lead-review/
│
├── data/
│   ├── raw/
│   │   └── campaign_submissions.csv
│   │
│   └── processed/
│       └── campaign_submissions_prepared.xlsx
│
├── src/
│   └── lead_review.py
│
├── tests/
│   └── test_lead_review.py
│
├── outputs/
│   ├── reviewed_submissions.csv
│   └── source_reconciliation.csv
│
├── requirements.txt
└── README.md
```

The Excel workbook contains the prepared dataset and documents the data-normalisation work completed before the Python analysis.

## Data preparation

The original campaign export is retained separately from the prepared data. The Excel workbook is used to inspect and prepare submissions, including:

- Standardising phone-number formats.
- Checking for missing values.
- Reviewing email addresses for inconsistent formatting.
- Checking submission timestamps.
- Identifying repeated values in email, phone, and IP fields.

Phone numbers are standardised to a consistent format so that equivalent numbers are easier to compare. For example:

| Original phone number | Normalised phone number |
| --- | --- |
| `+263771000001` | `+263771000001` |
| `0771000001` | `+263771000001` |

Normalised values are used for comparison; they are not evidence that two people are necessarily the same person.

The raw export should remain unchanged so that the preparation and review process can be audited.
