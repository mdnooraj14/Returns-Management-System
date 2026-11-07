# PROGRESS

Seed `20261022`, snapshot date `2026-10-22`. Python 3.11, pandas, NumPy, SQLite, Streamlit, Plotly, pytest.
Run everything: `python -m rma.cli all --scale 1 --out output/full` (see README).

| Phase | Status | Evidence |
|---|---|---|
| 1 Setup, schema, data dictionary, policy | DONE | 16 tables in `rma/schema.py` -> `sql/schema.sql` (loads in SQLite), `docs/data_dictionary.md`, `docs/ERD.md`; rule unit tests (windows, boundaries, overrides, refund math, duplicate block) pass |
| 2 Master data and orders | DONE | 30,000 orders / 73,309 lines / 12,000 customers / 600 SKUs in 3.8 s; line, order, tax, discount allocation reconcile to the cent (`tests/test_master.py`, SQL checks A01-A03) |
| 3 Return flow | DONE | Exactly 5,000 requests and 8,000 lines; every state change is an event (47k+); statuses derived from last event; partial returns, late, damaged, exchanges, missing shipment (447 voided labels), carrier loss, blocked duplicate attempts all present (`tests/test_returns.py`, scenario labels) |
| 4 Anomaly injection + ground truth | DONE | 80 each of 5 required edge cases, on disjoint requests, labelled in `ground_truth/anomalies.csv` only; no label/flag leaks into input tables (`tests/test_anomalies.py`). Two defects found and fixed along the way: QTY injection corrupting a sibling line's legitimate approval, and two anomalies landing on one request |
| 5 Independent SQL validator | DONE | 359 checks (317 structural, 36 invariant, 6 business) all PASS on full and starter data; the 6 business checks equal ground truth exactly (TP 80 / FP 0 / FN 0 each); 10 mutation tests prove the validator fails on corrupted data (`tests/test_validator.py`) |
| 6 Rules replay + metrics | DONE | Replay detector, never reads ground truth (tested): precision = recall = 1.0 per type (400/400), 0 unlabelled flags. Caveat: it replays the same rule engine that generated the data, so this proves rule consistency, not generalisation. `reports/metrics.md` |
| 7 Exports, README, manifest | DONE | CSV + JSON + SQL seed (`sql/seed.sql`) + schema, `manifest.json` (seed, command, versions, provenance, SHA-256 of 40 files), `reports/validation_summary.md`, README, data dictionary, ERD; full 105 MB / starter 11 MB |
| 8 Reproducibility | DONE | Two same-seed runs in separate processes (different PYTHONHASHSEED) + published dataset: 40/40 files identical, row counts equal; different seed changes output (`reports/reproducibility.md`, `tests/test_reproduce.py`) |
| 9 Streamlit dashboard | DONE | 6 tabs (overview, decisions, exceptions, RMA trace with event history, financials, data quality); served headless on :8599 and rendered in the browser pane; `streamlit.testing` AppTest passes for full + starter + trace selection |

Latest full run: 217,283 rows, 7 s to generate; 49 tests passing. Dashboard fix: a ternary statement `st.dataframe(..) if x else st.caption(..)` was auto-rendered by Streamlit magic (leaking DeltaGenerator docs); replaced with if/else and guarded by AST + AppTest regression tests.
