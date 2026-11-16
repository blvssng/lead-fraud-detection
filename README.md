# Campaign Lead Fraud Review Tool

A small Python tool for reviewing prize-campaign submissions for potential duplicates and suspicious patterns.

## Project overview

The tool helps campaign operators identify submissions that may need to be excluded from provisional counts or reviewed further. It applies configured rules to submission data and assigns each record a reporting status.

The tool does **not** determine whether a person has committed fraud. Its classifications are intended to support reporting and human review:

- **Count** — No configured rule has identified a reason to provisionally exclude the submission.
- **Duplicate** — The submission matches an earlier submission under the configured duplicate rule.
- **Hold for review** — The submission has a pattern that warrants further investigation.

A **Hold for review** status is not proof of fraud. Decisions about submissions should be made through appropriate human review.
