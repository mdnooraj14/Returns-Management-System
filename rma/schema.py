"""Single source of truth for the data model. Generates sql/schema.sql and docs/data_dictionary.md."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config as C
from .ids import PATTERNS

SQL_TYPE = {"id": "TEXT", "str": "TEXT", "date": "TEXT", "ts": "TEXT", "enum": "TEXT",
            "int": "INTEGER", "cents": "INTEGER", "bool": "INTEGER"}


@dataclass
class Col:
    name: str
    type: str  # id|str|date|ts|enum|int|cents|bool
    required: bool = True
    allowed: tuple | None = None
    units: str = ""
    unique: bool = False
    rule: str = ""
    fk: str | None = None  # "table.column"
    minv: int | None = None


@dataclass
class Table:
    name: str
    pk: str
    desc: str
    cols: list[Col]
    cardinality: str = ""
    lifecycle: str = ""
    uniques: list[tuple] = field(default_factory=list)

    @property
    def colnames(self) -> list[str]:
        return [c.name for c in self.cols]


def E(*v): return tuple(v)


def _c(name, type_, required=True, allowed=None, units="", unique=False, rule="", fk=None, minv=None):
    return Col(name, type_, required, allowed, units, unique, rule, fk, minv)


STATES = tuple(C.STATE_TAX_BPS)
TABLES: list[Table] = [
    Table("customer", "customer_id", "Customer master data.", [
        _c("customer_id", "id", unique=True, rule=PATTERNS["customer_id"]),
        _c("first_name", "str"), _c("last_name", "str"),
        _c("email", "str", unique=True, rule="synthetic address on example.com"),
        _c("state", "enum", allowed=STATES, rule="US state used for tax"),
        _c("loyalty_tier", "enum", allowed=E(*C.LOYALTY_TIERS), rule="drives goodwill override eligibility"),
        _c("created_date", "date", rule="ISO date; <= first order_date of the customer"),
    ], "Customer 1:N Order"),
    Table("product", "product_id", "Product/SKU master.", [
        _c("product_id", "id", unique=True, rule=PATTERNS["product_id"]),
        _c("name", "str"),
        _c("category", "enum", allowed=E(*C.CATEGORIES)),
        _c("unit_price_cents", "cents", units="USD cents", minv=1, rule="list price > 0"),
        _c("unit_cost_cents", "cents", units="USD cents", minv=1, rule="< unit_price_cents; drives refurbish-vs-scrap"),
    ], "Product 1:N OrderLine"),
    Table("return_policy", "policy_id", "Versioned return policy per category (effective dated).", [
        _c("policy_id", "id", unique=True, rule=PATTERNS["policy_id"]),
        _c("category", "enum", allowed=E(*C.CATEGORIES)),
        _c("window_days", "int", units="days", minv=0, rule="counted from delivery_date, inclusive"),
        _c("defect_extension_days", "int", units="days", minv=0, rule="added when reason is seller-fault"),
        _c("final_sale", "bool", rule="1 = category excluded from returns"),
        _c("requires_unopened", "bool", rule="1 = opened items rejected unless seller-fault"),
        _c("restocking_fee_bps_opened", "int", units="basis points", minv=0, rule="fee on paid share when item not SEALED"),
        _c("effective_from", "date"),
        _c("effective_to", "date", required=False, rule="NULL = open ended; versions of one category must not overlap"),
    ], "Category 1:N policy versions; version applies by delivery_date", uniques=[("category", "effective_from")]),
    Table("orders", "order_id", "Customer order header; totals are derived from lines.", [
        _c("order_id", "id", unique=True, rule=PATTERNS["order_id"]),
        _c("customer_id", "id", fk="customer.customer_id"),
        _c("order_date", "date", rule="2026-01-01..2026-09-30"),
        _c("status", "enum", allowed=E("DELIVERED", "CANCELLED")),
        _c("delivery_date", "date", required=False, rule="NULL iff CANCELLED; >= order_date"),
        _c("ship_state", "enum", allowed=STATES),
        _c("payment_method", "enum", allowed=E(*C.PAYMENT_METHODS)),
        _c("coupon_code", "enum", required=False, allowed=E("SAVE5", "SAVE10", "SAVE15", "SAVE20")),
        _c("subtotal_cents", "cents", units="USD cents", rule="= SUM(line gross)"),
        _c("discount_cents", "cents", units="USD cents", rule="= SUM(line discount)"),
        _c("shipping_cents", "cents", units="USD cents", rule="0 if subtotal-discount >= 7500 else 599"),
        _c("tax_cents", "cents", units="USD cents", rule="= SUM(line tax)"),
        _c("total_cents", "cents", units="USD cents", rule="= subtotal - discount + shipping + tax"),
    ], "Order 1:N OrderLine; Order 0..N ReturnRequest", lifecycle="DELIVERED | CANCELLED"),
    Table("order_line", "order_line_id", "Purchased line; per-line discount/tax allocation used for refund math.", [
        _c("order_line_id", "id", unique=True, rule=PATTERNS["order_line_id"]),
        _c("order_id", "id", fk="orders.order_id"),
        _c("line_no", "int", minv=1),
        _c("product_id", "id", fk="product.product_id"),
        _c("category", "enum", allowed=E(*C.CATEGORIES), rule="category snapshot at purchase"),
        _c("quantity", "int", units="units", minv=1),
        _c("unit_price_cents", "cents", units="USD cents"),
        _c("gross_cents", "cents", units="USD cents", rule="= quantity * unit_price"),
        _c("discount_cents", "cents", units="USD cents", rule="order discount allocated by largest remainder over gross"),
        _c("net_cents", "cents", units="USD cents", rule="= gross - discount"),
        _c("tax_rate_bps", "int", units="basis points", minv=0),
        _c("tax_cents", "cents", units="USD cents", rule="= round_half_up(net * bps / 10000); 0 for exempt categories"),
        _c("paid_cents", "cents", units="USD cents", rule="= net + tax (shipping excluded)"),
    ], "OrderLine 0..N ReturnLine", uniques=[("order_id", "line_no")]),
    Table("return_request", "return_request_id", "Customer return request (RMA header).", [
        _c("return_request_id", "id", unique=True, rule=PATTERNS["return_request_id"]),
        _c("order_id", "id", fk="orders.order_id"),
        _c("customer_id", "id", fk="customer.customer_id", rule="must equal orders.customer_id"),
        _c("requested_at", "date", rule=">= order delivery_date; <= snapshot 2026-10-22"),
        _c("channel", "enum", allowed=E(*C.CHANNELS)),
        _c("resolution_requested", "enum", allowed=E("REFUND", "EXCHANGE")),
        _c("refund_method", "enum", required=False, allowed=E(*C.REFUND_METHODS), rule="NULL for EXCHANGE"),
        _c("status", "enum", allowed=E(*C.REQUEST_STATES), rule="derived: equals last state_event.to_state"),
    ], "Request 1:N ReturnLine; Request 0..1 ReturnAuthorization", lifecycle="SUBMITTED>(REJECTED|AUTHORIZED>(EXPIRED|SHIPPED>(CLAIM_OPENED>CLOSED|RECEIVED>INSPECTED>(REFUNDED>)?CLOSED))"),
    Table("return_line", "return_line_id", "Requested quantity of one order line plus the eligibility decision.", [
        _c("return_line_id", "id", unique=True, rule=PATTERNS["return_line_id"]),
        _c("return_request_id", "id", fk="return_request.return_request_id"),
        _c("line_no", "int", minv=1),
        _c("order_line_id", "id", fk="order_line.order_line_id"),
        _c("qty_requested", "int", units="units", minv=1, rule="sum over requests <= purchased quantity (baseline)"),
        _c("reason_code", "enum", allowed=E(*C.REASONS)),
        _c("condition_declared", "enum", allowed=E(*C.DECLARED_CONDITIONS)),
        _c("line_decision", "enum", allowed=E(*C.LINE_DECISIONS), rule="PENDING iff decided_at NULL"),
        _c("decision_reason", "enum", required=False, allowed=E(*C.DECISION_REASONS)),
        _c("qty_approved", "int", required=False, units="units", minv=0, rule="<= purchased minus previously approved"),
        _c("override_code", "enum", required=False, allowed=E(*C.OVERRIDE_CODES), rule="required when approved after window"),
        _c("override_approved_by", "str", required=False, rule="MGR-nn when override_code set"),
        _c("decided_at", "date", required=False),
    ], "ReturnLine 0..1 Inspection; N:M ReturnLine<->ReturnShipment via shipment_line; N:M ReturnLine<->Refund via refund_line",
        uniques=[("return_request_id", "line_no"), ("return_request_id", "order_line_id")]),
    Table("return_authorization", "authorization_id", "Authorization issued when >=1 line is approved (effective decided_at..expires_at).", [
        _c("authorization_id", "id", unique=True, rule=PATTERNS["authorization_id"]),
        _c("return_request_id", "id", unique=True, fk="return_request.return_request_id"),
        _c("decision", "enum", allowed=E("APPROVED", "PARTIALLY_APPROVED")),
        _c("decided_at", "date"),
        _c("expires_at", "date", rule="= decided_at + 21 days"),
        _c("authorized_by", "str", rule="SYSTEM or MGR-nn (override)"),
    ], "Request 1:0..1 Authorization; Authorization 1:N ReturnShipment"),
    Table("return_shipment", "shipment_id", "Return parcel / label.", [
        _c("shipment_id", "id", unique=True, rule=PATTERNS["shipment_id"]),
        _c("authorization_id", "id", fk="return_authorization.authorization_id"),
        _c("carrier", "enum", allowed=E(*C.CARRIERS)),
        _c("tracking_number", "str", unique=True),
        _c("label_issued_at", "date", rule=">= authorization.decided_at"),
        _c("shipped_at", "date", required=False, rule=">= label_issued_at"),
        _c("received_at", "date", required=False, rule=">= shipped_at"),
        _c("status", "enum", allowed=E(*C.SHIPMENT_STATES), rule="derived: last state_event.to_state"),
    ], "Shipment 1:N ShipmentLine", lifecycle="LABEL_ISSUED>(VOIDED|IN_TRANSIT>(RECEIVED|LOST))"),
    Table("shipment_line", "shipment_line_id", "Bridge ReturnShipment <-> ReturnLine (N:M).", [
        _c("shipment_line_id", "id", unique=True, rule=PATTERNS["shipment_line_id"]),
        _c("shipment_id", "id", fk="return_shipment.shipment_id"),
        _c("return_line_id", "id", fk="return_line.return_line_id"),
        _c("qty_expected", "int", units="units", minv=1, rule="<= qty_approved of the line"),
        _c("qty_shipped", "int", required=False, units="units", minv=0, rule="<= qty_expected"),
        _c("qty_received", "int", required=False, units="units", minv=0, rule="<= qty_shipped"),
    ], "", uniques=[("shipment_id", "return_line_id")]),
    Table("inspection", "inspection_id", "Warehouse inspection of a returned line.", [
        _c("inspection_id", "id", unique=True, rule=PATTERNS["inspection_id"]),
        _c("return_line_id", "id", unique=True, fk="return_line.return_line_id"),
        _c("shipment_id", "id", fk="return_shipment.shipment_id"),
        _c("inspected_at", "date", rule=">= shipment.received_at"),
        _c("inspector_id", "str"),
        _c("qty_inspected", "int", units="units", minv=1, rule="= shipment_line.qty_received"),
        _c("condition_found", "enum", allowed=E(*C.CONDITIONS_FOUND)),
        _c("grade", "enum", allowed=E(*C.GRADES), rule="derived from condition_found + category"),
        _c("fault_party", "enum", allowed=E("SELLER", "CUSTOMER"), rule="SELLER iff reason claim consistent with condition_found"),
        _c("refund_eligible", "bool"),
    ], "ReturnLine 1:0..1 Inspection; Inspection 1:1 InventoryDisposition"),
    Table("inventory_disposition", "disposition_id", "Disposition decision for inspected goods.", [
        _c("disposition_id", "id", unique=True, rule=PATTERNS["disposition_id"]),
        _c("inspection_id", "id", unique=True, fk="inspection.inspection_id"),
        _c("return_line_id", "id", fk="return_line.return_line_id"),
        _c("product_id", "id", fk="product.product_id"),
        _c("disposition", "enum", allowed=E(*C.DISPOSITIONS), rule="A>RESTOCK B>REFURBISH C>REFURBISH if cost>=1500 else SCRAP D>SCRAP W,S>QUARANTINE"),
        _c("qty", "int", units="units", minv=1, rule="= qty_inspected"),
        _c("destination_location", "enum", allowed=E(*C.LOCATIONS)),
        _c("decided_at", "date", rule=">= inspected_at"),
        _c("est_recovery_cents", "cents", units="USD cents", rule="unit_price * qty * recovery factor"),
    ], "Disposition 1:0..1 InventoryMovement"),
    Table("inventory_movement", "movement_id", "Stock ledger entry caused by a disposition (or an exchange replacement).", [
        _c("movement_id", "id", unique=True, rule=PATTERNS["movement_id"]),
        _c("disposition_id", "id", required=False, fk="inventory_disposition.disposition_id", rule="NULL only for EXCHANGE_OUTBOUND"),
        _c("return_line_id", "id", fk="return_line.return_line_id"),
        _c("product_id", "id", fk="product.product_id"),
        _c("movement_type", "enum", allowed=E(*C.MOVEMENT_TYPES)),
        _c("location", "enum", allowed=E(*C.LOCATIONS)),
        _c("qty", "int", units="units", minv=1),
        _c("sellable_qty_delta", "int", units="units", rule=">0 only for RETURN_RESTOCK; <0 only for EXCHANGE_OUTBOUND"),
        _c("posted_at", "date", rule=">= inspection.inspected_at (restock never precedes inspection)"),
    ], ""),
    Table("refund", "refund_id", "Refund payout attempt (idempotent per request).", [
        _c("refund_id", "id", unique=True, rule=PATTERNS["refund_id"]),
        _c("return_request_id", "id", fk="return_request.return_request_id"),
        _c("idempotency_key", "str", rule="IDEM:<return_request_id>; one ISSUED payout per key"),
        _c("attempt_no", "int", minv=1),
        _c("method", "enum", allowed=E(*C.REFUND_METHODS)),
        _c("status", "enum", allowed=E("ISSUED", "BLOCKED_DUPLICATE"), rule="derived: last state_event.to_state"),
        _c("refund_date", "date", rule=">= every inspection of the request"),
        _c("refund_amount_cents", "cents", units="USD cents", rule="attempt 1: = SUM(refund_line.refund_cents) - shipping fee"),
        _c("paid_cents", "cents", units="USD cents", rule="= refund_amount for ISSUED, 0 for BLOCKED_DUPLICATE"),
        _c("return_shipping_fee_cents", "cents", units="USD cents", rule="799 flat for customer-fault, non-GOLD; capped at line total"),
        _c("currency", "enum", allowed=E("USD")),
    ], "Request 1:N Refund attempts; Refund N:M ReturnLine via refund_line", lifecycle="INITIATED>(ISSUED|BLOCKED_DUPLICATE)",
        uniques=[("return_request_id", "attempt_no")]),
    Table("refund_line", "refund_line_id", "Bridge Refund <-> ReturnLine with the refund math (attempt 1 only).", [
        _c("refund_line_id", "id", unique=True, rule=PATTERNS["refund_line_id"]),
        _c("refund_id", "id", fk="refund.refund_id"),
        _c("return_line_id", "id", fk="return_line.return_line_id"),
        _c("order_line_id", "id", fk="order_line.order_line_id"),
        _c("qty_refunded", "int", units="units", minv=1),
        _c("gross_cents", "cents", units="USD cents", rule="telescoping proration of order_line.gross"),
        _c("discount_cents", "cents", units="USD cents", rule="telescoping proration of order_line.discount"),
        _c("tax_cents", "cents", units="USD cents", rule="telescoping proration of order_line.tax"),
        _c("paid_share_cents", "cents", units="USD cents", rule="= gross - discount + tax"),
        _c("restocking_fee_cents", "cents", units="USD cents"),
        _c("condition_deduction_cents", "cents", units="USD cents"),
        _c("refund_cents", "cents", units="USD cents", rule="= paid_share - restocking_fee - condition_deduction"),
    ], "", uniques=[("refund_id", "return_line_id")]),
    Table("state_event", "event_id", "Append-only lifecycle history; state columns are derived from it.", [
        _c("event_id", "id", unique=True, rule=PATTERNS["event_id"]),
        _c("entity_type", "enum", allowed=E(*C.ENTITY_TYPES)),
        _c("entity_id", "id", rule="polymorphic reference; validated per entity_type by SQL"),
        _c("from_state", "str", required=False, rule="NULL on the initial event"),
        _c("to_state", "str"),
        _c("event_ts", "ts", rule="ISO-8601 seconds; <= snapshot date end"),
        _c("actor", "enum", allowed=E(*C.ACTORS)),
        _c("reason", "str", required=False),
    ], ""),
]
BY_NAME = {t.name: t for t in TABLES}


def _fmt(v):
    return "'" + str(v) + "'"


def sql_ddl() -> str:
    out = ["-- Generated from rma/schema.py. Structural constraints only; business rules are checked by sql/validation_checks.sql.",
           "PRAGMA foreign_keys = ON;", ""]
    for t in TABLES:
        lines = []
        for c in t.cols:
            s = f"  {c.name} {SQL_TYPE[c.type]}" + (" NOT NULL" if c.required else "")
            if c.name == t.pk:
                s += " PRIMARY KEY"
            elif c.unique:
                s += " UNIQUE"
            if c.allowed:
                s += f" CHECK ({c.name} IN ({', '.join(_fmt(a) for a in c.allowed)}))"
            if c.type == "bool":
                s += f" CHECK ({c.name} IN (0, 1))"
            if c.type == "cents":
                s += f" CHECK ({c.name} >= {c.minv if c.minv is not None else 0})"
            if c.type == "int" and c.minv is not None:
                s += f" CHECK ({c.name} >= {c.minv})"
            lines.append(s)
        for u in t.uniques:
            lines.append(f"  UNIQUE ({', '.join(u)})")
        for c in t.cols:
            if c.fk:
                tb, col = c.fk.split(".")
                lines.append(f"  FOREIGN KEY ({c.name}) REFERENCES {tb}({col})")
        out.append(f"CREATE TABLE {t.name} (\n" + ",\n".join(lines) + "\n);\n")
    return "\n".join(out)


def data_dictionary_md() -> str:
    o = ["# Data Dictionary", "", "Generated from `rma/schema.py` (single source of truth). Money is integer USD cents; dates are ISO `YYYY-MM-DD`; "
         "timestamps are ISO-8601. Every enum is enforced by a `CHECK` constraint and every FK by a `FOREIGN KEY`.", "",
         "## Relationship overview", "", "| Parent | Child | Cardinality | Optional? |", "|---|---|---|---|"]
    for t in TABLES:
        for c in t.cols:
            if c.fk:
                card = "1:1 (optional)" if c.unique else "1:N"
                o.append(f"| {c.fk.split('.')[0]} | {t.name} | {card} | {'child FK nullable' if not c.required else 'child FK required'} |")
    o += ["| return_shipment | return_line | N:M via shipment_line | – |", "| refund | return_line | N:M via refund_line | – |", ""]
    for t in TABLES:
        o += [f"## {t.name}", "", t.desc, "", f"- **Primary key:** `{t.pk}`"]
        if t.cardinality:
            o.append(f"- **Cardinality:** {t.cardinality}")
        if t.lifecycle:
            o.append(f"- **Lifecycle:** `{t.lifecycle}`")
        if t.uniques:
            o.append("- **Composite uniqueness:** " + "; ".join("(" + ", ".join(u) + ")" for u in t.uniques))
        o += ["", "| Field | Type | Req | Allowed values | Units | Unique | FK | Validation rule |", "|---|---|---|---|---|---|---|---|"]
        for c in t.cols:
            allowed = ", ".join(c.allowed) if c.allowed else ""
            rule = c.rule.replace("|", "\\|")
            uniq = "PK" if c.name == t.pk else ("yes" if c.unique else "")
            o.append(f"| {c.name} | {c.type} | {'Y' if c.required else 'N'} | {allowed} | {c.units} | {uniq} | {c.fk or ''} | {rule} |")
        o.append("")
    return "\n".join(o)


def write_docs(root) -> None:
    from pathlib import Path
    root = Path(root)
    (root / "sql").mkdir(exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    (root / "sql" / "schema.sql").write_text(sql_ddl(), encoding="utf-8", newline="\n")
    (root / "docs" / "data_dictionary.md").write_text(data_dictionary_md(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    from pathlib import Path
    write_docs(Path(__file__).resolve().parent.parent)
