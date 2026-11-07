"""Phase 4: labelled edge-case injection. Every injected row is described in ground truth (issue_type, field, before/after).
No label, flag or distinctive text is written into the input tables."""
from __future__ import annotations

from datetime import date, timedelta

from . import config as C
from . import ids
from .master import stream

SNAP = C.SNAPSHOT_DATE


def plan_late_flips(reqs: list[dict], p: C.Params) -> list[str]:
    """Late requests that policy rejects (no override eligible) -> chosen to be wrongly approved downstream."""
    rng = stream(p.seed, "anom_late")
    cands = []
    for r in reqs:
        for ln in r["lines"]:
            if ln["exp"] is not None and ln["exp"].reason == "LATE_REQUEST":
                cands.append(ln["id"])
                break  # one candidate line per request
    n = min(p.anomalies_per_type, len(cands))
    sel = rng.choice(len(cands), size=n, replace=False)
    return sorted(cands[int(i)] for i in sel)


def _one_per_request(items: list, key) -> list:
    seen, out = set(), []
    for it in items:
        k = key(it)
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def _choose(rng, items: list, n: int) -> list:
    n = min(n, len(items))
    return [items[int(i)] for i in sorted(rng.choice(len(items), size=n, replace=False).tolist())]


def inject(ctx, T: dict, reqs: list[dict], p: C.Params, cnt: ids.Counter, late_targets: list[str]) -> list[dict]:
    n = p.anomalies_per_type
    out: list[dict] = []
    line_row = {r["return_line_id"]: r for r in T["return_line"]}
    req_of_line = {k: v["return_request_id"] for k, v in line_row.items()}
    order_of_req = {r["return_request_id"]: r["order_id"] for r in T["return_request"]}
    used = {req_of_line[i] for i in late_targets}

    def add(issue, et, eid, rid, field, before, after, rule):
        out.append(dict(issue_type=issue, entity_type=et, entity_id=eid, return_request_id=rid, order_id=order_of_req[rid],
                        field_changed=field, original_value=str(before), injected_value=str(after), rule_violated=rule))

    for lid in late_targets:
        row = line_row[lid]
        add("LATE_NO_OVERRIDE", "RETURN_LINE", lid, row["return_request_id"], "line_decision,decision_reason,override_code",
            "REJECTED,LATE_REQUEST,NULL", f"{row['line_decision']},{row['decision_reason']},NULL",
            "request after policy window approved without override")

    # 1. quantity exceeds purchased
    rng = stream(p.seed, "anom_qty")
    per_ol: dict[str, int] = {}
    for r in T["return_line"]:
        per_ol[r["order_line_id"]] = per_ol.get(r["order_line_id"], 0) + 1
    # only order lines with a single return line: a sibling's legitimate approval must not be affected by the injection
    cands = [r for r in T["return_line"] if r["qty_approved"] and r["return_request_id"] not in used and per_ol[r["order_line_id"]] == 1]
    for row in _choose(rng, _one_per_request(cands, lambda r: r["return_request_id"]), n):
        Q = ctx.ol[row["order_line_id"]]["quantity"]
        new = Q + int(rng.integers(1, 3))
        add("QTY_EXCEEDS_PURCHASED", "RETURN_LINE", row["return_line_id"], row["return_request_id"], "qty_requested,qty_approved",
            f"{row['qty_requested']},{row['qty_approved']}", f"{new},{new}", f"approved quantity exceeds purchased quantity {Q}")
        row["qty_requested"] = row["qty_approved"] = new
        used.add(row["return_request_id"])

    # 2. refund exceeds paid amount
    rng = stream(p.seed, "anom_refund_exceeds")
    lines_of_refund: dict[str, list[dict]] = {}
    for l in T["refund_line"]:
        lines_of_refund.setdefault(l["refund_id"], []).append(l)
    cands = []
    for rf in T["refund"]:
        if rf["attempt_no"] != 1 or rf["status"] != "ISSUED" or rf["return_request_id"] in used:
            continue
        full = [l for l in lines_of_refund.get(rf["refund_id"], []) if l["qty_refunded"] == ctx.ol[l["order_line_id"]]["quantity"]]
        if full:
            cands.append((rf, full[0]))
    for rf, l in _choose(rng, cands, n):
        extra = max(100, l["paid_share_cents"] * int(rng.integers(5, 31)) // 100)
        before = rf["refund_amount_cents"]
        l["refund_cents"] = l["paid_share_cents"] + extra
        total = sum(x["refund_cents"] for x in lines_of_refund[rf["refund_id"]])
        rf["refund_amount_cents"] = rf["paid_cents"] = total - rf["return_shipping_fee_cents"]
        add("REFUND_EXCEEDS_PAID", "REFUND", rf["refund_id"], rf["return_request_id"], "refund_line.refund_cents,refund_amount_cents,paid_cents",
            f"{l['paid_share_cents'] - l['restocking_fee_cents'] - l['condition_deduction_cents']},{before}",
            f"{l['refund_cents']},{rf['refund_amount_cents']}", "refund exceeds amount paid for the order line")
        used.add(rf["return_request_id"])

    # 3. restock before inspection
    rng = stream(p.seed, "anom_restock")
    disp = {d["disposition_id"]: d for d in T["inventory_disposition"]}
    insp = {i["inspection_id"]: i for i in T["inspection"]}
    cands = [m for m in T["inventory_movement"] if m["movement_type"] == "RETURN_RESTOCK" and m["return_line_id"] and
             req_of_line[m["return_line_id"]] not in used]
    for m in _choose(rng, _one_per_request(cands, lambda m: req_of_line[m["return_line_id"]]), n):
        ins = insp[disp[m["disposition_id"]]["inspection_id"]]
        new = (date.fromisoformat(ins["inspected_at"]) - timedelta(int(rng.integers(1, 4)))).isoformat()
        add("RESTOCK_BEFORE_INSPECTION", "INVENTORY_DISPOSITION", m["disposition_id"], req_of_line[m["return_line_id"]], "inventory_movement.posted_at",
            m["posted_at"], new, f"sellable stock posted before inspection on {ins['inspected_at']}")
        m["posted_at"] = new
        used.add(req_of_line[m["return_line_id"]])

    # 4. duplicate refund (second ISSUED payout for the same idempotency key)
    rng = stream(p.seed, "anom_duplicate")
    has_second = {r["return_request_id"] for r in T["refund"] if r["attempt_no"] > 1}
    cands = [rf for rf in T["refund"] if rf["attempt_no"] == 1 and rf["status"] == "ISSUED" and rf["return_request_id"] not in used
             and rf["return_request_id"] not in has_second and rf["refund_date"] <= (SNAP - timedelta(4)).isoformat()]
    from .returns import tstamp
    for rf in _choose(rng, cands, n):
        d = date.fromisoformat(rf["refund_date"]) + timedelta(int(rng.integers(1, 5)))
        fid = ids.ref_id(cnt.next("ref"))
        T["refund"].append(dict(refund_id=fid, return_request_id=rf["return_request_id"], idempotency_key=rf["idempotency_key"], attempt_no=2,
                                method=rf["method"], status="ISSUED", refund_date=d.isoformat(), refund_amount_cents=rf["refund_amount_cents"],
                                paid_cents=rf["refund_amount_cents"], return_shipping_fee_cents=rf["return_shipping_fee_cents"], currency="USD"))
        for k, (st, m) in enumerate((("INITIATED", 3), ("ISSUED", 20)), start=0):
            T["state_event"].append(dict(entity_type="REFUND", entity_id=fid, from_state=None if k == 0 else "INITIATED", to_state=st,
                                         event_ts=tstamp(d, 5, m), actor="FINANCE", reason=None))
        add("DUPLICATE_REFUND", "REFUND", fid, rf["return_request_id"], "refund.attempt_no,status,paid_cents", "(none)",
            f"2,ISSUED,{rf['refund_amount_cents']}", "second payout issued for an already-paid idempotency key")
        used.add(rf["return_request_id"])
    return out
