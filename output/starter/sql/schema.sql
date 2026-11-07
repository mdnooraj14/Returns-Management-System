-- Generated from rma/schema.py. Structural constraints only; business rules are checked by sql/validation_checks.sql.
PRAGMA foreign_keys = ON;

CREATE TABLE customer (
  customer_id TEXT NOT NULL PRIMARY KEY,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK (state IN ('CA', 'NY', 'TX', 'FL', 'WA', 'IL', 'PA', 'OR', 'NC', 'OH')),
  loyalty_tier TEXT NOT NULL CHECK (loyalty_tier IN ('STANDARD', 'SILVER', 'GOLD')),
  created_date TEXT NOT NULL
);

CREATE TABLE product (
  product_id TEXT NOT NULL PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL CHECK (category IN ('APPAREL', 'FOOTWEAR', 'ELECTRONICS', 'HOME', 'BEAUTY', 'CLEARANCE', 'PERISHABLES', 'GIFT_CARDS')),
  unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 1),
  unit_cost_cents INTEGER NOT NULL CHECK (unit_cost_cents >= 1)
);

CREATE TABLE return_policy (
  policy_id TEXT NOT NULL PRIMARY KEY,
  category TEXT NOT NULL CHECK (category IN ('APPAREL', 'FOOTWEAR', 'ELECTRONICS', 'HOME', 'BEAUTY', 'CLEARANCE', 'PERISHABLES', 'GIFT_CARDS')),
  window_days INTEGER NOT NULL CHECK (window_days >= 0),
  defect_extension_days INTEGER NOT NULL CHECK (defect_extension_days >= 0),
  final_sale INTEGER NOT NULL CHECK (final_sale IN (0, 1)),
  requires_unopened INTEGER NOT NULL CHECK (requires_unopened IN (0, 1)),
  restocking_fee_bps_opened INTEGER NOT NULL CHECK (restocking_fee_bps_opened >= 0),
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  UNIQUE (category, effective_from)
);

CREATE TABLE orders (
  order_id TEXT NOT NULL PRIMARY KEY,
  customer_id TEXT NOT NULL,
  order_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('DELIVERED', 'CANCELLED')),
  delivery_date TEXT,
  ship_state TEXT NOT NULL CHECK (ship_state IN ('CA', 'NY', 'TX', 'FL', 'WA', 'IL', 'PA', 'OR', 'NC', 'OH')),
  payment_method TEXT NOT NULL CHECK (payment_method IN ('CARD', 'PAYPAL', 'APPLE_PAY')),
  coupon_code TEXT CHECK (coupon_code IN ('SAVE5', 'SAVE10', 'SAVE15', 'SAVE20')),
  subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0),
  discount_cents INTEGER NOT NULL CHECK (discount_cents >= 0),
  shipping_cents INTEGER NOT NULL CHECK (shipping_cents >= 0),
  tax_cents INTEGER NOT NULL CHECK (tax_cents >= 0),
  total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
  FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);

CREATE TABLE order_line (
  order_line_id TEXT NOT NULL PRIMARY KEY,
  order_id TEXT NOT NULL,
  line_no INTEGER NOT NULL CHECK (line_no >= 1),
  product_id TEXT NOT NULL,
  category TEXT NOT NULL CHECK (category IN ('APPAREL', 'FOOTWEAR', 'ELECTRONICS', 'HOME', 'BEAUTY', 'CLEARANCE', 'PERISHABLES', 'GIFT_CARDS')),
  quantity INTEGER NOT NULL CHECK (quantity >= 1),
  unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
  gross_cents INTEGER NOT NULL CHECK (gross_cents >= 0),
  discount_cents INTEGER NOT NULL CHECK (discount_cents >= 0),
  net_cents INTEGER NOT NULL CHECK (net_cents >= 0),
  tax_rate_bps INTEGER NOT NULL CHECK (tax_rate_bps >= 0),
  tax_cents INTEGER NOT NULL CHECK (tax_cents >= 0),
  paid_cents INTEGER NOT NULL CHECK (paid_cents >= 0),
  UNIQUE (order_id, line_no),
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (product_id) REFERENCES product(product_id)
);

CREATE TABLE return_request (
  return_request_id TEXT NOT NULL PRIMARY KEY,
  order_id TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  channel TEXT NOT NULL CHECK (channel IN ('WEB', 'APP', 'STORE', 'CALL')),
  resolution_requested TEXT NOT NULL CHECK (resolution_requested IN ('REFUND', 'EXCHANGE')),
  refund_method TEXT CHECK (refund_method IN ('ORIGINAL_PAYMENT', 'STORE_CREDIT')),
  status TEXT NOT NULL CHECK (status IN ('SUBMITTED', 'REJECTED', 'AUTHORIZED', 'SHIPPED', 'RECEIVED', 'INSPECTED', 'REFUNDED', 'CLOSED', 'EXPIRED', 'CLAIM_OPENED')),
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);

CREATE TABLE return_line (
  return_line_id TEXT NOT NULL PRIMARY KEY,
  return_request_id TEXT NOT NULL,
  line_no INTEGER NOT NULL CHECK (line_no >= 1),
  order_line_id TEXT NOT NULL,
  qty_requested INTEGER NOT NULL CHECK (qty_requested >= 1),
  reason_code TEXT NOT NULL CHECK (reason_code IN ('SIZE_FIT', 'CHANGED_MIND', 'NO_LONGER_NEEDED', 'NOT_AS_DESCRIBED', 'DEFECTIVE', 'DAMAGED_IN_TRANSIT', 'WRONG_ITEM')),
  condition_declared TEXT NOT NULL CHECK (condition_declared IN ('UNOPENED', 'OPENED', 'DAMAGED', 'DEFECTIVE')),
  line_decision TEXT NOT NULL CHECK (line_decision IN ('PENDING', 'APPROVED', 'APPROVED_OVERRIDE', 'REJECTED')),
  decision_reason TEXT CHECK (decision_reason IN ('ELIGIBLE', 'LATE_OVERRIDE', 'FINAL_SALE_CATEGORY', 'LATE_REQUEST', 'OPENED_NOT_RETURNABLE', 'QTY_EXHAUSTED')),
  qty_approved INTEGER CHECK (qty_approved >= 0),
  override_code TEXT CHECK (override_code IN ('GOODWILL_GOLD', 'GOODWILL_SILVER')),
  override_approved_by TEXT,
  decided_at TEXT,
  UNIQUE (return_request_id, line_no),
  UNIQUE (return_request_id, order_line_id),
  FOREIGN KEY (return_request_id) REFERENCES return_request(return_request_id),
  FOREIGN KEY (order_line_id) REFERENCES order_line(order_line_id)
);

CREATE TABLE return_authorization (
  authorization_id TEXT NOT NULL PRIMARY KEY,
  return_request_id TEXT NOT NULL UNIQUE,
  decision TEXT NOT NULL CHECK (decision IN ('APPROVED', 'PARTIALLY_APPROVED')),
  decided_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  authorized_by TEXT NOT NULL,
  FOREIGN KEY (return_request_id) REFERENCES return_request(return_request_id)
);

CREATE TABLE return_shipment (
  shipment_id TEXT NOT NULL PRIMARY KEY,
  authorization_id TEXT NOT NULL,
  carrier TEXT NOT NULL CHECK (carrier IN ('UPS', 'USPS', 'FEDEX')),
  tracking_number TEXT NOT NULL UNIQUE,
  label_issued_at TEXT NOT NULL,
  shipped_at TEXT,
  received_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('LABEL_ISSUED', 'IN_TRANSIT', 'RECEIVED', 'LOST', 'VOIDED')),
  FOREIGN KEY (authorization_id) REFERENCES return_authorization(authorization_id)
);

CREATE TABLE shipment_line (
  shipment_line_id TEXT NOT NULL PRIMARY KEY,
  shipment_id TEXT NOT NULL,
  return_line_id TEXT NOT NULL,
  qty_expected INTEGER NOT NULL CHECK (qty_expected >= 1),
  qty_shipped INTEGER CHECK (qty_shipped >= 0),
  qty_received INTEGER CHECK (qty_received >= 0),
  UNIQUE (shipment_id, return_line_id),
  FOREIGN KEY (shipment_id) REFERENCES return_shipment(shipment_id),
  FOREIGN KEY (return_line_id) REFERENCES return_line(return_line_id)
);

CREATE TABLE inspection (
  inspection_id TEXT NOT NULL PRIMARY KEY,
  return_line_id TEXT NOT NULL UNIQUE,
  shipment_id TEXT NOT NULL,
  inspected_at TEXT NOT NULL,
  inspector_id TEXT NOT NULL,
  qty_inspected INTEGER NOT NULL CHECK (qty_inspected >= 1),
  condition_found TEXT NOT NULL CHECK (condition_found IN ('SEALED', 'LIKE_NEW', 'USED', 'DAMAGED_MINOR', 'DAMAGED_SEVERE', 'DEFECTIVE', 'NOT_ORIGINAL_ITEM', 'SUSPECT_FRAUD')),
  grade TEXT NOT NULL CHECK (grade IN ('A', 'B', 'C', 'D', 'W', 'S')),
  fault_party TEXT NOT NULL CHECK (fault_party IN ('SELLER', 'CUSTOMER')),
  refund_eligible INTEGER NOT NULL CHECK (refund_eligible IN (0, 1)),
  FOREIGN KEY (return_line_id) REFERENCES return_line(return_line_id),
  FOREIGN KEY (shipment_id) REFERENCES return_shipment(shipment_id)
);

CREATE TABLE inventory_disposition (
  disposition_id TEXT NOT NULL PRIMARY KEY,
  inspection_id TEXT NOT NULL UNIQUE,
  return_line_id TEXT NOT NULL,
  product_id TEXT NOT NULL,
  disposition TEXT NOT NULL CHECK (disposition IN ('RESTOCK', 'REFURBISH', 'QUARANTINE', 'SCRAP')),
  qty INTEGER NOT NULL CHECK (qty >= 1),
  destination_location TEXT NOT NULL CHECK (destination_location IN ('SELLABLE', 'REFURB', 'QUARANTINE', 'SCRAP')),
  decided_at TEXT NOT NULL,
  est_recovery_cents INTEGER NOT NULL CHECK (est_recovery_cents >= 0),
  FOREIGN KEY (inspection_id) REFERENCES inspection(inspection_id),
  FOREIGN KEY (return_line_id) REFERENCES return_line(return_line_id),
  FOREIGN KEY (product_id) REFERENCES product(product_id)
);

CREATE TABLE inventory_movement (
  movement_id TEXT NOT NULL PRIMARY KEY,
  disposition_id TEXT,
  return_line_id TEXT NOT NULL,
  product_id TEXT NOT NULL,
  movement_type TEXT NOT NULL CHECK (movement_type IN ('RETURN_RESTOCK', 'REFURB_INTAKE', 'QUARANTINE_HOLD', 'SCRAP_WRITEOFF', 'EXCHANGE_OUTBOUND')),
  location TEXT NOT NULL CHECK (location IN ('SELLABLE', 'REFURB', 'QUARANTINE', 'SCRAP')),
  qty INTEGER NOT NULL CHECK (qty >= 1),
  sellable_qty_delta INTEGER NOT NULL,
  posted_at TEXT NOT NULL,
  FOREIGN KEY (disposition_id) REFERENCES inventory_disposition(disposition_id),
  FOREIGN KEY (return_line_id) REFERENCES return_line(return_line_id),
  FOREIGN KEY (product_id) REFERENCES product(product_id)
);

CREATE TABLE refund (
  refund_id TEXT NOT NULL PRIMARY KEY,
  return_request_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  attempt_no INTEGER NOT NULL CHECK (attempt_no >= 1),
  method TEXT NOT NULL CHECK (method IN ('ORIGINAL_PAYMENT', 'STORE_CREDIT')),
  status TEXT NOT NULL CHECK (status IN ('ISSUED', 'BLOCKED_DUPLICATE')),
  refund_date TEXT NOT NULL,
  refund_amount_cents INTEGER NOT NULL CHECK (refund_amount_cents >= 0),
  paid_cents INTEGER NOT NULL CHECK (paid_cents >= 0),
  return_shipping_fee_cents INTEGER NOT NULL CHECK (return_shipping_fee_cents >= 0),
  currency TEXT NOT NULL CHECK (currency IN ('USD')),
  UNIQUE (return_request_id, attempt_no),
  FOREIGN KEY (return_request_id) REFERENCES return_request(return_request_id)
);

CREATE TABLE refund_line (
  refund_line_id TEXT NOT NULL PRIMARY KEY,
  refund_id TEXT NOT NULL,
  return_line_id TEXT NOT NULL,
  order_line_id TEXT NOT NULL,
  qty_refunded INTEGER NOT NULL CHECK (qty_refunded >= 1),
  gross_cents INTEGER NOT NULL CHECK (gross_cents >= 0),
  discount_cents INTEGER NOT NULL CHECK (discount_cents >= 0),
  tax_cents INTEGER NOT NULL CHECK (tax_cents >= 0),
  paid_share_cents INTEGER NOT NULL CHECK (paid_share_cents >= 0),
  restocking_fee_cents INTEGER NOT NULL CHECK (restocking_fee_cents >= 0),
  condition_deduction_cents INTEGER NOT NULL CHECK (condition_deduction_cents >= 0),
  refund_cents INTEGER NOT NULL CHECK (refund_cents >= 0),
  UNIQUE (refund_id, return_line_id),
  FOREIGN KEY (refund_id) REFERENCES refund(refund_id),
  FOREIGN KEY (return_line_id) REFERENCES return_line(return_line_id),
  FOREIGN KEY (order_line_id) REFERENCES order_line(order_line_id)
);

CREATE TABLE state_event (
  event_id TEXT NOT NULL PRIMARY KEY,
  entity_type TEXT NOT NULL CHECK (entity_type IN ('RETURN_REQUEST', 'RETURN_SHIPMENT', 'REFUND')),
  entity_id TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT NOT NULL,
  event_ts TEXT NOT NULL,
  actor TEXT NOT NULL CHECK (actor IN ('SYSTEM', 'CUSTOMER', 'AGENT', 'WAREHOUSE', 'FINANCE', 'CARRIER')),
  reason TEXT
);
