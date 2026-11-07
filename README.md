# RMA - Returns Management Synthetic Data, Rules Engine and Dashboard

End-to-end synthetic data and tooling for the returns workflow: eligibility, authorization, return shipment, inspection,
restock/refurbish/quarantine/scrap, refund and duplicate-payout control. Fully synthetic and reproducible from a fixed seed.

## Quick start

```bash
pip install -r requirements.txt
python -m rma.cli all --scale 1 --out output/full        # generate + export + SQL validation + rules replay + metrics
python -m rma.cli all --scale 0.1 --out output/starter   # same generator, starter size
python -m rma.cli reproduce --scale 1 --out output/full  # regenerate twice, compare checksums
python -m pytest tests -q
streamlit run dashboard/app.py
```

**Generator command:** `python -m rma.cli generate --seed 20261022 --scale 1.0 --out output/full`
(`--scale` multiplies every volume; defaults give 30,000 orders, 5,000 return requests, 8,000 return lines).

## What is generated (full dataset, seed 20261022)

| Table | Rows | Table | Rows |
|---|---|---|---|
| customer | 12,000 | inspection | 5,473 |
| product | 600 | inventory_disposition | 5,469 |
| return_policy | 9 | inventory_movement | 6,027 |
| orders | 30,000 | refund | 3,315 |
| order_line | 73,309 | refund_line | 4,619 |
| return_request | **5,000** | return_authorization | 4,348 |
| return_line | **8,000** | return_shipment / shipment_line | 4,543 / 6,477 |
| state_event | 48,094 | | |

Starter (scale 0.1): 3,000 orders, 500 requests, 800 return lines. Output layout per dataset directory:

```
data/*.csv  json/*.json  sql/schema.sql  sql/seed.sql      inputs (no labels)
ground_truth/anomalies|decisions|scenario_labels (.csv/.json)  kept apart from inputs
reports/validation_summary|metrics|reproducibility (.md/.json), detections.csv
manifest.json   seed, command, versions, row counts, SHA-256 of every file, provenance
```

## Model and rules

16 tables (the 10 required entities plus Product, ReturnPolicy, ShipmentLine and RefundLine bridge tables, InventoryMovement and StateEvent).
See [docs/data_dictionary.md](docs/data_dictionary.md) (type, required, allowed values, units, uniqueness, validation rule for every field,
plus PK/FK/cardinality) and [docs/ERD.md](docs/ERD.md). Both, and `sql/schema.sql`, are generated from `rma/schema.py`.

IDs are zero-padded and immutable: `ORD-2026-000001`, `RMA-2026-000001`, `RMAL-RMA-2026-000001-01`, `RTS-2026-000001`, `REF-2026-000001`;
additional IDs follow the same style (`AUTH-`, `INSP-`, `DISP-`, `MOV-`, `CUST-`, `SKU-`, `ORDL-`, `RTSL-`, `REFL-`).

Policy (`rma/config.py`, effective-dated in `return_policy`): window counted from delivery date, inclusive; +15 days when the reason is seller-fault
(defective, damaged in transit, wrong item, not as described). Apparel/Footwear/Home 30 d, Electronics 15 d (20 d from 2026-06-01) with 10% restocking
fee when not sealed, Beauty 14 d and unopened only, Clearance/Perishables/Gift cards final sale. Late requests are approved only under the goodwill
override rule (GOLD <= 21 days late, SILVER <= 10) and the override is recorded.

Refund = paid share of the line (gross - allocated order discount + tax, prorated by a telescoping rounding that reconciles exactly across partial returns)
- restocking fee - condition deduction (grade B 15%, C 40%; grade D, wrong item and suspected fraud are refund-denied for customer-fault returns)
- a flat $7.99 return shipping fee (waived for GOLD tier and seller-fault). Inspection grade drives disposition (A restock, B refurbish, C refurbish if unit cost >= $15
else scrap, D scrap, W/S quarantine); only RESTOCK adds sellable stock, and only after inspection. A ledger blocks a second payout for the same idempotency key.

All outcomes are computed by `rma/rules.py` from sampled inputs (customer behaviour, inspection condition). State changes are append-only `state_event` rows; the
`status` columns are derived from the last event. The snapshot date is 2026-10-22, so some requests are legitimately still in flight.

## Labelled edge cases and ground truth

80 injected cases of each required type (return quantity exceeds purchased quantity, refund exceeds paid amount, restock before inspection, return after the window
without override, duplicate refund), on 400 distinct requests, listed with before/after values in `ground_truth/anomalies.csv`. Nothing in `data/` marks them.
`ground_truth/decisions.csv` holds the expected rule outcome for every decided return line and `scenario_labels.csv` tags normal, boundary and exception paths
(last eligible day, first late day, partial approval/quantity/shipment, final sale, late override, damaged goods, exchange, unused label, carrier loss, blocked duplicate attempt).

## Verification results (full dataset)

* **SQL validation** (`sql/validation_checks.sql` + checks generated from the schema, run on a SQLite copy loaded from the exported CSVs): 359/359 pass -
  317 structural (PK, not null, uniqueness, ID format, FK, enum, type, date format), 36 invariant (date order, arithmetic, discount/tax reconciliation, lifecycle, dispositions, duplicates),
  6 business checks whose flagged sets equal the ground truth exactly. Ten mutation tests show the validator fails when data is corrupted.
* **Rules replay** (`python -m rma.cli detect`): precision = recall = 1.0 for all five types (400/400, 0 unlabelled flags). This is rule-consistency, not generalisation:
  the detector re-applies the same rule engine that generated the data. `reports/metrics.md` also holds approval rates, cycle times, refund/fee/recovery totals and the duplicate block rate.
* **Reproducibility**: two same-seed runs in separate processes with different `PYTHONHASHSEED`, plus the published dataset - 40/40 files identical (row counts and SHA-256), and a different seed changes the output.
  Details in `output/full/reports/reproducibility.md`.
* **Tests**: `python -m pytest tests -q`.

## Provenance and lawful use

No external or public data is used. Every record is synthetic (names from small built-in lists, emails on the reserved `example.com` domain), so there are no licence, attribution or personal-data concerns.
`manifest.json` records this together with seed, command, library versions and checksums.

## Known limitations

* Distributions (reasons, conditions, price, lag) are plausible, hand-set parameters, not fitted to real retail data.
* IDs for injected rows are final: refund IDs are numbered in payout-date order after injection so injected payouts are not distinguishable by position.
* Money is USD cents; one currency, a simple state tax table, no multi-shipment order splitting.
