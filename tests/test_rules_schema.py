import re
import sqlite3
from datetime import date

import pytest

from rma import config as C
from rma import ids, rules, schema


POL = [dict(policy_id=f"POL-{r[0]}-V{r[1]}", category=r[0], window_days=r[2], defect_extension_days=r[3], final_sale=r[4],
            requires_unopened=r[5], restocking_fee_bps_opened=r[6], effective_from=r[7], effective_to=r[8]) for r in C.POLICY_ROWS]


def pol(cat, asof="2026-03-01"):
    return rules.policy_for(POL, cat, asof)


def ev(cat, days, reason="CHANGED_MIND", cond="UNOPENED", req=1, purchased=2, prev=0, tier="STANDARD", asof="2026-03-01"):
    d = date(2026, 3, 1)
    return rules.evaluate_line(pol(cat, asof), d, date.fromordinal(d.toordinal() + days), reason, cond, req, purchased, prev, tier)


def test_schema_sql_is_valid_and_has_fk_and_pk():
    con = sqlite3.connect(":memory:")
    con.executescript(schema.sql_ddl())
    assert len(schema.TABLES) == 16
    for t in schema.TABLES:
        assert t.pk in t.colnames
        for c in t.cols:
            if c.fk:
                tb, col = c.fk.split(".")
                assert col in schema.BY_NAME[tb].colnames


def test_id_formats():
    assert ids.order_id(1) == "ORD-2026-000001"
    assert ids.rma_id(1) == "RMA-2026-000001"
    assert ids.rma_line_id(ids.rma_id(1), 1) == "RMAL-RMA-2026-000001-01"
    assert ids.rts_id(7) == "RTS-2026-000007"
    assert ids.ref_id(12) == "REF-2026-000012"
    assert re.match(ids.PATTERNS["return_line_id"], "RMAL-RMA-2026-000001-01")


def test_allocate_and_prorate_reconcile():
    assert sum(rules.allocate(1001, [3000, 2000, 5000])) == 1001
    assert rules.allocate(0, [1, 2]) == [0, 0]
    assert rules.allocate(10, [0, 0]) == [0, 0]
    total, Q = 1999, 3
    parts = [rules.prorate(total, Q, 0, 1), rules.prorate(total, Q, 1, 1), rules.prorate(total, Q, 2, 1)]
    assert sum(parts) == total
    assert rules.prorate(total, Q, 0, 3) == total


def test_window_boundary_inclusive():
    assert ev("APPAREL", 30).decision == "APPROVED"
    d = ev("APPAREL", 31)
    assert (d.decision, d.reason) == ("REJECTED", "LATE_REQUEST")


def test_defect_extension_and_policy_version():
    assert ev("APPAREL", 45, reason="DEFECTIVE").decision == "APPROVED"
    assert ev("APPAREL", 46, reason="DEFECTIVE").decision == "REJECTED"
    assert pol("ELECTRONICS", "2026-03-01")["window_days"] == 15
    assert pol("ELECTRONICS", "2026-06-01")["window_days"] == 20


def test_final_sale_and_beauty_unopened():
    assert ev("GIFT_CARDS", 1).reason == "FINAL_SALE_CATEGORY"
    assert ev("CLEARANCE", 1).reason == "FINAL_SALE_CATEGORY"
    assert ev("BEAUTY", 3, cond="OPENED").reason == "OPENED_NOT_RETURNABLE"
    assert ev("BEAUTY", 3, reason="DEFECTIVE", cond="DEFECTIVE").decision == "APPROVED"


def test_override_rules():
    d = ev("APPAREL", 40, tier="GOLD")
    assert (d.decision, d.override_code) == ("APPROVED_OVERRIDE", "GOODWILL_GOLD")
    assert ev("APPAREL", 40, tier="SILVER").decision == "APPROVED_OVERRIDE"   # 10 late
    assert ev("APPAREL", 41, tier="SILVER").decision == "REJECTED"            # 11 late
    assert ev("APPAREL", 52, tier="GOLD").decision == "REJECTED"              # 22 late
    assert ev("APPAREL", 40, tier="STANDARD").reason == "LATE_REQUEST"


def test_quantity_cap():
    d = ev("HOME", 1, req=3, purchased=3, prev=2)
    assert d.qty_approved == 1
    assert ev("HOME", 1, req=1, purchased=3, prev=3).reason == "QTY_EXHAUSTED"


def test_grade_disposition_and_fault():
    assert rules.disposition_for(rules.grade_for("SEALED", "HOME"), 100) == "RESTOCK"
    assert rules.disposition_for(rules.grade_for("USED", "HOME"), 100) == "REFURBISH"
    assert rules.disposition_for("C", 1499) == "SCRAP" and rules.disposition_for("C", 1500) == "REFURBISH"
    assert rules.disposition_for(rules.grade_for("LIKE_NEW", "BEAUTY"), 100) == "SCRAP"
    assert rules.disposition_for("W", 100) == rules.disposition_for("S", 100) == "QUARANTINE"
    assert rules.fault_party("DEFECTIVE", "DEFECTIVE") == "SELLER"
    assert rules.fault_party("DEFECTIVE", "USED") == "CUSTOMER"
    assert not rules.refund_eligible("CUSTOMER", "D") and rules.refund_eligible("SELLER", "D")


def test_refund_math():
    ol = dict(quantity=2, gross_cents=20000, discount_cents=2000, tax_cents=1305)
    p = pol("ELECTRONICS")
    r = rules.refund_line_amounts(ol, 0, 2, "B", "CUSTOMER", "USED", p)
    assert r["paid_share_cents"] == 20000 - 2000 + 1305
    assert r["restocking_fee_cents"] == rules.bps_round(r["paid_share_cents"], 1000)
    assert r["refund_cents"] == r["paid_share_cents"] - r["restocking_fee_cents"] - r["condition_deduction_cents"]
    s = rules.refund_line_amounts(ol, 0, 2, "C", "SELLER", "DEFECTIVE", p)
    assert s["refund_cents"] == s["paid_share_cents"]
    assert rules.return_shipping_fee(["CUSTOMER"], "STANDARD", 5000) == 799
    assert rules.return_shipping_fee(["CUSTOMER"], "GOLD", 5000) == 0
    assert rules.return_shipping_fee(["CUSTOMER", "SELLER"], "STANDARD", 5000) == 0
    assert rules.return_shipping_fee(["CUSTOMER"], "STANDARD", 300) == 300


def test_duplicate_refund_blocked():
    led = rules.RefundLedger()
    assert led.attempt("IDEM:RMA-2026-000001", 500) == ("ISSUED", 500)
    assert led.attempt("IDEM:RMA-2026-000001", 500) == ("BLOCKED_DUPLICATE", 0)
    assert led.attempt("IDEM:RMA-2026-000002", 100)[0] == "ISSUED"
