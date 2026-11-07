# Metrics

## Detection (rules replay vs ground truth)

| Issue type | Labelled | Flagged | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| QTY_EXCEEDS_PURCHASED | 8 | 8 | 8 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| REFUND_EXCEEDS_PAID | 8 | 8 | 8 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| RESTOCK_BEFORE_INSPECTION | 8 | 8 | 8 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| LATE_NO_OVERRIDE | 8 | 8 | 8 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| DUPLICATE_REFUND | 8 | 8 | 8 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| overall | 40 | 40 | 40 | 0 | 0 | 1.0 | 1.0 | 1.0 |

## Decision accuracy vs ground-truth expectations

- eligibility decisions: 97.9950% (16 mismatches = injected late approvals + qty overrides)
- disposition: 100.0000%; refund amount per line: 97.9950% (16 mismatches = injected over-refunds)

## Operations

- request rate per delivered order: 17.06%; returned lines / lines sold: 11.21%
- line approval rate: 82.33%; override approvals: 7; exchanges: 51; partial approvals: 55
- unused labels voided: 51; carrier-lost parcels: 7

| Stage | n | mean d | median d | p90 d |
|---|---|---|---|---|
| request_to_decision | 434 | 0.61 | 0.0 | 2.0 |
| decision_to_ship | 400 | 6.58 | 7.0 | 11.0 |
| ship_to_receive | 387 | 5.14 | 5.0 | 8.0 |
| receive_to_inspect | 545 | 1.15 | 1.0 | 2.6000000000000227 |
| inspect_to_refund | 326 | 2.0 | 2.0 | 3.0 |
| request_to_refund | 326 | 15.76 | 16.0 | 21.0 |

## Financial

- refunds issued: 334; total paid: $46,801.30; refunded / delivered revenue: 5.82%
- fees retained: restocking $493.80, condition deductions $1,749.27, return shipping $1,214.48
- exposure: over-refund $103.10; duplicate payout leak $771.94
- estimated recovery from dispositions: $40,371.88 (87.71% of refunds)

| Disposition | Lines | Units | Est. recovery $ |
|---|---|---|---|
| QUARANTINE | 12 | 13 | 0.00 |
| REFURBISH | 181 | 243 | 11,931.11 |
| RESTOCK | 295 | 436 | 28,325.84 |
| SCRAP | 57 | 76 | 114.93 |

## Controls

- duplicate refund attempts: 14 -> blocked 6, paid 8 (block rate 42.86%)
- refund header reconciliation rate: 100.000%; restocks posted before inspection: 8 of 294
