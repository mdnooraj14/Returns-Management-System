"""Orchestrates master data -> orders -> return flow -> anomaly injection -> finalized DataFrames + ground truth."""
from __future__ import annotations

import pandas as pd

from . import config as C
from . import ids, master, returns, schema


def to_frame(name: str, rows: list[dict]) -> pd.DataFrame:
    t = schema.BY_NAME[name]
    df = pd.DataFrame(rows, columns=t.colnames)
    for c in t.cols:
        if c.type in ("int", "cents", "bool"):
            df[c.name] = df[c.name].astype("Int64")
    return df


def generate(p: C.Params, inject: bool = True) -> dict:
    products = master.build_products(p)
    policies = master.build_policies()
    customers, orders, lines = master.build_orders(p, products)
    ctx = returns.Ctx(p, customers, orders, lines, products, policies)
    cnt = ids.Counter()
    reqs = returns.pick_requests(ctx)
    returns.decide(ctx, reqs)

    late_targets: list[str] = []
    if inject:
        from . import anomalies
        late_targets = anomalies.plan_late_flips(reqs, p)
        returns.apply_late_flips(reqs, set(late_targets))
    T = returns.build_flow(ctx, reqs, cnt)
    anomaly_rows: list[dict] = []
    if inject:
        anomaly_rows = anomalies.inject(ctx, T, reqs, p, cnt, late_targets)

    renumber_refunds(T, anomaly_rows)
    ev = T["state_event"]
    order = sorted(range(len(ev)), key=lambda i: (ev[i]["event_ts"], ev[i]["entity_type"], ev[i]["entity_id"], i))
    T["state_event"] = [dict(event_id=ids.event_id(n), **ev[i]) for n, i in enumerate(order, start=1)]

    data = {"customer": customers, "product": products, "return_policy": policies, "orders": orders, "order_line": lines}
    data.update({k: v for k, v in T.items() if not k.startswith("_")})
    tables = {t.name: to_frame(t.name, data[t.name]) for t in schema.TABLES}
    gt = {
        "anomalies": pd.DataFrame(anomaly_rows, columns=ANOMALY_COLS),
        "decisions": pd.DataFrame(T["_decisions_gt"], columns=DECISION_COLS),
        "scenarios": pd.DataFrame(T["_scenarios"], columns=SCENARIO_COLS),
    }
    gt["anomalies"] = gt["anomalies"].sort_values(["issue_type", "entity_id"], kind="stable").reset_index(drop=True)
    gt["anomalies"].insert(0, "anomaly_id", [f"GT-{i:06d}" for i in range(1, len(gt["anomalies"]) + 1)])
    gt["scenarios"] = gt["scenarios"].sort_values(["scenario", "entity_id"], kind="stable").reset_index(drop=True)
    return dict(tables=tables, ground_truth=gt, params=p)


def renumber_refunds(T: dict, anomaly_rows: list[dict]) -> None:
    """Final, deterministic REF numbering in payout-date order, so injected payouts are not distinguishable by ID position."""
    refs = sorted(T["refund"], key=lambda r: (r["refund_date"], r["return_request_id"], r["attempt_no"]))
    m = {r["refund_id"]: ids.ref_id(i) for i, r in enumerate(refs, start=1)}
    for r in T["refund"]:
        r["refund_id"] = m[r["refund_id"]]
    T["refund"].sort(key=lambda r: r["refund_id"])
    for l in T["refund_line"]:
        k = int(l["refund_line_id"][-2:])
        l["refund_id"] = m[l["refund_id"]]
        l["refund_line_id"] = ids.ref_line_id(l["refund_id"], k)
    T["refund_line"].sort(key=lambda l: l["refund_line_id"])
    for e in T["state_event"]:
        if e["entity_type"] == "REFUND":
            e["entity_id"] = m[e["entity_id"]]
    for s in T["_scenarios"]:
        if s["entity_type"] == "REFUND":
            s["entity_id"] = m[s["entity_id"]]
    for a in anomaly_rows:
        if a["entity_type"] == "REFUND":
            a["entity_id"] = m[a["entity_id"]]


ANOMALY_COLS = ["issue_type", "entity_type", "entity_id", "return_request_id", "order_id", "field_changed", "original_value",
                "injected_value", "rule_violated"]
DECISION_COLS = ["return_line_id", "expected_line_decision", "expected_decision_reason", "expected_qty_approved",
                 "expected_override_code", "expected_disposition", "expected_refund_cents"]
SCENARIO_COLS = ["entity_type", "entity_id", "scenario"]
