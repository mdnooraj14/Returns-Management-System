"""Phase 6: operational, financial, control and detection metrics. Detection is scored against ground truth
(the only place ground truth is read); every other metric is computed from the input tables alone."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import config as C
from .detect import load_tables


def _d(s):
    return pd.to_datetime(s)


def operational(T: dict) -> dict:
    orders, ol, rq, rl = T["orders"], T["order_line"], T["return_request"], T["return_line"]
    delivered = orders[orders.status == "DELIVERED"]
    dec = rl[rl.line_decision != "PENDING"]
    approved = dec.qty_approved > 0
    cat = rl.merge(ol[["order_line_id", "category"]], on="order_line_id")
    cat = cat[cat.line_decision != "PENDING"]
    by_cat = cat.groupby("category").apply(lambda g: round(float((g.qty_approved > 0).mean()), 4), include_groups=False).to_dict()
    req_dec = rq.merge(rl.groupby("return_request_id").decided_at.min().rename("decided_at"), on="return_request_id")
    cyc = {}
    a = T["return_authorization"].merge(rq[["return_request_id", "requested_at"]], on="return_request_id")
    cyc["request_to_decision"] = (_d(a.decided_at) - _d(a.requested_at)).dt.days
    sh = T["return_shipment"].merge(a[["authorization_id", "decided_at"]], on="authorization_id")
    cyc["decision_to_ship"] = (_d(sh.shipped_at) - _d(sh.decided_at)).dt.days.dropna()
    cyc["ship_to_receive"] = (_d(sh.received_at) - _d(sh.shipped_at)).dt.days.dropna()
    ins = T["inspection"].merge(T["return_shipment"][["shipment_id", "received_at"]], on="shipment_id")
    cyc["receive_to_inspect"] = (_d(ins.inspected_at) - _d(ins.received_at)).dt.days
    last_ins = T["inspection"].merge(rl[["return_line_id", "return_request_id"]], on="return_line_id").groupby("return_request_id").inspected_at.max()
    f1 = T["refund"][T["refund"].attempt_no == 1].set_index("return_request_id").refund_date
    j = pd.concat([last_ins, f1], axis=1, join="inner")
    cyc["inspect_to_refund"] = (_d(j.refund_date) - _d(j.inspected_at)).dt.days
    rq_ref = rq.set_index("return_request_id").requested_at
    cyc["request_to_refund"] = (_d(f1) - _d(rq_ref.loc[f1.index])).dt.days
    cycle = {k: dict(n=int(len(v)), mean=round(float(v.mean()), 2), median=float(v.median()), p90=float(v.quantile(.9))) for k, v in cyc.items()}
    st = rq.status.value_counts().to_dict()
    sh_st = T["return_shipment"].status.value_counts().to_dict()
    return dict(
        orders=int(len(orders)), delivered_orders=int(len(delivered)), return_requests=int(len(rq)), return_lines=int(len(rl)),
        request_rate_per_delivered_order=round(len(rq) / len(delivered), 4), line_return_rate=round(len(rl) / len(ol), 4),
        line_approval_rate=round(float(approved.mean()), 4), approval_rate_by_category=by_cat,
        decision_reasons=dec.decision_reason.value_counts().to_dict(),
        override_approvals=int((dec.line_decision == "APPROVED_OVERRIDE").sum()),
        request_status=st, shipment_status=sh_st, exchange_requests=int((rq.resolution_requested == "EXCHANGE").sum()),
        partial_approvals=int((T["return_authorization"].decision == "PARTIALLY_APPROVED").sum()),
        unused_labels_voided=int(sh_st.get("VOIDED", 0)), carrier_lost=int(sh_st.get("LOST", 0)), cycle_days=cycle)


def financial(T: dict) -> dict:
    rf, rl = T["refund"], T["refund_line"]
    issued = rf[rf.status == "ISSUED"]
    delivered_rev = float((T["orders"].query("status == 'DELIVERED'").total_cents).sum())
    first = issued[issued.attempt_no == 1]
    over = rl.refund_cents.sub(rl.paid_share_cents).clip(lower=0).sum()
    dup = issued[issued.attempt_no > 1].paid_cents.sum()
    d = T["inventory_disposition"]
    disp = d.groupby("disposition").agg(units=("qty", "sum"), lines=("qty", "size"), est_recovery_cents=("est_recovery_cents", "sum"))
    merch = float(first.refund_amount_cents.sum())
    return dict(
        refunds_issued=int(len(issued)), refunded_cents=int(issued.paid_cents.sum()), refunded_first_attempt_cents=int(first.paid_cents.sum()),
        refund_pct_of_delivered_revenue=round(float(first.paid_cents.sum()) / delivered_rev, 5), avg_refund_cents=round(float(first.paid_cents.mean()), 1),
        restocking_fees_cents=int(rl.restocking_fee_cents.sum()), condition_deductions_cents=int(rl.condition_deduction_cents.sum()),
        return_shipping_fees_cents=int(first.return_shipping_fee_cents.sum()),
        refund_exposure_over_paid_cents=int(over), duplicate_payout_leak_cents=int(dup),
        disposition_mix={k: {kk: int(vv) for kk, vv in v.items()} for k, v in disp.to_dict("index").items()},
        est_recovery_cents=int(d.est_recovery_cents.sum()), recovery_to_refund_ratio=round(float(d.est_recovery_cents.sum()) / merch, 4) if merch else None)


def controls(T: dict) -> dict:
    rf, rl = T["refund"], T["refund_line"]
    attempts2 = rf[rf.attempt_no > 1]
    blocked = int((attempts2.status == "BLOCKED_DUPLICATE").sum())
    leaked = int((attempts2.status == "ISSUED").sum())
    h = rf[rf.attempt_no == 1].merge(rl.groupby("refund_id").refund_cents.sum().rename("s"), on="refund_id")
    recon = float(((h.s - h.return_shipping_fee_cents) == h.refund_amount_cents).mean())
    m = T["inventory_movement"]
    m = m[m.movement_type == "RETURN_RESTOCK"].merge(T["inventory_disposition"][["disposition_id", "inspection_id"]], on="disposition_id").merge(
        T["inspection"][["inspection_id", "inspected_at"]], on="inspection_id")
    return dict(duplicate_attempts=int(len(attempts2)), duplicates_blocked=blocked, duplicates_paid=leaked,
                duplicate_block_rate=round(blocked / max(1, blocked + leaked), 4), refund_header_reconciliation_rate=round(recon, 5),
                restocks_posted=int(len(m)), restocks_before_inspection=int((m.posted_at < m.inspected_at).sum()))


def detection(dataset_dir: Path, det: pd.DataFrame) -> dict:
    gt = pd.read_csv(Path(dataset_dir) / "ground_truth" / "anomalies.csv")
    out, TP, FP, FN = {}, 0, 0, 0
    for t in C.ISSUE_TYPES:
        g = set(gt[gt.issue_type == t].entity_id)
        f = set(det[det.issue_type == t].entity_id)
        tp, fp, fn = len(g & f), len(f - g), len(g - f)
        p = tp / (tp + fp) if tp + fp else 1.0
        r = tp / (tp + fn) if tp + fn else 1.0
        out[t] = dict(labelled=len(g), flagged=len(f), tp=tp, fp=fp, fn=fn, precision=round(p, 4), recall=round(r, 4),
                      f1=round(2 * p * r / (p + r), 4) if p + r else 0.0)
        TP, FP, FN = TP + tp, FP + fp, FN + fn
    p = TP / (TP + FP) if TP + FP else 1.0
    r = TP / (TP + FN) if TP + FN else 1.0
    out["_overall"] = dict(labelled=TP + FN, flagged=TP + FP, tp=TP, fp=FP, fn=FN, precision=round(p, 4), recall=round(r, 4),
                           f1=round(2 * p * r / (p + r), 4) if p + r else 0.0)
    out["_unlabelled_flags"] = det[~det.issue_type.isin(C.ISSUE_TYPES)].issue_type.value_counts().to_dict()
    return out


def decision_accuracy(dataset_dir: Path, T: dict) -> dict:
    """Stored decisions vs ground-truth expected decisions (rules applied without injection)."""
    gt = pd.read_csv(Path(dataset_dir) / "ground_truth" / "decisions.csv")
    m = gt.merge(T["return_line"], on="return_line_id")
    ok_dec = (m.expected_line_decision == m.line_decision) & (m.expected_qty_approved == m.qty_approved)
    disp = T["inventory_disposition"][["return_line_id", "disposition"]]
    mm = gt.dropna(subset=["expected_disposition"]).merge(disp, on="return_line_id")
    rfd = T["refund_line"].groupby("return_line_id").refund_cents.sum().rename("stored_refund")
    mr = gt.merge(rfd, on="return_line_id", how="left").fillna({"stored_refund": 0})
    return dict(eligibility_decision_accuracy=round(float(ok_dec.mean()), 5), eligibility_mismatches=int((~ok_dec).sum()),
                disposition_accuracy=round(float((mm.expected_disposition == mm.disposition).mean()), 5),
                refund_amount_accuracy=round(float((mr.expected_refund_cents == mr.stored_refund).mean()), 5),
                refund_amount_mismatches=int((mr.expected_refund_cents != mr.stored_refund).sum()))


def compute(dataset_dir: Path, det: pd.DataFrame) -> dict:
    dataset_dir = Path(dataset_dir)
    T = load_tables(dataset_dir / "data")
    res = dict(operational=operational(T), financial=financial(T), controls=controls(T), detection=detection(dataset_dir, det),
               decision_accuracy=decision_accuracy(dataset_dir, T))
    rep = dataset_dir / "reports"
    rep.mkdir(exist_ok=True)
    (rep / "metrics.json").write_text(json.dumps(res, indent=2, default=int), encoding="utf-8", newline="\n")
    (rep / "metrics.md").write_text(to_markdown(res), encoding="utf-8", newline="\n")
    return res


def to_markdown(m: dict) -> str:
    o, f, c, d, a = m["operational"], m["financial"], m["controls"], m["detection"], m["decision_accuracy"]
    L = ["# Metrics", "", "## Detection (rules replay vs ground truth)", "", "| Issue type | Labelled | Flagged | TP | FP | FN | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in d.items():
        if not k.startswith("_unl"):
            L.append(f"| {k.strip('_')} | {v['labelled']} | {v['flagged']} | {v['tp']} | {v['fp']} | {v['fn']} | {v['precision']} | {v['recall']} | {v['f1']} |")
    L += ["", "## Decision accuracy vs ground-truth expectations", "", f"- eligibility decisions: {a['eligibility_decision_accuracy']:.4%} ({a['eligibility_mismatches']} mismatches = injected late approvals + qty overrides)",
          f"- disposition: {a['disposition_accuracy']:.4%}; refund amount per line: {a['refund_amount_accuracy']:.4%} ({a['refund_amount_mismatches']} mismatches = injected over-refunds + refunds paid on wrongly approved late lines)",
          "", "## Operations", "", f"- request rate per delivered order: {o['request_rate_per_delivered_order']:.2%}; returned lines / lines sold: {o['line_return_rate']:.2%}",
          f"- line approval rate: {o['line_approval_rate']:.2%}; override approvals: {o['override_approvals']}; exchanges: {o['exchange_requests']}; partial approvals: {o['partial_approvals']}",
          f"- unused labels voided: {o['unused_labels_voided']}; carrier-lost parcels: {o['carrier_lost']}", "", "| Stage | n | mean d | median d | p90 d |", "|---|---|---|---|---|"]
    L += [f"| {k} | {v['n']} | {v['mean']} | {v['median']} | {v['p90']} |" for k, v in o["cycle_days"].items()]
    L += ["", "## Financial", "", f"- refunds issued: {f['refunds_issued']}; total paid: ${f['refunded_cents'] / 100:,.2f}; refunded / delivered revenue: {f['refund_pct_of_delivered_revenue']:.2%}",
          f"- fees retained: restocking ${f['restocking_fees_cents'] / 100:,.2f}, condition deductions ${f['condition_deductions_cents'] / 100:,.2f}, return shipping ${f['return_shipping_fees_cents'] / 100:,.2f}",
          f"- exposure: over-refund ${f['refund_exposure_over_paid_cents'] / 100:,.2f}; duplicate payout leak ${f['duplicate_payout_leak_cents'] / 100:,.2f}",
          f"- estimated recovery from dispositions: ${f['est_recovery_cents'] / 100:,.2f} ({f['recovery_to_refund_ratio']:.2%} of refunds)", "",
          "| Disposition | Lines | Units | Est. recovery $ |", "|---|---|---|---|"]
    L += [f"| {k} | {v['lines']} | {v['units']} | {v['est_recovery_cents'] / 100:,.2f} |" for k, v in f["disposition_mix"].items()]
    L += ["", "## Controls", "", f"- duplicate refund attempts: {c['duplicate_attempts']} -> blocked {c['duplicates_blocked']}, paid {c['duplicates_paid']} (block rate {c['duplicate_block_rate']:.2%})",
          f"- refund header reconciliation rate: {c['refund_header_reconciliation_rate']:.3%}; restocks posted before inspection: {c['restocks_before_inspection']} of {c['restocks_posted']}"]
    return "\n".join(L) + "\n"
