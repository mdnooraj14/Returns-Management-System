# Entity Relationship Diagram

```mermaid
erDiagram
    customer ||--o{ orders : places
    orders ||--|{ order_line : contains
    product ||--o{ order_line : "sold as"
    return_policy }o--|| product : "applies by category + delivery date"
    orders ||--o{ return_request : "returned via"
    customer ||--o{ return_request : submits
    return_request ||--|{ return_line : has
    order_line ||--o{ return_line : "returned as"
    return_request ||--o| return_authorization : "authorized by"
    return_authorization ||--o{ return_shipment : "ships via"
    return_shipment ||--|{ shipment_line : carries
    return_line ||--o{ shipment_line : "shipped in"
    return_line ||--o| inspection : "inspected as"
    return_shipment ||--o{ inspection : "received in"
    inspection ||--|| inventory_disposition : "decides"
    inventory_disposition ||--o| inventory_movement : "posts"
    return_request ||--o{ refund : "paid by (attempts)"
    refund ||--|{ refund_line : "itemised in"
    return_line ||--o{ refund_line : "refunded as"
    state_event }o..o| return_request : "history of"
    state_event }o..o| return_shipment : "history of"
    state_event }o..o| refund : "history of"
```

## Lifecycles (recorded as append-only `state_event` rows)

| Entity | States |
|---|---|
| ReturnRequest | SUBMITTED → REJECTED \| AUTHORIZED → EXPIRED \| SHIPPED → CLAIM_OPENED → CLOSED \| RECEIVED → INSPECTED → (REFUNDED →) CLOSED |
| ReturnShipment | LABEL_ISSUED → VOIDED \| IN_TRANSIT → RECEIVED \| LOST |
| Refund | INITIATED → ISSUED \| BLOCKED_DUPLICATE |

## Effective dating
* `return_policy` versions are effective-dated; the version in force on the order's `delivery_date` governs eligibility
  (ELECTRONICS window 15 days until 2026-05-31, 20 days from 2026-06-01).
* `return_authorization` is effective `decided_at` .. `expires_at` (21 days).
* Snapshot date is fixed at 2026-10-22: no event exists after it, so some requests are legitimately still in flight.
