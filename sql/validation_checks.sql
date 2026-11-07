-- Independent SQL validation suite (SQLite). Written separately from rma/rules.py: policy, windows, lifecycle and math are restated here.
-- Block format:  -- check: <ID> | <layer> | expect=<zero|gt:ISSUE_TYPE> | <description>
-- Every query returns offending entity keys in column `entity_id`.
-- layers: invariant (must be zero on all rows, anomalies included) | business (must equal labelled ground truth exactly)

-- check: D01 | invariant | expect=zero | order delivered before it was placed
SELECT order_id AS entity_id FROM orders WHERE delivery_date < order_date;

-- check: D02 | invariant | expect=zero | delivery_date presence must match order status
SELECT order_id AS entity_id FROM orders WHERE (status = 'CANCELLED' AND delivery_date IS NOT NULL) OR (status = 'DELIVERED' AND delivery_date IS NULL);

-- check: D03 | invariant | expect=zero | return requested before delivery, or for an undelivered order, or after snapshot
SELECT rq.return_request_id AS entity_id FROM return_request rq JOIN orders o ON o.order_id = rq.order_id
WHERE o.status <> 'DELIVERED' OR rq.requested_at < o.delivery_date OR rq.requested_at > '2026-10-22';

-- check: D04 | invariant | expect=zero | line decision date before request, or PENDING/decided_at mismatch
SELECT rl.return_line_id AS entity_id FROM return_line rl JOIN return_request rq ON rq.return_request_id = rl.return_request_id
WHERE rl.decided_at < rq.requested_at OR (rl.line_decision = 'PENDING') <> (rl.decided_at IS NULL);

-- check: D05 | invariant | expect=zero | authorization before request or expiry != decided_at + 21 days
SELECT a.authorization_id AS entity_id FROM return_authorization a JOIN return_request rq ON rq.return_request_id = a.return_request_id
WHERE a.decided_at < rq.requested_at OR julianday(a.expires_at) - julianday(a.decided_at) <> 21;

-- check: D06 | invariant | expect=zero | shipment dates out of order (label <= shipped <= received)
SELECT s.shipment_id AS entity_id FROM return_shipment s JOIN return_authorization a ON a.authorization_id = s.authorization_id
WHERE s.label_issued_at < a.decided_at OR s.shipped_at < s.label_issued_at OR s.received_at < s.shipped_at
   OR (s.received_at IS NOT NULL AND s.shipped_at IS NULL);

-- check: D07 | invariant | expect=zero | inspection before parcel received
SELECT i.inspection_id AS entity_id FROM inspection i JOIN return_shipment s ON s.shipment_id = i.shipment_id
WHERE s.received_at IS NULL OR i.inspected_at < s.received_at;

-- check: D08 | invariant | expect=zero | disposition decided before inspection
SELECT d.disposition_id AS entity_id FROM inventory_disposition d JOIN inspection i ON i.inspection_id = d.inspection_id WHERE d.decided_at < i.inspected_at;

-- check: D09 | invariant | expect=zero | refund paid before an inspection of its request
SELECT DISTINCT r.refund_id AS entity_id FROM refund r JOIN return_line rl ON rl.return_request_id = r.return_request_id
JOIN inspection i ON i.return_line_id = rl.return_line_id WHERE r.refund_date < i.inspected_at;

-- check: D10 | invariant | expect=zero | non-restock movement posted before the inspection
SELECT m.movement_id AS entity_id FROM inventory_movement m JOIN inspection i ON i.return_line_id = m.return_line_id
WHERE m.movement_type <> 'RETURN_RESTOCK' AND m.posted_at < i.inspected_at;

-- check: D11 | invariant | expect=zero | state event after the snapshot date
SELECT event_id AS entity_id FROM state_event WHERE substr(event_ts, 1, 10) > '2026-10-22';

-- check: D12 | invariant | expect=zero | customer created after first order
SELECT c.customer_id AS entity_id FROM customer c JOIN (SELECT customer_id, MIN(order_date) d FROM orders GROUP BY customer_id) f ON f.customer_id = c.customer_id WHERE c.created_date > f.d;

-- check: A01 | invariant | expect=zero | order line arithmetic (gross, net, paid, tax)
SELECT order_line_id AS entity_id FROM order_line
WHERE gross_cents <> quantity * unit_price_cents OR net_cents <> gross_cents - discount_cents OR paid_cents <> net_cents + tax_cents
   OR tax_cents <> (net_cents * tax_rate_bps + 5000) / 10000;

-- check: A02 | invariant | expect=zero | order header totals must equal sum of lines (and have lines)
SELECT o.order_id AS entity_id FROM orders o LEFT JOIN (SELECT order_id, SUM(gross_cents) g, SUM(discount_cents) d, SUM(tax_cents) t FROM order_line GROUP BY order_id) l ON l.order_id = o.order_id
WHERE l.order_id IS NULL OR o.subtotal_cents <> l.g OR o.discount_cents <> l.d OR o.tax_cents <> l.t;

-- check: A03 | invariant | expect=zero | order total and shipping rule
SELECT order_id AS entity_id FROM orders
WHERE total_cents <> subtotal_cents - discount_cents + shipping_cents + tax_cents
   OR shipping_cents <> CASE WHEN subtotal_cents - discount_cents >= 7500 THEN 0 ELSE 599 END;

-- check: A04 | invariant | expect=zero | refund_line paid_share != gross - discount + tax
SELECT refund_line_id AS entity_id FROM refund_line WHERE paid_share_cents <> gross_cents - discount_cents + tax_cents;

-- check: A05 | business | expect=gt:REFUND_EXCEEDS_PAID | refund_line refund != paid_share - restocking fee - condition deduction (entity = refund)
SELECT DISTINCT refund_id AS entity_id FROM refund_line WHERE refund_cents <> paid_share_cents - restocking_fee_cents - condition_deduction_cents;

-- check: A06 | invariant | expect=zero | refund header (attempt 1) != sum of lines - return shipping fee
SELECT r.refund_id AS entity_id FROM refund r LEFT JOIN (SELECT refund_id, SUM(refund_cents) s FROM refund_line GROUP BY refund_id) l ON l.refund_id = r.refund_id
WHERE r.attempt_no = 1 AND (l.s IS NULL OR r.refund_amount_cents <> l.s - r.return_shipping_fee_cents);

-- check: A07 | invariant | expect=zero | paid_cents must equal amount for ISSUED and 0 for BLOCKED_DUPLICATE; replays carry no lines
SELECT r.refund_id AS entity_id FROM refund r
WHERE (r.status = 'ISSUED' AND r.paid_cents <> r.refund_amount_cents) OR (r.status = 'BLOCKED_DUPLICATE' AND r.paid_cents <> 0)
   OR (r.attempt_no > 1 AND EXISTS (SELECT 1 FROM refund_line l WHERE l.refund_id = r.refund_id));

-- check: A08 | invariant | expect=zero | fully returned order line: refunded gross/discount/tax must equal the order line (discount and tax reconciliation)
SELECT ol.order_line_id AS entity_id FROM order_line ol JOIN
 (SELECT order_line_id, SUM(qty_refunded) q, SUM(gross_cents) g, SUM(discount_cents) d, SUM(tax_cents) t FROM refund_line GROUP BY order_line_id) r ON r.order_line_id = ol.order_line_id
WHERE r.q = ol.quantity AND (r.g <> ol.gross_cents OR r.d <> ol.discount_cents OR r.t <> ol.tax_cents);

-- check: A09 | invariant | expect=zero | refund_line order_line must match its return_line; return request customer must match order customer
SELECT l.refund_line_id AS entity_id FROM refund_line l JOIN return_line rl ON rl.return_line_id = l.return_line_id WHERE rl.order_line_id <> l.order_line_id
UNION ALL
SELECT rq.return_request_id FROM return_request rq JOIN orders o ON o.order_id = rq.order_id WHERE o.customer_id <> rq.customer_id;

-- check: A10 | invariant | expect=zero | quantity chain: expected <= approved, shipped <= expected, received <= shipped, inspected = received, disposition qty = inspected
SELECT sl.shipment_line_id AS entity_id FROM shipment_line sl JOIN return_line rl ON rl.return_line_id = sl.return_line_id
WHERE sl.qty_expected > rl.qty_approved OR sl.qty_shipped > sl.qty_expected OR sl.qty_received > sl.qty_shipped
UNION ALL
SELECT i.inspection_id FROM inspection i JOIN shipment_line sl ON sl.return_line_id = i.return_line_id AND sl.shipment_id = i.shipment_id WHERE i.qty_inspected <> sl.qty_received
UNION ALL
SELECT d.disposition_id FROM inventory_disposition d JOIN inspection i ON i.inspection_id = d.inspection_id WHERE d.qty <> i.qty_inspected
UNION ALL
SELECT l.refund_line_id FROM refund_line l JOIN inspection i ON i.return_line_id = l.return_line_id WHERE l.qty_refunded > i.qty_inspected;

-- check: B01 | business | expect=gt:QTY_EXCEEDS_PURCHASED | approved return quantity exceeds purchased quantity
SELECT rl.return_line_id AS entity_id FROM return_line rl JOIN order_line ol ON ol.order_line_id = rl.order_line_id WHERE rl.qty_approved > ol.quantity;

-- check: B02 | business | expect=gt:REFUND_EXCEEDS_PAID | refund exceeds paid share of a line, or cumulative refunds exceed the amount paid for the order line
SELECT DISTINCT refund_id AS entity_id FROM refund_line WHERE refund_cents > paid_share_cents
UNION
SELECT DISTINCT l.refund_id FROM refund_line l JOIN (SELECT l2.order_line_id, SUM(l2.refund_cents) s FROM refund_line l2 GROUP BY l2.order_line_id) t ON t.order_line_id = l.order_line_id
JOIN order_line ol ON ol.order_line_id = l.order_line_id WHERE t.s > ol.paid_cents;

-- check: B03 | business | expect=gt:RESTOCK_BEFORE_INSPECTION | sellable restock posted before the inspection of that line
SELECT d.disposition_id AS entity_id FROM inventory_movement m JOIN inventory_disposition d ON d.disposition_id = m.disposition_id
JOIN inspection i ON i.inspection_id = d.inspection_id WHERE m.movement_type = 'RETURN_RESTOCK' AND m.posted_at < i.inspected_at;

-- check: B04 | business | expect=gt:LATE_NO_OVERRIDE | approved after the policy window (version in force at delivery) with no override
SELECT rl.return_line_id AS entity_id FROM return_line rl
JOIN return_request rq ON rq.return_request_id = rl.return_request_id JOIN orders o ON o.order_id = rq.order_id
JOIN order_line ol ON ol.order_line_id = rl.order_line_id
JOIN return_policy pp ON pp.category = ol.category AND o.delivery_date >= pp.effective_from AND (pp.effective_to IS NULL OR o.delivery_date <= pp.effective_to)
WHERE rl.qty_approved > 0 AND rl.override_code IS NULL AND pp.final_sale = 0
  AND julianday(rq.requested_at) - julianday(o.delivery_date) >
      pp.window_days + CASE WHEN rl.reason_code IN ('NOT_AS_DESCRIBED','DEFECTIVE','DAMAGED_IN_TRANSIT','WRONG_ITEM') THEN pp.defect_extension_days ELSE 0 END;

-- check: B05 | business | expect=gt:DUPLICATE_REFUND | second ISSUED payout for the same idempotency key
SELECT r.refund_id AS entity_id FROM refund r
WHERE r.status = 'ISSUED' AND EXISTS (SELECT 1 FROM refund p WHERE p.idempotency_key = r.idempotency_key AND p.status = 'ISSUED' AND p.attempt_no < r.attempt_no);

-- check: B06 | invariant | expect=zero | override approvals must satisfy the goodwill rule (GOLD <= 21 days late, SILVER <= 10) and carry a code
SELECT rl.return_line_id AS entity_id FROM return_line rl
JOIN return_request rq ON rq.return_request_id = rl.return_request_id JOIN orders o ON o.order_id = rq.order_id
JOIN customer c ON c.customer_id = rq.customer_id JOIN order_line ol ON ol.order_line_id = rl.order_line_id
JOIN return_policy pp ON pp.category = ol.category AND o.delivery_date >= pp.effective_from AND (pp.effective_to IS NULL OR o.delivery_date <= pp.effective_to)
WHERE rl.line_decision = 'APPROVED_OVERRIDE' AND NOT (
  (c.loyalty_tier = 'GOLD' AND rl.override_code = 'GOODWILL_GOLD' AND julianday(rq.requested_at) - julianday(o.delivery_date) - pp.window_days - CASE WHEN rl.reason_code IN ('NOT_AS_DESCRIBED','DEFECTIVE','DAMAGED_IN_TRANSIT','WRONG_ITEM') THEN pp.defect_extension_days ELSE 0 END <= 21)
  OR (c.loyalty_tier = 'SILVER' AND rl.override_code = 'GOODWILL_SILVER' AND julianday(rq.requested_at) - julianday(o.delivery_date) - pp.window_days - CASE WHEN rl.reason_code IN ('NOT_AS_DESCRIBED','DEFECTIVE','DAMAGED_IN_TRANSIT','WRONG_ITEM') THEN pp.defect_extension_days ELSE 0 END <= 10))
UNION ALL
SELECT return_line_id FROM return_line WHERE (override_code IS NOT NULL) <> (line_decision = 'APPROVED_OVERRIDE');

-- check: B07 | invariant | expect=zero | approved quantity in a final-sale category, or opened beauty without seller fault
SELECT rl.return_line_id AS entity_id FROM return_line rl
JOIN return_request rq ON rq.return_request_id = rl.return_request_id JOIN orders o ON o.order_id = rq.order_id JOIN order_line ol ON ol.order_line_id = rl.order_line_id
JOIN return_policy pp ON pp.category = ol.category AND o.delivery_date >= pp.effective_from AND (pp.effective_to IS NULL OR o.delivery_date <= pp.effective_to)
WHERE rl.qty_approved > 0 AND (pp.final_sale = 1 OR (pp.requires_unopened = 1 AND rl.condition_declared <> 'UNOPENED'
      AND rl.reason_code NOT IN ('NOT_AS_DESCRIBED','DEFECTIVE','DAMAGED_IN_TRANSIT','WRONG_ITEM')));

-- check: B08 | invariant | expect=zero | decision fields inconsistent (REJECTED needs qty 0; APPROVED needs qty>=1 and reason; authorization iff approved line)
SELECT return_line_id AS entity_id FROM return_line
WHERE (line_decision = 'REJECTED' AND (qty_approved <> 0 OR decision_reason IS NULL OR decision_reason IN ('ELIGIBLE','LATE_OVERRIDE')))
   OR (line_decision IN ('APPROVED','APPROVED_OVERRIDE') AND (qty_approved IS NULL OR qty_approved < 1))
   OR (line_decision = 'PENDING' AND (qty_approved IS NOT NULL OR decision_reason IS NOT NULL))
UNION ALL
SELECT rq.return_request_id FROM return_request rq
WHERE (EXISTS (SELECT 1 FROM return_line rl WHERE rl.return_request_id = rq.return_request_id AND rl.qty_approved > 0)) <>
      (EXISTS (SELECT 1 FROM return_authorization a WHERE a.return_request_id = rq.return_request_id))
UNION ALL
SELECT a.authorization_id FROM return_authorization a
WHERE (a.decision = 'APPROVED') <> (NOT EXISTS (SELECT 1 FROM return_line rl WHERE rl.return_request_id = a.return_request_id AND (rl.qty_approved IS NULL OR rl.qty_approved = 0)));

-- check: B09 | invariant | expect=zero | grade/fault/eligibility/disposition must follow inspection rules
SELECT i.inspection_id AS entity_id FROM inspection i JOIN return_line rl ON rl.return_line_id = i.return_line_id JOIN order_line ol ON ol.order_line_id = rl.order_line_id
WHERE i.grade <> CASE i.condition_found WHEN 'SEALED' THEN 'A' WHEN 'LIKE_NEW' THEN CASE WHEN ol.category = 'BEAUTY' THEN 'D' ELSE 'A' END
        WHEN 'USED' THEN CASE WHEN ol.category = 'BEAUTY' THEN 'D' ELSE 'B' END WHEN 'DAMAGED_MINOR' THEN 'C' WHEN 'DEFECTIVE' THEN 'C'
        WHEN 'DAMAGED_SEVERE' THEN 'D' WHEN 'NOT_ORIGINAL_ITEM' THEN 'W' WHEN 'SUSPECT_FRAUD' THEN 'S' END
   OR i.fault_party <> CASE WHEN (rl.reason_code = 'DEFECTIVE' AND i.condition_found = 'DEFECTIVE')
        OR (rl.reason_code = 'DAMAGED_IN_TRANSIT' AND i.condition_found IN ('DAMAGED_MINOR','DAMAGED_SEVERE'))
        OR (rl.reason_code IN ('WRONG_ITEM','NOT_AS_DESCRIBED') AND i.condition_found IN ('SEALED','LIKE_NEW','USED','DEFECTIVE','DAMAGED_MINOR')) THEN 'SELLER' ELSE 'CUSTOMER' END
   OR i.refund_eligible <> CASE WHEN i.fault_party = 'SELLER' OR i.grade IN ('A','B','C') THEN 1 ELSE 0 END;

-- check: B10 | invariant | expect=zero | disposition must follow grade (A restock, B refurbish, C refurbish if cost>=1500 else scrap, D scrap, W/S quarantine); location follows disposition
SELECT d.disposition_id AS entity_id FROM inventory_disposition d JOIN inspection i ON i.inspection_id = d.inspection_id JOIN product p ON p.product_id = d.product_id
WHERE d.disposition <> CASE i.grade WHEN 'A' THEN 'RESTOCK' WHEN 'B' THEN 'REFURBISH' WHEN 'C' THEN CASE WHEN p.unit_cost_cents >= 1500 THEN 'REFURBISH' ELSE 'SCRAP' END WHEN 'D' THEN 'SCRAP' ELSE 'QUARANTINE' END
   OR d.destination_location <> CASE d.disposition WHEN 'RESTOCK' THEN 'SELLABLE' WHEN 'REFURBISH' THEN 'REFURB' WHEN 'QUARANTINE' THEN 'QUARANTINE' ELSE 'SCRAP' END;

-- check: B11 | invariant | expect=zero | inventory movement must be controlled by its disposition (type, location, qty, sellable delta)
SELECT m.movement_id AS entity_id FROM inventory_movement m JOIN inventory_disposition d ON d.disposition_id = m.disposition_id
WHERE m.movement_type <> CASE d.disposition WHEN 'RESTOCK' THEN 'RETURN_RESTOCK' WHEN 'REFURBISH' THEN 'REFURB_INTAKE' WHEN 'QUARANTINE' THEN 'QUARANTINE_HOLD' ELSE 'SCRAP_WRITEOFF' END
   OR m.location <> d.destination_location OR m.qty <> d.qty OR m.sellable_qty_delta <> CASE WHEN d.disposition = 'RESTOCK' THEN d.qty ELSE 0 END
UNION ALL
SELECT m.movement_id FROM inventory_movement m
WHERE (m.disposition_id IS NULL AND (m.movement_type <> 'EXCHANGE_OUTBOUND' OR m.sellable_qty_delta >= 0))
   OR (m.disposition_id IS NOT NULL AND m.movement_type = 'EXCHANGE_OUTBOUND');

-- check: B12 | invariant | expect=zero | refund only after inspection, only for eligible lines, never for exchange requests
SELECT DISTINCT l.refund_id AS entity_id FROM refund_line l LEFT JOIN inspection i ON i.return_line_id = l.return_line_id WHERE i.inspection_id IS NULL OR i.refund_eligible = 0
UNION ALL
SELECT r.refund_id FROM refund r JOIN return_request rq ON rq.return_request_id = r.return_request_id WHERE rq.resolution_requested = 'EXCHANGE' OR rq.refund_method IS NULL OR rq.refund_method <> r.method;

-- check: B13 | invariant | expect=zero | return shipping fee rule (799 flat, waived for GOLD or any seller-fault line, capped at merchandise total)
SELECT r.refund_id AS entity_id FROM refund r JOIN return_request rq ON rq.return_request_id = r.return_request_id JOIN customer c ON c.customer_id = rq.customer_id
JOIN (SELECT l.refund_id, SUM(l.refund_cents) s, MAX(i.fault_party = 'SELLER') seller FROM refund_line l JOIN inspection i ON i.return_line_id = l.return_line_id GROUP BY l.refund_id) t ON t.refund_id = r.refund_id
WHERE r.attempt_no = 1 AND r.return_shipping_fee_cents <> CASE WHEN t.seller = 1 OR c.loyalty_tier = 'GOLD' THEN 0 ELSE MIN(799, t.s) END;

-- check: L01 | invariant | expect=zero | state transition not allowed by the lifecycle
WITH allowed(et, f, t) AS (VALUES
 ('RETURN_REQUEST',NULL,'SUBMITTED'),('RETURN_REQUEST','SUBMITTED','REJECTED'),('RETURN_REQUEST','SUBMITTED','AUTHORIZED'),
 ('RETURN_REQUEST','AUTHORIZED','SHIPPED'),('RETURN_REQUEST','AUTHORIZED','EXPIRED'),('RETURN_REQUEST','SHIPPED','RECEIVED'),
 ('RETURN_REQUEST','SHIPPED','CLAIM_OPENED'),('RETURN_REQUEST','RECEIVED','INSPECTED'),('RETURN_REQUEST','INSPECTED','REFUNDED'),
 ('RETURN_REQUEST','INSPECTED','CLOSED'),('RETURN_REQUEST','REFUNDED','CLOSED'),('RETURN_REQUEST','CLAIM_OPENED','CLOSED'),
 ('RETURN_SHIPMENT',NULL,'LABEL_ISSUED'),('RETURN_SHIPMENT','LABEL_ISSUED','IN_TRANSIT'),('RETURN_SHIPMENT','LABEL_ISSUED','VOIDED'),
 ('RETURN_SHIPMENT','IN_TRANSIT','RECEIVED'),('RETURN_SHIPMENT','IN_TRANSIT','LOST'),
 ('REFUND',NULL,'INITIATED'),('REFUND','INITIATED','ISSUED'),('REFUND','INITIATED','BLOCKED_DUPLICATE'))
SELECT e.event_id AS entity_id FROM state_event e
LEFT JOIN allowed a ON a.et = e.entity_type AND a.t = e.to_state AND a.f IS e.from_state
WHERE a.et IS NULL;

-- check: L02 | invariant | expect=zero | from_state must equal the previous to_state of the same entity (history is continuous and ordered)
SELECT event_id AS entity_id FROM (
  SELECT event_id, from_state, LAG(to_state) OVER (PARTITION BY entity_type, entity_id ORDER BY event_ts, event_id) AS prev FROM state_event)
WHERE from_state IS NOT prev;

-- check: L03 | invariant | expect=zero | current status column must equal the last event
WITH last AS (SELECT entity_type, entity_id, to_state, ROW_NUMBER() OVER (PARTITION BY entity_type, entity_id ORDER BY event_ts DESC, event_id DESC) rn FROM state_event)
SELECT r.return_request_id AS entity_id FROM return_request r LEFT JOIN last l ON l.entity_type = 'RETURN_REQUEST' AND l.entity_id = r.return_request_id AND l.rn = 1 WHERE l.to_state IS NOT r.status
UNION ALL
SELECT s.shipment_id FROM return_shipment s LEFT JOIN last l ON l.entity_type = 'RETURN_SHIPMENT' AND l.entity_id = s.shipment_id AND l.rn = 1 WHERE l.to_state IS NOT s.status
UNION ALL
SELECT f.refund_id FROM refund f LEFT JOIN last l ON l.entity_type = 'REFUND' AND l.entity_id = f.refund_id AND l.rn = 1 WHERE l.to_state IS NOT f.status;

-- check: L04 | invariant | expect=zero | event points to a missing parent, or an entity has no initial event
SELECT e.event_id AS entity_id FROM state_event e
WHERE (e.entity_type = 'RETURN_REQUEST' AND e.entity_id NOT IN (SELECT return_request_id FROM return_request))
   OR (e.entity_type = 'RETURN_SHIPMENT' AND e.entity_id NOT IN (SELECT shipment_id FROM return_shipment))
   OR (e.entity_type = 'REFUND' AND e.entity_id NOT IN (SELECT refund_id FROM refund))
UNION ALL
SELECT return_request_id FROM return_request WHERE return_request_id NOT IN (SELECT entity_id FROM state_event WHERE entity_type = 'RETURN_REQUEST' AND from_state IS NULL)
UNION ALL
SELECT shipment_id FROM return_shipment WHERE shipment_id NOT IN (SELECT entity_id FROM state_event WHERE entity_type = 'RETURN_SHIPMENT' AND from_state IS NULL)
UNION ALL
SELECT refund_id FROM refund WHERE refund_id NOT IN (SELECT entity_id FROM state_event WHERE entity_type = 'REFUND' AND from_state IS NULL);

-- check: L05 | invariant | expect=zero | lifecycle vs facts: AUTHORIZED+ needs an authorization; RECEIVED+ needs received parcels; INSPECTED+ needs inspections; REFUNDED needs an ISSUED refund
SELECT rq.return_request_id AS entity_id FROM return_request rq
WHERE (rq.status IN ('AUTHORIZED','SHIPPED','RECEIVED','INSPECTED','REFUNDED','EXPIRED','CLAIM_OPENED') AND NOT EXISTS (SELECT 1 FROM return_authorization a WHERE a.return_request_id = rq.return_request_id))
   OR (rq.status IN ('INSPECTED','REFUNDED') AND NOT EXISTS (SELECT 1 FROM return_line rl JOIN inspection i ON i.return_line_id = rl.return_line_id WHERE rl.return_request_id = rq.return_request_id))
   OR (rq.status = 'REFUNDED' AND NOT EXISTS (SELECT 1 FROM refund r WHERE r.return_request_id = rq.return_request_id AND r.status = 'ISSUED'))
   OR (rq.status = 'REJECTED' AND EXISTS (SELECT 1 FROM return_authorization a WHERE a.return_request_id = rq.return_request_id));

-- check: U01 | invariant | expect=zero | one return request per (order line, request) and one authorization / inspection per owner
SELECT return_request_id || '|' || order_line_id AS entity_id FROM return_line GROUP BY return_request_id, order_line_id HAVING COUNT(*) > 1
UNION ALL
SELECT return_request_id FROM return_authorization GROUP BY return_request_id HAVING COUNT(*) > 1
UNION ALL
SELECT return_line_id FROM inspection GROUP BY return_line_id HAVING COUNT(*) > 1
UNION ALL
SELECT inspection_id FROM inventory_disposition GROUP BY inspection_id HAVING COUNT(*) > 1;

-- check: P01 | invariant | expect=zero | policy versions of one category must not overlap
SELECT a.policy_id AS entity_id FROM return_policy a JOIN return_policy b ON a.category = b.category AND a.policy_id < b.policy_id
AND a.effective_from <= COALESCE(b.effective_to, '9999-12-31') AND b.effective_from <= COALESCE(a.effective_to, '9999-12-31');
