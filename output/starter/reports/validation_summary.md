# Validation summary (starter)

**Overall: PASS** - 359/359 checks passed.

| Layer | Checks | Passed |
|---|---|---|
| structural | 317 | 317 |
| invariant | 36 | 36 |
| business | 6 | 6 |

## Business checks vs ground truth (must match exactly)

| Check | Description | Flagged | In ground truth | TP | FP | FN | Status |
|---|---|---|---|---|---|---|---|
| A05 | refund_line refund != paid_share - restocking fee - condition deduction (entity = refund) | 8 | 8 | 8 | 0 | 0 | PASS |
| B01 | approved return quantity exceeds purchased quantity | 8 | 8 | 8 | 0 | 0 | PASS |
| B02 | refund exceeds paid share of a line, or cumulative refunds exceed the amount paid for the order line | 8 | 8 | 8 | 0 | 0 | PASS |
| B03 | sellable restock posted before the inspection of that line | 8 | 8 | 8 | 0 | 0 | PASS |
| B04 | approved after the policy window (version in force at delivery) with no override | 8 | 8 | 8 | 0 | 0 | PASS |
| B05 | second ISSUED payout for the same idempotency key | 8 | 8 | 8 | 0 | 0 | PASS |

## Invariant checks (must be zero)

| Check | Description | Violations | Status |
|---|---|---|---|
| D01 | order delivered before it was placed | 0 | PASS |
| D02 | delivery_date presence must match order status | 0 | PASS |
| D03 | return requested before delivery, or for an undelivered order, or after snapshot | 0 | PASS |
| D04 | line decision date before request, or PENDING/decided_at mismatch | 0 | PASS |
| D05 | authorization before request or expiry != decided_at + 21 days | 0 | PASS |
| D06 | shipment dates out of order (label <= shipped <= received) | 0 | PASS |
| D07 | inspection before parcel received | 0 | PASS |
| D08 | disposition decided before inspection | 0 | PASS |
| D09 | refund paid before an inspection of its request | 0 | PASS |
| D10 | non-restock movement posted before the inspection | 0 | PASS |
| D11 | state event after the snapshot date | 0 | PASS |
| D12 | customer created after first order | 0 | PASS |
| A01 | order line arithmetic (gross, net, paid, tax) | 0 | PASS |
| A02 | order header totals must equal sum of lines (and have lines) | 0 | PASS |
| A03 | order total and shipping rule | 0 | PASS |
| A04 | refund_line paid_share != gross - discount + tax | 0 | PASS |
| A06 | refund header (attempt 1) != sum of lines - return shipping fee | 0 | PASS |
| A07 | paid_cents must equal amount for ISSUED and 0 for BLOCKED_DUPLICATE; replays carry no lines | 0 | PASS |
| A08 | fully returned order line: refunded gross/discount/tax must equal the order line (discount and tax reconciliation) | 0 | PASS |
| A09 | refund_line order_line must match its return_line; return request customer must match order customer | 0 | PASS |
| A10 | quantity chain: expected <= approved, shipped <= expected, received <= shipped, inspected = received, disposition qty = inspected | 0 | PASS |
| B06 | override approvals must satisfy the goodwill rule (GOLD <= 21 days late, SILVER <= 10) and carry a code | 0 | PASS |
| B07 | approved quantity in a final-sale category, or opened beauty without seller fault | 0 | PASS |
| B08 | decision fields inconsistent (REJECTED needs qty 0; APPROVED needs qty>=1 and reason; authorization iff approved line) | 0 | PASS |
| B09 | grade/fault/eligibility/disposition must follow inspection rules | 0 | PASS |
| B10 | disposition must follow grade (A restock, B refurbish, C refurbish if cost>=1500 else scrap, D scrap, W/S quarantine); location follows disposition | 0 | PASS |
| B11 | inventory movement must be controlled by its disposition (type, location, qty, sellable delta) | 0 | PASS |
| B12 | refund only after inspection, only for eligible lines, never for exchange requests | 0 | PASS |
| B13 | return shipping fee rule (799 flat, waived for GOLD or any seller-fault line, capped at merchandise total) | 0 | PASS |
| L01 | state transition not allowed by the lifecycle | 0 | PASS |
| L02 | from_state must equal the previous to_state of the same entity (history is continuous and ordered) | 0 | PASS |
| L03 | current status column must equal the last event | 0 | PASS |
| L04 | event points to a missing parent, or an entity has no initial event | 0 | PASS |
| L05 | lifecycle vs facts: AUTHORIZED+ needs an authorization; RECEIVED+ needs received parcels; INSPECTED+ needs inspections; REFUNDED needs an ISSUED refund | 0 | PASS |
| U01 | one return request per (order line, request) and one authorization / inspection per owner | 0 | PASS |
| P01 | policy versions of one category must not overlap | 0 | PASS |

Structural checks (PK/NOT NULL/unique/ID format/FK/enum/type/date format): 317 generated from the schema, 317 passed.

Row counts: customer=1200, product=600, return_policy=9, orders=3000, order_line=7138, return_request=500, return_line=800, return_authorization=434, return_shipment=459, shipment_line=657, inspection=545, inventory_disposition=545, inventory_movement=596, refund=340, refund_line=469, state_event=4852
