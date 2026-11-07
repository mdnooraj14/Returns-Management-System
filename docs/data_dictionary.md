# Data Dictionary

Generated from `rma/schema.py` (single source of truth). Money is integer USD cents; dates are ISO `YYYY-MM-DD`; timestamps are ISO-8601. Every enum is enforced by a `CHECK` constraint and every FK by a `FOREIGN KEY`.

## Relationship overview

| Parent | Child | Cardinality | Optional? |
|---|---|---|---|
| customer | orders | 1:N | child FK required |
| orders | order_line | 1:N | child FK required |
| product | order_line | 1:N | child FK required |
| orders | return_request | 1:N | child FK required |
| customer | return_request | 1:N | child FK required |
| return_request | return_line | 1:N | child FK required |
| order_line | return_line | 1:N | child FK required |
| return_request | return_authorization | 1:1 (optional) | child FK required |
| return_authorization | return_shipment | 1:N | child FK required |
| return_shipment | shipment_line | 1:N | child FK required |
| return_line | shipment_line | 1:N | child FK required |
| return_line | inspection | 1:1 (optional) | child FK required |
| return_shipment | inspection | 1:N | child FK required |
| inspection | inventory_disposition | 1:1 (optional) | child FK required |
| return_line | inventory_disposition | 1:N | child FK required |
| product | inventory_disposition | 1:N | child FK required |
| inventory_disposition | inventory_movement | 1:N | child FK nullable |
| return_line | inventory_movement | 1:N | child FK required |
| product | inventory_movement | 1:N | child FK required |
| return_request | refund | 1:N | child FK required |
| refund | refund_line | 1:N | child FK required |
| return_line | refund_line | 1:N | child FK required |
| order_line | refund_line | 1:N | child FK required |
| return_shipment | return_line | N:M via shipment_line | – |
| refund | return_line | N:M via refund_line | – |

## customer

Customer master data.

- **Primary key:** `customer_id`
- **Cardinality:** Customer 1:N Order

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| customer_id | id | Y |  |  | PK |  | ^CUST-\d{6}$ |
| first_name | str | Y |  |  |  |  |  |
| last_name | str | Y |  |  |  |  |  |
| email | str | Y |  |  | yes |  | synthetic address on example.com |
| state | enum | Y | CA, NY, TX, FL, WA, IL, PA, OR, NC, OH |  |  |  | US state used for tax |
| loyalty_tier | enum | Y | STANDARD, SILVER, GOLD |  |  |  | drives goodwill override eligibility |
| created_date | date | Y |  |  |  |  | ISO date; <= first order_date of the customer |

## product

Product/SKU master.

- **Primary key:** `product_id`
- **Cardinality:** Product 1:N OrderLine

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| product_id | id | Y |  |  | PK |  | ^SKU-\d{6}$ |
| name | str | Y |  |  |  |  |  |
| category | enum | Y | APPAREL, FOOTWEAR, ELECTRONICS, HOME, BEAUTY, CLEARANCE, PERISHABLES, GIFT_CARDS |  |  |  |  |
| unit_price_cents | cents | Y |  | USD cents |  |  | list price > 0 |
| unit_cost_cents | cents | Y |  | USD cents |  |  | < unit_price_cents; drives refurbish-vs-scrap |

## return_policy

Versioned return policy per category (effective dated).

- **Primary key:** `policy_id`
- **Cardinality:** Category 1:N policy versions; version applies by delivery_date
- **Composite uniqueness:** (category, effective_from)

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| policy_id | id | Y |  |  | PK |  | ^POL-[A-Z_]+-V\d+$ |
| category | enum | Y | APPAREL, FOOTWEAR, ELECTRONICS, HOME, BEAUTY, CLEARANCE, PERISHABLES, GIFT_CARDS |  |  |  |  |
| window_days | int | Y |  | days |  |  | counted from delivery_date, inclusive |
| defect_extension_days | int | Y |  | days |  |  | added when reason is seller-fault |
| final_sale | bool | Y |  |  |  |  | 1 = category excluded from returns |
| requires_unopened | bool | Y |  |  |  |  | 1 = opened items rejected unless seller-fault |
| restocking_fee_bps_opened | int | Y |  | basis points |  |  | fee on paid share when item not SEALED |
| effective_from | date | Y |  |  |  |  |  |
| effective_to | date | N |  |  |  |  | NULL = open ended; versions of one category must not overlap |

## orders

Customer order header; totals are derived from lines.

- **Primary key:** `order_id`
- **Cardinality:** Order 1:N OrderLine; Order 0..N ReturnRequest
- **Lifecycle:** `DELIVERED | CANCELLED`

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| order_id | id | Y |  |  | PK |  | ^ORD-2026-\d{6}$ |
| customer_id | id | Y |  |  |  | customer.customer_id |  |
| order_date | date | Y |  |  |  |  | 2026-01-01..2026-09-30 |
| status | enum | Y | DELIVERED, CANCELLED |  |  |  |  |
| delivery_date | date | N |  |  |  |  | NULL iff CANCELLED; >= order_date |
| ship_state | enum | Y | CA, NY, TX, FL, WA, IL, PA, OR, NC, OH |  |  |  |  |
| payment_method | enum | Y | CARD, PAYPAL, APPLE_PAY |  |  |  |  |
| coupon_code | enum | N | SAVE5, SAVE10, SAVE15, SAVE20 |  |  |  |  |
| subtotal_cents | cents | Y |  | USD cents |  |  | = SUM(line gross) |
| discount_cents | cents | Y |  | USD cents |  |  | = SUM(line discount) |
| shipping_cents | cents | Y |  | USD cents |  |  | 0 if subtotal-discount >= 7500 else 599 |
| tax_cents | cents | Y |  | USD cents |  |  | = SUM(line tax) |
| total_cents | cents | Y |  | USD cents |  |  | = subtotal - discount + shipping + tax |

## order_line

Purchased line; per-line discount/tax allocation used for refund math.

- **Primary key:** `order_line_id`
- **Cardinality:** OrderLine 0..N ReturnLine
- **Composite uniqueness:** (order_id, line_no)

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| order_line_id | id | Y |  |  | PK |  | ^ORDL-ORD-2026-\d{6}-\d{2}$ |
| order_id | id | Y |  |  |  | orders.order_id |  |
| line_no | int | Y |  |  |  |  |  |
| product_id | id | Y |  |  |  | product.product_id |  |
| category | enum | Y | APPAREL, FOOTWEAR, ELECTRONICS, HOME, BEAUTY, CLEARANCE, PERISHABLES, GIFT_CARDS |  |  |  | category snapshot at purchase |
| quantity | int | Y |  | units |  |  |  |
| unit_price_cents | cents | Y |  | USD cents |  |  |  |
| gross_cents | cents | Y |  | USD cents |  |  | = quantity * unit_price |
| discount_cents | cents | Y |  | USD cents |  |  | order discount allocated by largest remainder over gross |
| net_cents | cents | Y |  | USD cents |  |  | = gross - discount |
| tax_rate_bps | int | Y |  | basis points |  |  |  |
| tax_cents | cents | Y |  | USD cents |  |  | = round_half_up(net * bps / 10000); 0 for exempt categories |
| paid_cents | cents | Y |  | USD cents |  |  | = net + tax (shipping excluded) |

## return_request

Customer return request (RMA header).

- **Primary key:** `return_request_id`
- **Cardinality:** Request 1:N ReturnLine; Request 0..1 ReturnAuthorization
- **Lifecycle:** `SUBMITTED>(REJECTED|AUTHORIZED>(EXPIRED|SHIPPED>(CLAIM_OPENED>CLOSED|RECEIVED>INSPECTED>(REFUNDED>)?CLOSED))`

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| return_request_id | id | Y |  |  | PK |  | ^RMA-2026-\d{6}$ |
| order_id | id | Y |  |  |  | orders.order_id |  |
| customer_id | id | Y |  |  |  | customer.customer_id | must equal orders.customer_id |
| requested_at | date | Y |  |  |  |  | >= order delivery_date; <= snapshot 2026-10-22 |
| channel | enum | Y | WEB, APP, STORE, CALL |  |  |  |  |
| resolution_requested | enum | Y | REFUND, EXCHANGE |  |  |  |  |
| refund_method | enum | N | ORIGINAL_PAYMENT, STORE_CREDIT |  |  |  | NULL for EXCHANGE |
| status | enum | Y | SUBMITTED, REJECTED, AUTHORIZED, SHIPPED, RECEIVED, INSPECTED, REFUNDED, CLOSED, EXPIRED, CLAIM_OPENED |  |  |  | derived: equals last state_event.to_state |

## return_line

Requested quantity of one order line plus the eligibility decision.

- **Primary key:** `return_line_id`
- **Cardinality:** ReturnLine 0..1 Inspection; N:M ReturnLine<->ReturnShipment via shipment_line; N:M ReturnLine<->Refund via refund_line
- **Composite uniqueness:** (return_request_id, line_no); (return_request_id, order_line_id)

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| return_line_id | id | Y |  |  | PK |  | ^RMAL-RMA-2026-\d{6}-\d{2}$ |
| return_request_id | id | Y |  |  |  | return_request.return_request_id |  |
| line_no | int | Y |  |  |  |  |  |
| order_line_id | id | Y |  |  |  | order_line.order_line_id |  |
| qty_requested | int | Y |  | units |  |  | sum over requests <= purchased quantity (baseline) |
| reason_code | enum | Y | SIZE_FIT, CHANGED_MIND, NO_LONGER_NEEDED, NOT_AS_DESCRIBED, DEFECTIVE, DAMAGED_IN_TRANSIT, WRONG_ITEM |  |  |  |  |
| condition_declared | enum | Y | UNOPENED, OPENED, DAMAGED, DEFECTIVE |  |  |  |  |
| line_decision | enum | Y | PENDING, APPROVED, APPROVED_OVERRIDE, REJECTED |  |  |  | PENDING iff decided_at NULL |
| decision_reason | enum | N | ELIGIBLE, LATE_OVERRIDE, FINAL_SALE_CATEGORY, LATE_REQUEST, OPENED_NOT_RETURNABLE, QTY_EXHAUSTED |  |  |  |  |
| qty_approved | int | N |  | units |  |  | <= purchased minus previously approved |
| override_code | enum | N | GOODWILL_GOLD, GOODWILL_SILVER |  |  |  | required when approved after window |
| override_approved_by | str | N |  |  |  |  | MGR-nn when override_code set |
| decided_at | date | N |  |  |  |  |  |

## return_authorization

Authorization issued when >=1 line is approved (effective decided_at..expires_at).

- **Primary key:** `authorization_id`
- **Cardinality:** Request 1:0..1 Authorization; Authorization 1:N ReturnShipment

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| authorization_id | id | Y |  |  | PK |  | ^AUTH-2026-\d{6}$ |
| return_request_id | id | Y |  |  | yes | return_request.return_request_id |  |
| decision | enum | Y | APPROVED, PARTIALLY_APPROVED |  |  |  |  |
| decided_at | date | Y |  |  |  |  |  |
| expires_at | date | Y |  |  |  |  | = decided_at + 21 days |
| authorized_by | str | Y |  |  |  |  | SYSTEM or MGR-nn (override) |

## return_shipment

Return parcel / label.

- **Primary key:** `shipment_id`
- **Cardinality:** Shipment 1:N ShipmentLine
- **Lifecycle:** `LABEL_ISSUED>(VOIDED|IN_TRANSIT>(RECEIVED|LOST))`

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| shipment_id | id | Y |  |  | PK |  | ^RTS-2026-\d{6}$ |
| authorization_id | id | Y |  |  |  | return_authorization.authorization_id |  |
| carrier | enum | Y | UPS, USPS, FEDEX |  |  |  |  |
| tracking_number | str | Y |  |  | yes |  |  |
| label_issued_at | date | Y |  |  |  |  | >= authorization.decided_at |
| shipped_at | date | N |  |  |  |  | >= label_issued_at |
| received_at | date | N |  |  |  |  | >= shipped_at |
| status | enum | Y | LABEL_ISSUED, IN_TRANSIT, RECEIVED, LOST, VOIDED |  |  |  | derived: last state_event.to_state |

## shipment_line

Bridge ReturnShipment <-> ReturnLine (N:M).

- **Primary key:** `shipment_line_id`
- **Composite uniqueness:** (shipment_id, return_line_id)

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| shipment_line_id | id | Y |  |  | PK |  | ^RTSL-RTS-2026-\d{6}-\d{2}$ |
| shipment_id | id | Y |  |  |  | return_shipment.shipment_id |  |
| return_line_id | id | Y |  |  |  | return_line.return_line_id |  |
| qty_expected | int | Y |  | units |  |  | = qty_approved of the line |
| qty_shipped | int | N |  | units |  |  | <= qty_expected |
| qty_received | int | N |  | units |  |  | <= qty_shipped |

## inspection

Warehouse inspection of a returned line.

- **Primary key:** `inspection_id`
- **Cardinality:** ReturnLine 1:0..1 Inspection; Inspection 1:1 InventoryDisposition

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| inspection_id | id | Y |  |  | PK |  | ^INSP-2026-\d{6}$ |
| return_line_id | id | Y |  |  | yes | return_line.return_line_id |  |
| shipment_id | id | Y |  |  |  | return_shipment.shipment_id |  |
| inspected_at | date | Y |  |  |  |  | >= shipment.received_at |
| inspector_id | str | Y |  |  |  |  |  |
| qty_inspected | int | Y |  | units |  |  | = shipment_line.qty_received |
| condition_found | enum | Y | SEALED, LIKE_NEW, USED, DAMAGED_MINOR, DAMAGED_SEVERE, DEFECTIVE, NOT_ORIGINAL_ITEM, SUSPECT_FRAUD |  |  |  |  |
| grade | enum | Y | A, B, C, D, W, S |  |  |  | derived from condition_found + category |
| fault_party | enum | Y | SELLER, CUSTOMER |  |  |  | SELLER iff reason claim consistent with condition_found |
| refund_eligible | bool | Y |  |  |  |  |  |

## inventory_disposition

Disposition decision for inspected goods.

- **Primary key:** `disposition_id`
- **Cardinality:** Disposition 1:0..1 InventoryMovement

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| disposition_id | id | Y |  |  | PK |  | ^DISP-2026-\d{6}$ |
| inspection_id | id | Y |  |  | yes | inspection.inspection_id |  |
| return_line_id | id | Y |  |  |  | return_line.return_line_id |  |
| product_id | id | Y |  |  |  | product.product_id |  |
| disposition | enum | Y | RESTOCK, REFURBISH, QUARANTINE, SCRAP |  |  |  | A>RESTOCK B>REFURBISH C>REFURBISH if cost>=1500 else SCRAP D>SCRAP W,S>QUARANTINE |
| qty | int | Y |  | units |  |  | = qty_inspected |
| destination_location | enum | Y | SELLABLE, REFURB, QUARANTINE, SCRAP |  |  |  |  |
| decided_at | date | Y |  |  |  |  | >= inspected_at |
| est_recovery_cents | cents | Y |  | USD cents |  |  | unit_price * qty * recovery factor |

## inventory_movement

Stock ledger entry caused by a disposition (or an exchange replacement).

- **Primary key:** `movement_id`

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| movement_id | id | Y |  |  | PK |  | ^MOV-2026-\d{6}$ |
| disposition_id | id | N |  |  |  | inventory_disposition.disposition_id | NULL only for EXCHANGE_OUTBOUND |
| return_line_id | id | Y |  |  |  | return_line.return_line_id |  |
| product_id | id | Y |  |  |  | product.product_id |  |
| movement_type | enum | Y | RETURN_RESTOCK, REFURB_INTAKE, QUARANTINE_HOLD, SCRAP_WRITEOFF, EXCHANGE_OUTBOUND |  |  |  |  |
| location | enum | Y | SELLABLE, REFURB, QUARANTINE, SCRAP |  |  |  |  |
| qty | int | Y |  | units |  |  |  |
| sellable_qty_delta | int | Y |  | units |  |  | >0 only for RETURN_RESTOCK; <0 only for EXCHANGE_OUTBOUND |
| posted_at | date | Y |  |  |  |  | >= inspection.inspected_at (restock never precedes inspection) |

## refund

Refund payout attempt (idempotent per request).

- **Primary key:** `refund_id`
- **Cardinality:** Request 1:N Refund attempts; Refund N:M ReturnLine via refund_line
- **Lifecycle:** `INITIATED>(ISSUED|BLOCKED_DUPLICATE)`
- **Composite uniqueness:** (return_request_id, attempt_no)

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| refund_id | id | Y |  |  | PK |  | ^REF-2026-\d{6}$ |
| return_request_id | id | Y |  |  |  | return_request.return_request_id |  |
| idempotency_key | str | Y |  |  |  |  | IDEM:<return_request_id>; one ISSUED payout per key |
| attempt_no | int | Y |  |  |  |  |  |
| method | enum | Y | ORIGINAL_PAYMENT, STORE_CREDIT |  |  |  |  |
| status | enum | Y | ISSUED, BLOCKED_DUPLICATE |  |  |  | derived: last state_event.to_state |
| refund_date | date | Y |  |  |  |  | >= every inspection of the request |
| refund_amount_cents | cents | Y |  | USD cents |  |  | attempt 1: = SUM(refund_line.refund_cents) - shipping fee |
| paid_cents | cents | Y |  | USD cents |  |  | = refund_amount for ISSUED, 0 for BLOCKED_DUPLICATE |
| return_shipping_fee_cents | cents | Y |  | USD cents |  |  | 799 flat for customer-fault, non-GOLD; capped at line total |
| currency | enum | Y | USD |  |  |  |  |

## refund_line

Bridge Refund <-> ReturnLine with the refund math (attempt 1 only).

- **Primary key:** `refund_line_id`
- **Composite uniqueness:** (refund_id, return_line_id)

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| refund_line_id | id | Y |  |  | PK |  | ^REFL-REF-2026-\d{6}-\d{2}$ |
| refund_id | id | Y |  |  |  | refund.refund_id |  |
| return_line_id | id | Y |  |  |  | return_line.return_line_id |  |
| order_line_id | id | Y |  |  |  | order_line.order_line_id |  |
| qty_refunded | int | Y |  | units |  |  |  |
| gross_cents | cents | Y |  | USD cents |  |  | telescoping proration of order_line.gross |
| discount_cents | cents | Y |  | USD cents |  |  | telescoping proration of order_line.discount |
| tax_cents | cents | Y |  | USD cents |  |  | telescoping proration of order_line.tax |
| paid_share_cents | cents | Y |  | USD cents |  |  | = gross - discount + tax |
| restocking_fee_cents | cents | Y |  | USD cents |  |  |  |
| condition_deduction_cents | cents | Y |  | USD cents |  |  |  |
| refund_cents | cents | Y |  | USD cents |  |  | = paid_share - restocking_fee - condition_deduction |

## state_event

Append-only lifecycle history; state columns are derived from it.

- **Primary key:** `event_id`

| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| event_id | id | Y |  |  | PK |  | ^EVT-\d{9}$ |
| entity_type | enum | Y | RETURN_REQUEST, RETURN_SHIPMENT, REFUND |  |  |  |  |
| entity_id | id | Y |  |  |  |  | polymorphic reference; validated per entity_type by SQL |
| from_state | str | N |  |  |  |  | NULL on the initial event |
| to_state | str | Y |  |  |  |  |  |
| event_ts | ts | Y |  |  |  |  | ISO-8601 seconds; <= snapshot date end |
| actor | enum | Y | SYSTEM, CUSTOMER, AGENT, WAREHOUSE, FINANCE, CARRIER |  |  |  |  |
| reason | str | N |  |  |  |  |  |
