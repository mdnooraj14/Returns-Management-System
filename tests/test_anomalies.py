from datetime import date

import pandas as pd
import pytest

from rma import config as C
from rma import generate as G
from rma import ids, rules
from rma.master import build_policies

P = C.Params()


@pytest.fixture(scope="module")
def gen():
    return G.generate(P)


def test_counts_per_type_and_required_types(gen):
    a = gen["ground_truth"]["anomalies"]
    assert set(a.issue_type) == set(C.ISSUE_TYPES)
    assert (a.groupby("issue_type").size() == P.anomalies_per_type).all()
    assert a.anomaly_id.is_unique and a.anomaly_id.iloc[0] == "GT-000001"


def test_volumes_unchanged_by_injection(gen):
    t = gen["tables"]
    assert len(t["orders"]) == 30000 and len(t["return_request"]) == 5000 and len(t["return_line"]) == 8000


def test_no_label_leakage_into_inputs(gen):
    banned = {"issue_type", "ground_truth", "is_anomaly", "anomaly", "label", "expected_decision"}
    for name, df in gen["tables"].items():
        assert not banned & set(df.columns), name
    txt = " ".join(gen["tables"]["state_event"].reason.dropna().unique())
    assert "DUPLICATE_REFUND" not in txt and "LATE_NO_OVERRIDE" not in txt


def test_each_anomaly_truly_violates_rule(gen):
    t, a = gen["tables"], gen["ground_truth"]["anomalies"]
    ol = t["order_line"].set_index("order_line_id")
    rl = t["return_line"].set_index("return_line_id")
    ids_ = lambda k: set(a[a.issue_type == k].entity_id)

    q = rl.loc[sorted(ids_("QTY_EXCEEDS_PURCHASED"))]
    assert (q.qty_approved > q.order_line_id.map(ol.quantity)).all()

    rf = t["refund_line"]
    per = rf.groupby("refund_id").apply(lambda g: (g.refund_cents > g.paid_share_cents).any(), include_groups=False)
    assert per[sorted(ids_("REFUND_EXCEEDS_PAID"))].all()
    j = rf[rf.refund_id.isin(ids_("REFUND_EXCEEDS_PAID"))].groupby("order_line_id").refund_cents.sum()
    assert (j > ol.loc[j.index].paid_cents).any()

    mv = t["inventory_movement"].set_index("disposition_id")
    dsp = t["inventory_disposition"].set_index("disposition_id")
    ins = t["inspection"].set_index("inspection_id")
    for d in ids_("RESTOCK_BEFORE_INSPECTION"):
        assert mv.loc[d].posted_at < ins.loc[dsp.loc[d].inspection_id].inspected_at

    pol = build_policies()
    rq = t["return_request"].set_index("return_request_id")
    ordr = t["orders"].set_index("order_id")
    for lid in ids_("LATE_NO_OVERRIDE"):
        r = rl.loc[lid]
        o = ordr.loc[rq.loc[r.return_request_id].order_id]
        p = rules.policy_for(pol, ol.loc[r.order_line_id].category, o.delivery_date)
        days = (date.fromisoformat(rq.loc[r.return_request_id].requested_at) - date.fromisoformat(o.delivery_date)).days
        assert days > rules.allowed_days(p, r.reason_code)
        assert r.line_decision == "APPROVED" and pd.isna(r.override_code)

    refunds = t["refund"]
    issued = refunds[refunds.status == "ISSUED"].groupby("idempotency_key").size()
    dup_reqs = {refunds.set_index("refund_id").loc[r].return_request_id for r in ids_("DUPLICATE_REFUND")}
    assert set(issued[issued > 1].index) == {rules.idempotency_key(r) for r in dup_reqs}


def test_anomalies_disjoint_requests(gen):
    a = gen["ground_truth"]["anomalies"]
    assert a.return_request_id.is_unique
