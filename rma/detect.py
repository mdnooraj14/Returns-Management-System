"""Phase 6: rules-engine replay. Re-derives every eligibility, refund, duplicate-payout and restock decision from the stored
input tables using rma.rules and flags records whose stored outcome violates policy. Never reads ground truth."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

from . import rules


def _none(v):
    return None if pd.isna(v) else v


def load_tables(data_dir: Path) -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_csv(p) for p in sorted(Path(data_dir).glob("*.csv"))}


def detect_decisions(T: dict) -> list[dict]:
    pol = [{k: _none(v) for k, v in r.items()} for r in T["return_policy"].to_dict("records")]
    ol = T["order_line"].set_index("order_line_id").to_dict("index")
    orders = T["orders"].set_index("order_id").to_dict("index")
    tier = T["customer"].set_index("customer_id").loyalty_tier.to_dict()
    rq = T["return_request"].set_index("return_request_id").to_dict("index")
    prev = defaultdict(int)
    flags = []
    lines = T["return_line"].sort_values(["return_request_id", "line_no"])
    for r in lines.itertuples(index=False):
        if r.line_decision == "PENDING":
            continue
        req = rq[r.return_request_id]
        o = orders[req["order_id"]]
        line = ol[r.order_line_id]
        p = rules.policy_for(pol, line["category"], o["delivery_date"])
        rep = rules.evaluate_line(p, date.fromisoformat(o["delivery_date"]), date.fromisoformat(req["requested_at"]), r.reason_code,
                                  r.condition_declared, int(r.qty_requested), int(line["quantity"]), prev[r.order_line_id], tier[req["customer_id"]])
        stored = int(r.qty_approved)
        if stored > 0 and rep.reason == "LATE_REQUEST" and pd.isna(r.override_code):
            flags.append(dict(issue_type="LATE_NO_OVERRIDE", entity_type="RETURN_LINE", entity_id=r.return_line_id,
                              evidence=f"{rep.days_since_delivery}d since delivery > {rep.allowed_days}d window, no override"))
        elif stored > 0 and rep.qty_approved > 0 and stored > rep.qty_approved:
            flags.append(dict(issue_type="QTY_EXCEEDS_PURCHASED", entity_type="RETURN_LINE", entity_id=r.return_line_id,
                              evidence=f"approved {stored} > eligible {rep.qty_approved} (purchased {int(line['quantity'])}, previously approved {prev[r.order_line_id]})"))
        elif stored > 0 and rep.qty_approved == 0 and rep.reason != "LATE_REQUEST":
            flags.append(dict(issue_type="POLICY_DECISION_MISMATCH", entity_type="RETURN_LINE", entity_id=r.return_line_id,
                              evidence=f"approved but rules reject: {rep.reason}"))
        prev[r.order_line_id] += min(stored, rep.qty_approved)
    return flags


def detect_refunds(T: dict) -> list[dict]:
    pol = [{k: _none(v) for k, v in r.items()} for r in T["return_policy"].to_dict("records")]
    ol = T["order_line"].set_index("order_line_id").to_dict("index")
    orders = T["orders"].set_index("order_id").to_dict("index")
    insp = T["inspection"].set_index("return_line_id").to_dict("index")
    rq = T["return_request"].set_index("return_request_id").to_dict("index")
    rf = T["refund"].set_index("refund_id").to_dict("index")
    lines = T["refund_line"].copy()
    lines["rid"] = lines.refund_id.map(lambda x: rf[x]["return_request_id"])
    lines = lines.sort_values(["rid", "refund_line_id"])
    prev = defaultdict(int)
    cum = defaultdict(int)
    over: dict[str, str] = {}
    for r in lines.itertuples(index=False):
        line = ol[r.order_line_id]
        o = orders[rq[r.rid]["order_id"]]
        i = insp[r.return_line_id]
        p = rules.policy_for(pol, line["category"], o["delivery_date"])
        exp = rules.refund_line_amounts(line, prev[r.order_line_id], int(r.qty_refunded), i["grade"], i["fault_party"], i["condition_found"], p)
        prev[r.order_line_id] += int(r.qty_refunded)
        cum[r.order_line_id] += int(r.refund_cents)
        if r.refund_cents > exp["refund_cents"] or r.refund_cents > r.paid_share_cents:
            over[r.refund_id] = f"line {r.return_line_id}: refunded {int(r.refund_cents)} > rule-allowed {exp['refund_cents']}"
        elif cum[r.order_line_id] > line["paid_cents"]:
            over[r.refund_id] = f"cumulative refunds {cum[r.order_line_id]} > paid {line['paid_cents']} for {r.order_line_id}"
    flags = [dict(issue_type="REFUND_EXCEEDS_PAID", entity_type="REFUND", entity_id=k, evidence=v) for k, v in over.items()]

    ledger = rules.RefundLedger()
    for r in T["refund"].sort_values(["refund_date", "attempt_no", "refund_id"]).itertuples(index=False):
        status, _ = ledger.attempt(r.idempotency_key, int(r.refund_amount_cents))
        if status == "BLOCKED_DUPLICATE" and r.status == "ISSUED":
            flags.append(dict(issue_type="DUPLICATE_REFUND", entity_type="REFUND", entity_id=r.refund_id,
                              evidence=f"payout of {int(r.paid_cents)} issued again for key {r.idempotency_key}"))
    return flags


def detect_inventory(T: dict) -> list[dict]:
    m = T["inventory_movement"]
    m = m[m.movement_type == "RETURN_RESTOCK"].merge(T["inventory_disposition"][["disposition_id", "inspection_id"]], on="disposition_id")
    m = m.merge(T["inspection"][["inspection_id", "inspected_at"]], on="inspection_id")
    bad = m[m.posted_at < m.inspected_at]
    return [dict(issue_type="RESTOCK_BEFORE_INSPECTION", entity_type="INVENTORY_DISPOSITION", entity_id=r.disposition_id,
                 evidence=f"sellable stock posted {r.posted_at} before inspection {r.inspected_at}") for r in bad.itertuples()]


def run(dataset_dir: Path) -> pd.DataFrame:
    dataset_dir = Path(dataset_dir)
    T = load_tables(dataset_dir / "data")
    flags = detect_decisions(T) + detect_refunds(T) + detect_inventory(T)
    df = pd.DataFrame(flags, columns=["issue_type", "entity_type", "entity_id", "evidence"]).sort_values(["issue_type", "entity_id"]).reset_index(drop=True)
    (dataset_dir / "reports").mkdir(exist_ok=True)
    df.to_csv(dataset_dir / "reports" / "detections.csv", index=False, lineterminator="\n")
    return df
