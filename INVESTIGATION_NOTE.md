# Investigation note

## Initial finding

The first pattern to investigate is `partner_a`: L03, L04 and L05 use the same normalised phone number across three different email addresses within six seconds (09:15:01–09:15:07). The phone-burst rule therefore holds all three for human review. Their IP addresses differ, so the phone pattern is the common signal.

L01 and L02 have the same email after trimming/lowercasing. L01 is retained and L02 is marked duplicate. The two phone formats also normalise to the same Zimbabwean E.164 number, but the duplicate-email rule is the reason for L02's final decision.

L06–L08 share an IP within eight seconds, but all are from `event_qr`. The brief confirms that this link was used at an in-person activation with shared Wi-Fi, so this IP cluster is noted but counted rather than held. L09 has no phone; it remains countable, with a data-quality note. L10 is counted.

## Baseline reconciliation

| Source | Raw | Duplicates | Holds | Provisional count | Upper bound |
|---|---:|---:|---:|---:|---:|
| event_qr | 3 | 0 | 0 | 3 | 3 |
| partner_a | 5 | 0 | 3 | 2 | 5 |
| website | 2 | 1 | 0 | 1 | 1 |
| **TOTAL** | **10** | **1** | **3** | **6** | **9** |

The provisional figure to share pending review is **6**. The upper bound is **9** if all three held partner_a submissions are subsequently cleared. The figures reconcile: 10 raw = 1 duplicate + 3 holds + 6 provisional.

## Sensitivity analysis

The baseline phone rule is at least 3 distinct emails sharing a phone within 10 seconds.

| Scenario | Holds | Provisional count | Change vs baseline |
|---|---:|---:|---:|
| Baseline | 3 | 6 | 0 |
| Require 4 shared-phone entries | 0 | 9 | +3 |
| Reduce phone window to 5 seconds | 0 | 9 | +3 |
| Remove event_qr shared-IP exemption | 3 | 3 | -3 |

Changing the phone threshold from 3 to 4, or shrinking the window to 5 seconds, clears L03–L05 and increases the provisional count by three. This illustrates that the client-facing number is sensitive to the chosen threshold. Removing the event Wi-Fi exemption instead holds L06–L08 and reduces the provisional count by three, demonstrating why campaign context matters.

## Legitimate entrants and limitations

A family, household, office, or event activation may legitimately share a phone or IP address. Conversely, people submitting from separate devices can still coordinate. A shared signal should therefore trigger review, not an automatic fraud finding. Grouping is within source to avoid treating unrelated channels as one cluster. Time windows and minimum group sizes are configurable.

The sample contains only ten synthetic rows, one day of time-only timestamps, and no verified fraud outcomes. The rules cannot estimate precision/recall or prove intent. The `event_qr` exemption is based on the explicit shared-Wi-Fi context in the brief; it should be revisited if the source setup changes.

## Evidence to request before calling anything fraud

- Landing-page/server logs, including submission timestamps with timezone and request/session identifiers.
- Referral click IDs, campaign/affiliate IDs, redirect history and source attribution validation.
- IP context (including whether it is carrier-grade NAT, corporate, venue or public Wi-Fi), not just the IP string.
- Device/browser signals and session patterns, collected lawfully and proportionately.
- Phone/email verification outcomes and any contactability or delivery evidence.
- Partner_a's traffic acquisition method, placement, incentive arrangements and any sub-publisher details.
- Manual sampling and contact/consent evidence, plus confirmation from the campaign owner.

Do not label or reject these entrants as fraudulent on this dataset alone. Keep them in a review queue and report the provisional count with the held volume disclosed.

## AI-use note

AI assistance was used to review the initial implementation, identify execution/setup and edge-case risks, structure the README and tests, and help explain the rule outcomes. The rules, assumptions and final decisions should be understood and defended by the candidate; the tool does not infer confirmed fraud.

## Implementation note

The final version uses only the Python standard library. Its phone normaliser is intentionally scoped to the Zimbabwean mobile-number formats present in this assessment; it does not claim to validate numbers for other countries.
