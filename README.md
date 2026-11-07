# Returns Management System (RMA)

An end-to-end Returns Management System featuring synthetic data generation, return eligibility rules, authorization, shipment tracking, inspection, inventory disposition, refund processing, duplicate-payout prevention and an interactive analytics dashboard.

The project demonstrates a complete retail returns workflow using reproducible synthetic data, Python business logic, SQL validation and Streamlit visualizations.

All generated records are synthetic and reproducible using a fixed random seed.

## 1. Project Overview

The Returns Management System simulates the lifecycle of a retail product return, from the initial customer request to the final refund and inventory update.

The system covers:

- Return eligibility and policy evaluation.
- Return authorization and expiration.
- Return shipment and delivery tracking.
- Product inspection and condition assessment.
- Inventory disposition: restock, refurbish, quarantine or scrap.
- Refund calculation and processing.
- Duplicate refund prevention.
- Data validation and anomaly detection.
- Interactive operational and financial dashboards.

## 2. Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python 3.11 |
| Data processing | Pandas, NumPy |
| Database and validation | SQLite, SQL |
| Dashboard | Streamlit |
| Data visualization | Plotly |
| Automated testing | Pytest |
| Data formats | CSV, JSON |
| Version control | Git and GitHub |

## 3. Architecture Overview

The project is organized into four main components.

### Data Generation

Generates reproducible synthetic datasets for customers, products, orders, return requests, shipments, inspections, refunds and inventory movements.

### Business Rules Engine

Evaluates return eligibility, authorization, refund calculations, inspection outcomes, inventory disposition and duplicate-payout prevention.

### Validation and Anomaly Detection

Uses SQL validation checks and business-rule evaluation to identify data integrity issues and predefined business anomalies.

### Interactive Dashboard

Provides visual insights into return performance, operational decisions, exceptions, refund metrics and data quality through a Streamlit application.

## 4. Installation and Quick Start

### Prerequisites

- Python 3.11
- Git
- Windows, macOS or Linux

### Step 1: Clone the repository

```bash
git clone https://github.com/mdnooraj14/Returns-Management-System.git
cd Returns-Management-System
```

### Step 2: Create a virtual environment

**Windows PowerShell:**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Generate the full dataset and execute the pipeline

```bash
python -m rma.cli all --scale 1 --out output/full
```

This command generates the synthetic dataset, exports the data, performs SQL validation, replays business rules and produces evaluation reports.

### Step 5: Run automated tests

```bash
python -m pytest tests -q
```

### Step 6: Launch the dashboard

```bash
streamlit run dashboard/app.py
```

Open the local URL displayed in the terminal, usually:

http://localhost:8501

The repository includes a starter dataset at `output/starter/` for exploring the dashboard without first generating the full dataset.

## 5. Command-Line Operations

The CLI supports the following operations:

| Command | Purpose |
|---|---|
| `generate` | Generate synthetic datasets |
| `validate` | Execute SQL and data validation |
| `detect` | Run anomaly detection and rules evaluation |
| `reproduce` | Regenerate datasets and compare checksums |
| `all` | Execute the complete pipeline |

### Generate a dataset

```bash
python -m rma.cli generate --seed 20261022 --scale 1.0 --out output/full
```

### Run validation

```bash
python -m rma.cli validate --out output/full
```

### Run anomaly detection

```bash
python -m rma.cli detect --out output/full
```

### Verify reproducibility

```bash
python -m rma.cli reproduce --scale 1 --out output/full
```

### Generate a smaller dataset

```bash
python -m rma.cli all --scale 0.1 --out output/demo
```

The `--scale` parameter controls the generated data volume.

## 6. Dataset Overview

The full dataset is generated using seed `20261022`.

| Table | Records | Table | Records |
|---|---:|---|---:|
| customer | 12,000 | inspection | 5,473 |
| product | 600 | inventory_disposition | 5,469 |
| return_policy | 9 | inventory_movement | 6,027 |
| orders | 30,000 | refund | 3,315 |
| order_line | 73,309 | refund_line | 4,619 |
| return_request | 5,000 | return_authorization | 4,348 |
| return_line | 8,000 | return_shipment | 4,543 |
| shipment_line | 6,477 | state_event | 48,094 |

The starter dataset uses a scale of `0.1` and contains:

- 3,000 orders.
- 500 return requests.
- 800 return lines.

### Generated output structure

Each dataset directory contains:

```text
output/
├── starter/
│   ├── data/
│   │   └── *.csv
│   ├── json/
│   │   └── *.json
│   ├── sql/
│   │   ├── schema.sql
│   │   └── seed.sql
│   ├── ground_truth/
│   │   ├── anomalies.csv
│   │   ├── decisions.csv
│   │   └── scenario_labels.csv
│   ├── reports/
│   │   ├── detections.csv
│   │   ├── metrics.json
│   │   ├── metrics.md
│   │   ├── reproducibility.json
│   │   ├── reproducibility.md
│   │   ├── validation_summary.json
│   │   └── validation_summary.md
│   └── manifest.json
```

Ground-truth labels are kept separate from the generated input datasets.

The manifest records the seed, generation command, library versions, row counts, file checksums and provenance information.

## 7. Data Model and Entity Relationships

The database contains 16 tables covering the complete returns workflow.

The model includes the required business entities along with supporting entities and bridge tables.

The main entities include:

- Customer
- Product
- Orders
- Order Line
- Return Policy
- Return Request
- Return Line
- Return Authorization
- Return Shipment
- Shipment Line
- Inspection
- Refund
- Refund Line
- Inventory Disposition
- Inventory Movement
- State Event

The schema and documentation are maintained through `rma/schema.py`.

Supporting documentation:

- [Entity Relationship Diagram](docs/ERD.md)
- [Data Dictionary](docs/data_dictionary.md)
- [SQL Schema](sql/schema.sql)

## 8. Business Rules and Processing Logic

### Return Eligibility

Return eligibility is calculated using the effective-dated return policy and the order delivery date.

The configured policy includes:

| Category | Return Window |
|---|---:|
| Apparel | 30 days |
| Footwear | 30 days |
| Home | 30 days |
| Electronics | 15 days |
| Beauty | 14 days |
| Clearance | Final sale |
| Perishables | Final sale |
| Gift Cards | Final sale |

Electronics has a 20-day window from June 1, 2026.

Seller-fault reasons receive an additional 15 days.

Late requests may be approved through the recorded goodwill override:

- GOLD: up to 21 days late.
- SILVER: up to 10 days late.

### Refund Calculation

Refunds are calculated using the paid share of the returned order line.

The calculation considers:

- Gross line amount.
- Allocated order discount.
- Tax.
- Restocking fees.
- Product condition deductions.
- Return shipping fees.

Partial returns use proportional rounding that reconciles across returned quantities.

Condition deductions:

- Grade B: 15%.
- Grade C: 40%.
- Grade D: refund denied for customer-fault returns.

Wrong items and suspected fraud are also subject to refund-denial rules for customer-fault returns.

A $7.99 return shipping fee applies, with waivers for GOLD customers and seller-fault returns.

### Inventory Disposition

Inspection results determine the returned product's inventory disposition.

| Inspection Grade | Disposition |
|---|---|
| A | Restock |
| B | Refurbish |
| C | Refurbish if unit cost is at least $15; otherwise scrap |
| D | Scrap |
| W / S | Quarantine |

Only inspected RESTOCK items increase sellable inventory.

### Duplicate Refund Prevention

A refund ledger uses an idempotency key to prevent a second payout for the same transaction.

### Lifecycle Management

State changes are recorded as append-only `state_event` records.

The current status is derived from the latest event.

The snapshot date is October 22, 2026, so some requests are legitimately still in progress.

## 9. Anomaly Detection and Ground Truth

The dataset includes 400 injected anomaly cases across five predefined categories.

| Anomaly Type | Injected Cases |
|---|---:|
| Return quantity exceeds purchased quantity | 80 |
| Refund exceeds paid amount | 80 |
| Restock before inspection | 80 |
| Late return without override | 80 |
| Duplicate refund | 80 |
| **Total** | **400** |

The ground-truth files contain the expected decisions, scenario labels and anomaly details.

The normal input datasets do not contain explicit labels identifying injected anomalies.

## 10. Validation and Evaluation Results

The full dataset was evaluated using SQL validation, business-rule replay, anomaly detection and reproducibility checks.

### SQL Validation

**359 out of 359 checks passed.**

| Validation Category | Checks |
|---|---:|
| Structural checks | 317 |
| Invariant checks | 36 |
| Business checks | 6 |
| **Total** | **359** |

The checks cover primary keys, foreign keys, uniqueness, required values, ID formats, data types, dates, financial reconciliation, lifecycle consistency and business rules.

Ten mutation tests verify that the validator detects deliberately corrupted data.

### Anomaly Detection

The rules replay evaluation reported:

| Metric | Result |
|---|---:|
| Precision | 1.0 |
| Recall | 1.0 |
| F1 Score | 1.0 |
| Injected anomalies | 400 |
| Unlabelled flags | 0 |

**Important evaluation limitation:** The anomaly detector re-applies the same business rules used to generate the synthetic anomalies. These results demonstrate rule consistency on the generated dataset, not generalization to unseen real-world anomalies.

### Reproducibility

The reproducibility evaluation confirmed:

- 40 out of 40 files matched across the tested runs.
- SHA-256 checksums and row counts were compared.
- Same-seed runs produced identical outputs.
- A different seed produced different output.

### Automated Testing

Run the test suite using:

```bash
python -m pytest tests -q
```

## 11. Dashboard

The Streamlit dashboard provides an interactive view of the generated returns data.

Its main sections include:

- **Overview:** Key return and refund metrics.
- **Decisions:** Return eligibility and approval outcomes.
- **Exceptions:** Detected anomalies and exception analysis.
- **Trace an RMA:** Detailed lifecycle tracking for an individual return.
- **Financials:** Refunds, fees and recovery analysis.
- **Data Quality:** SQL validation, business checks and reproducibility results.

Launch the dashboard:

```bash
streamlit run dashboard/app.py
```

## 12. Assumptions and Limitations

- All records are synthetic and are not based on external retail datasets.
- Reason, condition, price and processing-time distributions use manually configured parameters rather than fitted real-world distributions.
- The evaluation metrics reflect the predefined synthetic scenarios.
- Money is represented in USD cents.
- The system uses one currency.
- Tax calculation uses a simplified state tax table.
- Multi-shipment order splitting is not supported.
- The snapshot date is fixed at October 22, 2026.

## 13. Data Provenance and Privacy

All generated records are synthetic.

Customer names are selected from built-in lists, and email addresses use the reserved `example.com` domain.

No external or public customer datasets are used.

The manifest records generation metadata, seed, library versions, row counts and file checksums.

## 14. Project Documentation

Additional project documentation:

- [Entity Relationship Diagram](docs/ERD.md)
- [Data Dictionary](docs/data_dictionary.md)
- [AI Usage and Development Disclosure](docs/AI_USAGE.md)

## 15. License and Usage

This project was developed as part of the YottaFlex AI Recruitment Drive candidate project submission.
