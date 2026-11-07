import re
from collections import defaultdict

import pytest

from rma import config as C
from rma import generate as G
from rma import ids, returns


@pytest.fixture(scope="module")
def base():
    return G.generate(C.Params(), inject=False)["tables"]


def test_exact_volumes(base):
    assert len(base["orders"]) == 30000 and len(base["return_request"]) == 5000 and len(base["return_line"]) == 8000


def test_line_count_plan():
    for n, l in [(5000, 8000), (100, 160), (500, 800)]:
        pl = returns.line_count_plan(n, l)
        assert sum(pl.values()) == n and sum(k * v for k, v in pl.items()) == l


def test_id_patterns(base):
    for t in base.values():
        for col in t.columns:
            if col in ids.PATTERNS:
                s = t[col].dropna()
                bad = s[~s.str.match(ids.PATTERNS[col])]
                assert bad.empty, (col, bad.head())


def test_lifecycle_transitions_and_status(base):
    ev = base["state_event"]
    by = defaultdict(list)
    for r in ev.itertuples():
        by[(r.entity_type, r.entity_id)].append(r)
    for (et, eid), rows in by.items():
        rows.sort(key=lambda r: r.event_ts)
        prev = None
        for r in rows:
            fs = None if r.from_state is None or r.from_state != r.from_state else r.from_state
            assert fs == prev, (eid, r)
            assert (fs, r.to_state) in C.TRANSITIONS[et], (eid, fs, r.to_state)
            prev = r.to_state
    st = {k: v[-1].to_state for k, v in by.items()}
    for r in base["return_request"].itertuples():
        assert st[("RETURN_REQUEST", r.return_request_id)] == r.status
    for r in base["refund"].itertuples():
        assert st[("REFUND", r.refund_id)] == r.status


def test_refund_reconciliation(base):
    rl, rf = base["refund_line"], base["refund"]
    assert (rl.paid_share_cents == rl.gross_cents - rl.discount_cents + rl.tax_cents).all()
    assert (rl.refund_cents == rl.paid_share_cents - rl.restocking_fee_cents - rl.condition_deduction_cents).all()
    s = rl.groupby("refund_id").refund_cents.sum()
    first = rf[rf.attempt_no == 1].set_index("refund_id")
    assert ((s - first.return_shipping_fee_cents) == first.refund_amount_cents).all()
    ol = base["order_line"].set_index("order_line_id")
    per = rl.groupby("order_line_id").agg(c=("refund_cents", "sum"), q=("qty_refunded", "sum"))
    j = per.join(ol[["paid_cents", "quantity"]])
    assert (j.c <= j.paid_cents).all() and (j.q <= j.quantity).all()
    full = j[j.q == j.quantity]  # fully returned lines refund at most the paid amount (equality absent deductions)
    assert (full.c <= full.paid_cents).all()


def test_duplicates_blocked(base):
    rf = base["refund"]
    issued = rf[rf.status == "ISSUED"].groupby("idempotency_key").size()
    assert issued.max() == 1
    blocked = rf[rf.status == "BLOCKED_DUPLICATE"]
    assert len(blocked) > 0 and (blocked.paid_cents == 0).all()


def test_disposition_controls_inventory(base):
    mv = base["inventory_movement"].merge(base["inventory_disposition"][["disposition_id", "disposition", "inspection_id"]], on="disposition_id", how="left")
    ins = base["inspection"].set_index("inspection_id").inspected_at
    m = mv[mv.disposition_id.notna()]
    assert ((m.sellable_qty_delta > 0) == (m.disposition == "RESTOCK")).all()
    assert (m.posted_at >= m.inspection_id.map(ins)).all()
    ex = mv[mv.movement_type == "EXCHANGE_OUTBOUND"]
    assert (ex.sellable_qty_delta < 0).all()


def test_no_event_after_snapshot_and_requests_not_future(base):
    assert base["state_event"].event_ts.max() <= "2026-10-22T23:59:59"
    assert base["return_request"].requested_at.max() <= "2026-10-22"


def test_policy_followed_on_decisions(base):
    rl = base["return_line"]
    late_app = rl[(rl.line_decision == "APPROVED_OVERRIDE")]
    assert late_app.override_code.notna().all()
    assert (rl[rl.decision_reason == "FINAL_SALE_CATEGORY"].qty_approved == 0).all()


def test_deterministic_small():
    a = G.generate(C.Params(scale=0.03), inject=False)["tables"]
    b = G.generate(C.Params(scale=0.03), inject=False)["tables"]
    for k in a:
        assert a[k].equals(b[k]), k
