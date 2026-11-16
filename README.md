# lead-fraud-detection
Campaign Lead Fraud Review Tool

# Project Overview

This project investigates potential duplicate and suspicious submissions received through a prize entry campaign landing page. The objective is to build a small Python tool that reviews campaign submissions and classifies them according to a set of configured rules.

Importantly, the tool does not automatically declare submissions fraudulent. It classifies records for reporting purposes as:

- Count: No configured rule has identified a reason to exclude the submission provisionally.
- Duplicate: The submission matches an earlier submission based on the defined duplicate rule.
- Hold for review: The submission has a suspicious pattern that requires further investigation.

A hold does not mean fraud has been proven.
