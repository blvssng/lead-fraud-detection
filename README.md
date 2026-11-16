# Campaign Lead Fraud Review Tool

A small Python tool for reviewing prize-campaign submissions for potential duplicates and suspicious patterns.

## Project overview

The tool helps campaign operators identify submissions that may need to be excluded from provisional counts or reviewed further. It applies configured rules to submission data and assigns each record a review status and reason.

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

Phone numbers are normalised to a consistent local format so that equivalent numbers are easier to compare. For example:

| Original phone number | Normalised phone number |
| --- | --- |
| `+263771000001` | `0771000001` |

Normalised values are used for comparison; they are not evidence that two people are necessarily the same person.

The raw export should remain unchanged so that the preparation and review process can be audited.

## Detection approach

The tool uses deterministic rules supported by identity-relationship analysis. These rules identify records for provisional handling and human review; they do not establish that fraud has occurred.

### Rule 1: Duplicate email

Email addresses are trimmed of surrounding whitespace and converted to lowercase before comparison.

Where the same normalised email appears more than once, the earliest submission is retained and subsequent submissions are marked as duplicates.

### Rule 2: Shared-phone burst

A group is held for review when all of the following conditions are met:

- At least three submissions share the same normalised phone number.
- The submissions come from the same referral source.
- The time between the first and last submission is no more than 10 seconds.
- The submissions have distinct normalised email addresses.

The entire group is held because the available information does not establish which submission, if any, is genuine.

### Rule 3: Shared IP address

A shared IP address alone does not cause a submission to be excluded. This is important because attendees at the in-person event used shared Wi-Fi.

### Rule 4: Rapid submissions

Rapid submissions alone do not result in exclusion. Timing is considered alongside other evidence.

### Rule 5: Missing phone number

A missing phone number is recorded as a data-quality warning. It does not automatically exclude a submission, assuming the campaign did not make the phone field mandatory.
