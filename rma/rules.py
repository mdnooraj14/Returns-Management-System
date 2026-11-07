"""Business rules engine: pure functions, no randomness. Used by the generator to *derive* outcomes
and by the detector to replay decisions on stored data. The SQL validator is a separate implementation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import config as C


# ------------------------------------------------------------------ money helpers
def allocate(total: int, weights: list[int]) -> list[int]:
    """Largest-remainder allocation: parts are non-negative ints summing exactly to total."""
    w = sum(weights)
    if w == 0 or total == 0:
        return [0] * len(weights)
    base = [total * x // w for x in weights]
    order = sorted(range(len(weights)), key=lambda i: (-(total * weights[i] % w), i))
    for i in order[: total - sum(base)]:
        base[i] += 1
    return base


def prorate(total: int, qty_total: int, qty_prev: int, qty: int) -> int:
    """Telescoping round-half-up share of `total` for units (qty_prev, qty_prev+qty] of qty_total.
    Summed over successive returns of one line the shares equal `total` exactly when all units return."""
    h = qty_total // 2
    return (total * (qty_prev + qty) + h) // qty_total - (total * qty_prev + h) // qty_total


def bps_round(amount: int, bps: int) -> int:
    return (amount * bps + 5000) // 10000


# ------------------------------------------------------------------ eligibility
def policy_for(policies: list[dict], category: str, as_of: str) -> dict:
    for p in policies:
        if p["category"] == category and p["effective_from"] <= as_of and (p["effective_to"] is None or as_of <= p["effective_to"]):
            return p
    raise KeyError(f"no policy for {category} at {as_of}")


def allowed_days(policy: dict, reason: str) -> int:
    return policy["window_days"] + (policy["defect_extension_days"] if reason in C.SELLER_FAULT_REASONS else 0)


def late_override_code(tier: str, days_late: int) -> str | None:
    rule = C.OVERRIDE_RULES.get(tier)
    if rule and days_late <= rule[1]:
        return rule[0]
    return None


@dataclass(frozen=True)
class LineDecision:
    decision: str  # APPROVED | APPROVED_OVERRIDE | REJECTED
    reason: str
    qty_approved: int
    override_code: str | None
    days_since_delivery: int
    allowed_days: int


def evaluate_line(policy: dict, delivery_date: date, requested_at: date, reason: str, condition_declared: str,
                  qty_requested: int, qty_purchased: int, qty_prev_approved: int, tier: str) -> LineDecision:
    days = (requested_at - delivery_date).days
    allowed = allowed_days(policy, reason)

    def rej(r):
        return LineDecision("REJECTED", r, 0, None, days, allowed)

    if policy["final_sale"]:
        return rej("FINAL_SALE_CATEGORY")
    remaining = qty_purchased - qty_prev_approved
    if remaining <= 0:
        return rej("QTY_EXHAUSTED")
    if policy["requires_unopened"] and reason not in C.SELLER_FAULT_REASONS and condition_declared != "UNOPENED":
        return rej("OPENED_NOT_RETURNABLE")
    qty = min(qty_requested, remaining)
    if days > allowed:
        code = late_override_code(tier, days - allowed)
        if code is None:
            return rej("LATE_REQUEST")
        return LineDecision("APPROVED_OVERRIDE", "LATE_OVERRIDE", qty, code, days, allowed)
    return LineDecision("APPROVED", "ELIGIBLE", qty, None, days, allowed)


# ------------------------------------------------------------------ inspection / disposition
def grade_for(condition: str, category: str) -> str:
    if condition == "SEALED":
        return "A"
    if condition == "LIKE_NEW":
        return "D" if category == "BEAUTY" else "A"  # opened beauty is not resalable (hygiene)
    if condition == "USED":
        return "D" if category == "BEAUTY" else "B"
    return {"DAMAGED_MINOR": "C", "DEFECTIVE": "C", "DAMAGED_SEVERE": "D", "NOT_ORIGINAL_ITEM": "W", "SUSPECT_FRAUD": "S"}[condition]


def disposition_for(grade: str, unit_cost_cents: int) -> str:
    if grade == "A":
        return "RESTOCK"
    if grade == "B":
        return "REFURBISH"
    if grade == "C":
        return "REFURBISH" if unit_cost_cents >= C.REFURB_MIN_COST_CENTS else "SCRAP"
    if grade == "D":
        return "SCRAP"
    return "QUARANTINE"


CLAIM_CONSISTENT = {
    "DEFECTIVE": {"DEFECTIVE"},
    "DAMAGED_IN_TRANSIT": {"DAMAGED_MINOR", "DAMAGED_SEVERE"},
    "WRONG_ITEM": {"SEALED", "LIKE_NEW", "USED", "DEFECTIVE", "DAMAGED_MINOR"},
    "NOT_AS_DESCRIBED": {"SEALED", "LIKE_NEW", "USED", "DEFECTIVE", "DAMAGED_MINOR"},
}


def fault_party(reason: str, condition: str) -> str:
    return "SELLER" if condition in CLAIM_CONSISTENT.get(reason, ()) else "CUSTOMER"


def refund_eligible(fault: str, grade: str) -> bool:
    return fault == "SELLER" or grade in ("A", "B", "C")


# ------------------------------------------------------------------ refund math
def refund_line_amounts(order_line: dict, prev_qty: int, qty: int, grade: str, fault: str, condition: str, policy: dict) -> dict:
    Q = order_line["quantity"]
    gross = prorate(order_line["gross_cents"], Q, prev_qty, qty)
    disc = prorate(order_line["discount_cents"], Q, prev_qty, qty)
    tax = prorate(order_line["tax_cents"], Q, prev_qty, qty)
    paid = gross - disc + tax
    restock = deduct = 0
    if fault == "CUSTOMER":
        if policy["restocking_fee_bps_opened"] and condition != "SEALED":
            restock = min(paid, bps_round(paid, policy["restocking_fee_bps_opened"]))
        deduct = min(paid - restock, bps_round(paid, C.CONDITION_DEDUCTION_BPS.get(grade, 0)))
    return dict(qty_refunded=qty, gross_cents=gross, discount_cents=disc, tax_cents=tax, paid_share_cents=paid,
                restocking_fee_cents=restock, condition_deduction_cents=deduct, refund_cents=paid - restock - deduct)


def return_shipping_fee(faults: list[str], tier: str, merchandise_total: int) -> int:
    if not faults or "SELLER" in faults or tier == "GOLD":
        return 0
    return min(C.RETURN_SHIPPING_FEE_CENTS, merchandise_total)


class RefundLedger:
    """Idempotent payout control: at most one ISSUED payout per idempotency key."""

    def __init__(self):
        self.paid: dict[str, int] = {}

    def attempt(self, key: str, amount: int) -> tuple[str, int]:
        if key in self.paid:
            return "BLOCKED_DUPLICATE", 0
        self.paid[key] = amount
        return "ISSUED", amount


def idempotency_key(return_request_id: str) -> str:
    return f"IDEM:{return_request_id}"
