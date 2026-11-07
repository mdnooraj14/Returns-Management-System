"""Central configuration: volumes, calendar, policy, enums. All business constants live here."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

SEED = 20261022
YEAR = 2026
SNAPSHOT_DATE = date(2026, 10, 22)  # fixed "as-of" date; no event after this exists
ORDER_START = date(2026, 1, 1)
ORDER_END = date(2026, 9, 30)

BASE_VOLUMES = dict(orders=30000, requests=5000, lines=8000, customers=12000, products=600, anomalies_per_type=80)


@dataclass(frozen=True)
class Params:
    seed: int = SEED
    scale: float = 1.0

    @property
    def orders(self) -> int:
        return max(20, round(BASE_VOLUMES["orders"] * self.scale))

    @property
    def requests(self) -> int:
        return max(5, round(BASE_VOLUMES["requests"] * self.scale))

    @property
    def lines(self) -> int:
        return max(8, round(BASE_VOLUMES["lines"] * self.scale))

    @property
    def customers(self) -> int:
        return max(20, round(BASE_VOLUMES["customers"] * self.scale))

    @property
    def products(self) -> int:
        return BASE_VOLUMES["products"]

    @property
    def anomalies_per_type(self) -> int:
        return max(2, round(BASE_VOLUMES["anomalies_per_type"] * self.scale))


# ---------------------------------------------------------------- enums
CATEGORIES = ["APPAREL", "FOOTWEAR", "ELECTRONICS", "HOME", "BEAUTY", "CLEARANCE", "PERISHABLES", "GIFT_CARDS"]
CATEGORY_LINE_WEIGHT = [0.26, 0.10, 0.16, 0.20, 0.12, 0.06, 0.07, 0.03]
RETURN_PROPENSITY = {"APPAREL": 1.6, "FOOTWEAR": 1.5, "ELECTRONICS": 1.0, "HOME": 0.8, "BEAUTY": 0.6,
                     "CLEARANCE": 0.7, "PERISHABLES": 0.15, "GIFT_CARDS": 0.1}
# (median $, min $, max $) for lognormal price draw
PRICE_SHAPE = {"APPAREL": (45, 12, 220), "FOOTWEAR": (70, 25, 250), "ELECTRONICS": (120, 15, 1200),
               "HOME": (40, 8, 400), "BEAUTY": (22, 5, 120), "CLEARANCE": (18, 4, 90), "PERISHABLES": (14, 4, 60)}
GIFT_CARD_VALUES_CENTS = [2500, 5000, 10000]

STATE_TAX_BPS = {"CA": 725, "NY": 400, "TX": 625, "FL": 600, "WA": 650, "IL": 625, "PA": 600, "OR": 0, "NC": 475, "OH": 575}
STATE_WEIGHT = [0.20, 0.12, 0.13, 0.10, 0.07, 0.08, 0.07, 0.04, 0.09, 0.10]
TAX_EXEMPT_CATEGORIES = {"PERISHABLES", "GIFT_CARDS"}
DISCOUNT_EXCLUDED_CATEGORIES = {"GIFT_CARDS"}
COUPONS = [(None, 0), ("SAVE5", 5), ("SAVE10", 10), ("SAVE15", 15), ("SAVE20", 20)]
COUPON_WEIGHT = [0.55, 0.10, 0.20, 0.10, 0.05]
PAYMENT_METHODS = ["CARD", "PAYPAL", "APPLE_PAY"]
LOYALTY_TIERS = ["STANDARD", "SILVER", "GOLD"]
FREE_SHIPPING_THRESHOLD_CENTS = 7500
SHIPPING_FEE_CENTS = 599

REASONS = ["SIZE_FIT", "CHANGED_MIND", "NO_LONGER_NEEDED", "NOT_AS_DESCRIBED", "DEFECTIVE", "DAMAGED_IN_TRANSIT", "WRONG_ITEM"]
SELLER_FAULT_REASONS = {"NOT_AS_DESCRIBED", "DEFECTIVE", "DAMAGED_IN_TRANSIT", "WRONG_ITEM"}
DECLARED_CONDITIONS = ["UNOPENED", "OPENED", "DAMAGED", "DEFECTIVE"]
CHANNELS = ["WEB", "APP", "STORE", "CALL"]
CONDITIONS_FOUND = ["SEALED", "LIKE_NEW", "USED", "DAMAGED_MINOR", "DAMAGED_SEVERE", "DEFECTIVE", "NOT_ORIGINAL_ITEM", "SUSPECT_FRAUD"]
GRADES = ["A", "B", "C", "D", "W", "S"]
DISPOSITIONS = ["RESTOCK", "REFURBISH", "QUARANTINE", "SCRAP"]
LOCATIONS = ["SELLABLE", "REFURB", "QUARANTINE", "SCRAP"]
DISPOSITION_LOCATION = {"RESTOCK": "SELLABLE", "REFURBISH": "REFURB", "QUARANTINE": "QUARANTINE", "SCRAP": "SCRAP"}
MOVEMENT_TYPE = {"RESTOCK": "RETURN_RESTOCK", "REFURBISH": "REFURB_INTAKE", "QUARANTINE": "QUARANTINE_HOLD", "SCRAP": "SCRAP_WRITEOFF"}
MOVEMENT_TYPES = list(MOVEMENT_TYPE.values()) + ["EXCHANGE_OUTBOUND"]
RECOVERY_FACTOR_BPS = {"RESTOCK": 9000, "REFURBISH": 5500, "QUARANTINE": 0, "SCRAP": 300}
LINE_DECISIONS = ["PENDING", "APPROVED", "APPROVED_OVERRIDE", "REJECTED"]
DECISION_REASONS = ["ELIGIBLE", "LATE_OVERRIDE", "FINAL_SALE_CATEGORY", "LATE_REQUEST", "OPENED_NOT_RETURNABLE", "QTY_EXHAUSTED"]
OVERRIDE_CODES = ["GOODWILL_GOLD", "GOODWILL_SILVER"]
CARRIERS = ["UPS", "USPS", "FEDEX"]
SHIPMENT_STATES = ["LABEL_ISSUED", "IN_TRANSIT", "RECEIVED", "LOST", "VOIDED"]
REFUND_STATES = ["INITIATED", "ISSUED", "BLOCKED_DUPLICATE"]
REFUND_METHODS = ["ORIGINAL_PAYMENT", "STORE_CREDIT"]
REQUEST_STATES = ["SUBMITTED", "REJECTED", "AUTHORIZED", "SHIPPED", "RECEIVED", "INSPECTED", "REFUNDED", "CLOSED", "EXPIRED", "CLAIM_OPENED"]
ENTITY_TYPES = ["RETURN_REQUEST", "RETURN_SHIPMENT", "REFUND"]
ACTORS = ["SYSTEM", "CUSTOMER", "AGENT", "WAREHOUSE", "FINANCE", "CARRIER"]

# lifecycle: allowed (from, to) transitions per entity type; from=None is the initial state
TRANSITIONS = {
    "RETURN_REQUEST": {(None, "SUBMITTED"), ("SUBMITTED", "REJECTED"), ("SUBMITTED", "AUTHORIZED"),
                       ("AUTHORIZED", "SHIPPED"), ("AUTHORIZED", "EXPIRED"), ("SHIPPED", "RECEIVED"),
                       ("SHIPPED", "CLAIM_OPENED"), ("RECEIVED", "INSPECTED"), ("INSPECTED", "REFUNDED"),
                       ("INSPECTED", "CLOSED"), ("REFUNDED", "CLOSED"), ("CLAIM_OPENED", "CLOSED")},
    "RETURN_SHIPMENT": {(None, "LABEL_ISSUED"), ("LABEL_ISSUED", "IN_TRANSIT"), ("LABEL_ISSUED", "VOIDED"),
                        ("IN_TRANSIT", "RECEIVED"), ("IN_TRANSIT", "LOST")},
    "REFUND": {(None, "INITIATED"), ("INITIATED", "ISSUED"), ("INITIATED", "BLOCKED_DUPLICATE")},
}

# ---------------------------------------------------------------- policy
# (category, version, window_days, defect_extension_days, final_sale, requires_unopened, restock_bps_opened, from, to)
POLICY_ROWS = [
    ("APPAREL", 1, 30, 15, 0, 0, 0, "2026-01-01", None),
    ("FOOTWEAR", 1, 30, 15, 0, 0, 0, "2026-01-01", None),
    ("ELECTRONICS", 1, 15, 15, 0, 0, 1000, "2026-01-01", "2026-05-31"),
    ("ELECTRONICS", 2, 20, 15, 0, 0, 1000, "2026-06-01", None),
    ("HOME", 1, 30, 15, 0, 0, 0, "2026-01-01", None),
    ("BEAUTY", 1, 14, 15, 0, 1, 0, "2026-01-01", None),
    ("CLEARANCE", 1, 0, 0, 1, 0, 0, "2026-01-01", None),
    ("PERISHABLES", 1, 0, 0, 1, 0, 0, "2026-01-01", None),
    ("GIFT_CARDS", 1, 0, 0, 1, 0, 0, "2026-01-01", None),
]

AUTH_VALID_DAYS = 21
RETURN_SHIPPING_FEE_CENTS = 799
CONDITION_DEDUCTION_BPS = {"A": 0, "B": 1500, "C": 4000}  # grade D / W / S are refund-denied for customer fault
REFURB_MIN_COST_CENTS = 1500
OVERRIDE_RULES = {"GOLD": ("GOODWILL_GOLD", 21), "SILVER": ("GOODWILL_SILVER", 10)}  # tier -> (code, max days late)

# ---------------------------------------------------------------- anomaly labels
ISSUE_TYPES = ["QTY_EXCEEDS_PURCHASED", "REFUND_EXCEEDS_PAID", "RESTOCK_BEFORE_INSPECTION", "LATE_NO_OVERRIDE", "DUPLICATE_REFUND"]
