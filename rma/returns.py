"""Phase 3: return requests -> decisions -> authorization -> shipment -> inspection -> disposition -> refund.
Outcomes are derived by rma.rules from sampled *inputs* (customer behaviour, inspection condition); never assigned directly."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import numpy as np

from . import config as C
from . import ids, rules
from .master import pick, stream

SNAP = C.SNAPSHOT_DATE
D = date.fromisoformat

REASON_W = {
    "APPAREL": [.40, .25, .08, .10, .07, .05, .05], "FOOTWEAR": [.45, .22, .06, .09, .08, .05, .05],
    "ELECTRONICS": [0, .30, .12, .10, .30, .12, .06], "HOME": [0, .30, .15, .15, .15, .15, .10],
    "BEAUTY": [0, .30, .20, .15, .15, .10, .10], "CLEARANCE": [.10, .35, .15, .10, .15, .10, .05],
    "PERISHABLES": [0, .25, .10, .15, .20, .20, .10], "GIFT_CARDS": [0, .60, .30, .10, 0, 0, 0],
}
UNOPENED_P = {"APPAREL": .35, "FOOTWEAR": .35, "ELECTRONICS": .40, "HOME": .35, "BEAUTY": .30}
FOUND = {
    "DEFECTIVE": {"DEFECTIVE": .86, "USED": .08, "LIKE_NEW": .04, "SUSPECT_FRAUD": .02},
    "DAMAGED_IN_TRANSIT": {"DAMAGED_MINOR": .55, "DAMAGED_SEVERE": .38, "LIKE_NEW": .05, "SUSPECT_FRAUD": .02},
    "WRONG_ITEM": {"SEALED": .45, "LIKE_NEW": .50, "SUSPECT_FRAUD": .02, "NOT_ORIGINAL_ITEM": .03},
    "NOT_AS_DESCRIBED": {"LIKE_NEW": .45, "SEALED": .20, "USED": .20, "DEFECTIVE": .10, "NOT_ORIGINAL_ITEM": .03, "SUSPECT_FRAUD": .02},
    "UNOPENED": {"SEALED": .88, "LIKE_NEW": .08, "USED": .02, "DAMAGED_MINOR": .01, "NOT_ORIGINAL_ITEM": .005, "SUSPECT_FRAUD": .005},
    "OPENED": {"LIKE_NEW": .55, "USED": .30, "DAMAGED_MINOR": .08, "DAMAGED_SEVERE": .04, "NOT_ORIGINAL_ITEM": .015, "SUSPECT_FRAUD": .015},
}


def line_count_plan(n_req: int, n_lines: int, followup_frac: float = 0.06) -> dict[int, int]:
    """Requests with k lines (k=1..4) such that sum(count)=n_req and sum(k*count)=n_lines exactly."""
    k4, k3 = round(0.02 * n_req), round(0.10 * n_req)
    k2 = n_lines - n_req - 2 * k3 - 3 * k4
    k1 = n_req - k2 - k3 - k4
    if min(k1, k2, k3, k4) < 0:
        raise ValueError("infeasible line plan")
    return {1: k1, 2: k2, 3: k3, 4: k4}


def _weighted(rng, dist: dict) -> str:
    keys = list(dist)
    return keys[pick(rng, len(keys), [dist[k] for k in keys])]


def tstamp(d: date, stage: int, minute: int) -> str:
    m = 5 * 60 + stage * 95 + minute
    return f"{d.isoformat()}T{m // 60:02d}:{m % 60:02d}:{(minute * 7) % 60:02d}"


class Ctx:
    def __init__(self, p, customers, orders, lines, products, policies):
        self.p = p
        self.cust = {c["customer_id"]: c for c in customers}
        self.order = {o["order_id"]: o for o in orders}
        self.ol = {l["order_line_id"]: l for l in lines}
        self.prod = {x["product_id"]: x for x in products}
        self.policies = policies
        self.lines_of = defaultdict(list)
        for l in lines:
            self.lines_of[l["order_id"]].append(l)

    def policy(self, ol):
        return rules.policy_for(self.policies, ol["category"], self.order[ol["order_id"]]["delivery_date"])


# ------------------------------------------------------------------ request skeletons
def pick_requests(ctx: Ctx) -> list[dict]:
    p = ctx.p
    rng = stream(p.seed, "req_pick")
    plan = line_count_plan(p.requests, p.lines)
    F = round(0.06 * p.requests)
    delivered = [o for o in ctx.order.values() if o["status"] == "DELIVERED"]
    prop = {o["order_id"]: sum(C.RETURN_PROPENSITY[l["category"]] for l in ctx.lines_of[o["order_id"]]) for o in delivered}
    requested = defaultdict(int)
    reqs: list[dict] = []
    used: set[str] = set()

    def new_line(l, q):
        reason = C.REASONS[pick(rng, len(C.REASONS), REASON_W[l["category"]])]
        if reason == "DEFECTIVE":
            cond = "DEFECTIVE"
        elif reason == "DAMAGED_IN_TRANSIT":
            cond = "DAMAGED"
        elif reason == "WRONG_ITEM":
            cond = "UNOPENED" if rng.random() < .5 else "OPENED"
        elif reason == "NOT_AS_DESCRIBED":
            cond = "OPENED"
        else:
            cond = "UNOPENED" if rng.random() < UNOPENED_P.get(l["category"], .35) else "OPENED"
        requested[l["order_line_id"]] += q
        return dict(ol=l, qty=q, reason=reason, cond=cond)

    def lag_days(o, chosen):
        ws = [ctx.policy(l)["window_days"] for l in chosen if not ctx.policy(l)["final_sale"]]
        ref = max(ws) if ws else 30
        u = rng.random()
        if u < .80:
            lag = 1 + int(rng.beta(1.5, 2.5) * ref)
        elif u < .88:
            lag = ref + int(rng.integers(-1, 2))
        else:
            lag = ref + 1 + int(rng.exponential(12))
        return max(0, min(lag, (SNAP - D(o["delivery_date"])).days))

    for k in (4, 3, 2, 1):
        n_k = plan[k] - (F if k == 1 else 0)
        pool = [o for o in delivered if len(ctx.lines_of[o["order_id"]]) >= k and o["order_id"] not in used]
        if len(pool) < n_k:
            raise ValueError(f"not enough orders with >= {k} lines ({len(pool)} < {n_k})")
        w = np.array([prop[o["order_id"]] for o in pool], dtype=float)
        sel = rng.choice(len(pool), size=n_k, replace=False, p=w / w.sum())
        for si in sel:
            o = pool[int(si)]
            used.add(o["order_id"])
            ols = ctx.lines_of[o["order_id"]]
            lw = np.array([C.RETURN_PROPENSITY[l["category"]] for l in ols])
            ch = sorted(rng.choice(len(ols), size=k, replace=False, p=lw / lw.sum()).tolist())
            chosen = []
            for ci in ch:
                l = ols[ci]
                Q = l["quantity"]
                q = Q if (Q == 1 or rng.random() < .55) else int(rng.integers(1, Q))
                chosen.append(new_line(l, q))
            d = D(o["delivery_date"]) + timedelta(lag_days(o, [c["ol"] for c in chosen]))
            reqs.append(dict(order=o, lines=chosen, date=d, parent=None))

    primaries = list(reqs)
    made, attempts = 0, 0
    while made < F:
        attempts += 1
        if attempts > max(1000, F * 400):
            raise ValueError("could not place follow-up requests")
        par = primaries[int(rng.integers(0, len(primaries)))]
        cands = [l for l in ctx.lines_of[par["order"]["order_id"]] if requested[l["order_line_id"]] < l["quantity"]]
        if not cands:
            continue
        l = cands[int(rng.integers(0, len(cands)))]
        d = par["date"] + timedelta(4 + int(rng.integers(0, 22)))
        if d > SNAP:
            continue
        rem = l["quantity"] - requested[l["order_line_id"]]
        q = rem if rng.random() < .6 else int(rng.integers(1, rem + 1))
        reqs.append(dict(order=par["order"], lines=[new_line(l, q)], date=d, parent=par))
        made += 1

    for i, r in enumerate(reqs):
        r["seq"] = i
        r["resolution"] = "EXCHANGE" if rng.random() < .10 else "REFUND"
        r["method"] = None if r["resolution"] == "EXCHANGE" else C.REFUND_METHODS[pick(rng, 2, [.85, .15])]
        r["channel"] = C.CHANNELS[pick(rng, 4, [.60, .25, .10, .05])]
    reqs.sort(key=lambda r: (r["date"], r["seq"]))
    for i, r in enumerate(reqs, start=1):
        r["idx"] = i
        r["id"] = ids.rma_id(i)
        r["lines"].sort(key=lambda x: x["ol"]["line_no"])
        for k, ln in enumerate(r["lines"], start=1):
            ln["id"] = ids.rma_line_id(r["id"], k)
            ln["line_no"] = k
    return reqs


# ------------------------------------------------------------------ decisions (pass 1)
def decide(ctx: Ctx, reqs: list[dict]) -> None:
    prev = defaultdict(int)
    for r in reqs:
        rng = stream(ctx.p.seed, "decide", r["idx"])
        r["decided_at"] = r["date"] + timedelta(int(rng.choice([0, 1, 2], p=[.5, .35, .15])))
        r["pending"] = r["decided_at"] > SNAP
        o = r["order"]
        tier = ctx.cust[o["customer_id"]]["loyalty_tier"]
        for ln in r["lines"]:
            ln["flip"] = False
            if r["pending"]:
                ln["dec"] = ln["exp"] = None
                continue
            ol = ln["ol"]
            dec = rules.evaluate_line(ctx.policy(ol), D(o["delivery_date"]), r["date"], ln["reason"], ln["cond"], ln["qty"],
                                      ol["quantity"], prev[ol["order_line_id"]], tier)
            ln["dec"] = ln["exp"] = dec
            prev[ol["order_line_id"]] += dec.qty_approved


def apply_late_flips(reqs: list[dict], flip_ids: set[str]) -> None:
    """Injected control failure: late line approved without override (labelled in ground truth)."""
    for r in reqs:
        for ln in r["lines"]:
            if ln["id"] in flip_ids:
                ln["flip"] = True
                ln["dec"] = rules.LineDecision("APPROVED", "ELIGIBLE", ln["qty"], None, ln["exp"].days_since_delivery, ln["exp"].allowed_days)


# ------------------------------------------------------------------ downstream (pass 2)
def build_flow(ctx: Ctx, reqs: list[dict], cnt: ids.Counter) -> dict:
    p = ctx.p
    T = {k: [] for k in ("return_request", "return_line", "return_authorization", "return_shipment", "shipment_line", "inspection",
                         "inventory_disposition", "inventory_movement", "refund", "refund_line", "state_event")}
    last: dict = {}
    refunded_qty = defaultdict(int)
    ledger = rules.RefundLedger()
    gt_dec, scen = [], []
    used_tracking: set[str] = set()

    def ev(et, eid, to, d, stage, actor, reason=None, minute=0):
        assert d <= SNAP, (et, eid, to, d)
        T["state_event"].append(dict(entity_type=et, entity_id=eid, from_state=last.get((et, eid)), to_state=to,
                                     event_ts=tstamp(d, stage, minute), actor=actor, reason=reason))
        last[(et, eid)] = to

    def sc(et, eid, s):
        scen.append(dict(entity_type=et, entity_id=eid, scenario=s))

    for r in reqs:
        rng = stream(p.seed, "flow", r["idx"])
        rid, o = r["id"], r["order"]
        tier = ctx.cust[o["customer_id"]]["loyalty_tier"]
        T["return_request"].append(dict(return_request_id=rid, order_id=o["order_id"], customer_id=o["customer_id"],
                                        requested_at=r["date"].isoformat(), channel=r["channel"],
                                        resolution_requested=r["resolution"], refund_method=r["method"], status=None))
        ev("RETURN_REQUEST", rid, "SUBMITTED", r["date"], 0, "CUSTOMER")
        approved = [ln for ln in r["lines"] if ln["dec"] and ln["dec"].qty_approved > 0]
        mgr = f"MGR-{int(rng.integers(1, 9)):02d}"
        row_for = {}
        for ln in r["lines"]:
            dec = ln["dec"]
            row = dict(return_line_id=ln["id"], return_request_id=rid, line_no=ln["line_no"], order_line_id=ln["ol"]["order_line_id"],
                       qty_requested=ln["qty"], reason_code=ln["reason"], condition_declared=ln["cond"],
                       line_decision="PENDING" if dec is None else dec.decision, decision_reason=None if dec is None else dec.reason,
                       qty_approved=None if dec is None else dec.qty_approved,
                       override_code=None if dec is None else dec.override_code,
                       override_approved_by=mgr if dec is not None and dec.override_code else None,
                       decided_at=None if dec is None else r["decided_at"].isoformat())
            T["return_line"].append(row)
            row_for[ln["id"]] = row
            ln["exp_disp"], ln["exp_refund"] = None, 0
            if ln["flip"]:
                continue
            ol = ln["ol"]
            if ln["qty"] < ol["quantity"]:
                sc("RETURN_LINE", ln["id"], "PARTIAL_QTY_RETURN")
            if dec is not None:
                if dec.reason == "LATE_REQUEST":
                    sc("RETURN_LINE", ln["id"], "LATE_REJECTED")
                elif dec.reason == "LATE_OVERRIDE":
                    sc("RETURN_LINE", ln["id"], "LATE_OVERRIDE_APPROVED")
                elif dec.reason == "FINAL_SALE_CATEGORY":
                    sc("RETURN_LINE", ln["id"], "FINAL_SALE_REJECTED")
                elif dec.reason == "OPENED_NOT_RETURNABLE":
                    sc("RETURN_LINE", ln["id"], "OPENED_BEAUTY_REJECTED")
                if dec.decision == "APPROVED" and dec.days_since_delivery == dec.allowed_days:
                    sc("RETURN_LINE", ln["id"], "BOUNDARY_LAST_ELIGIBLE_DAY")
                if dec.days_since_delivery == dec.allowed_days + 1 and not dec.reason == "FINAL_SALE_CATEGORY":
                    sc("RETURN_LINE", ln["id"], "BOUNDARY_FIRST_LATE_DAY")
        if r["resolution"] == "EXCHANGE":
            sc("RETURN_REQUEST", rid, "EXCHANGE")

        if r["pending"]:
            continue
        if not approved:
            ev("RETURN_REQUEST", rid, "REJECTED", r["decided_at"], 1, "SYSTEM", r["lines"][0]["dec"].reason)
            continue

        # ---- authorization
        d_dec = r["decided_at"]
        partial = len(approved) < len(r["lines"])
        has_override = any(ln["dec"].override_code for ln in approved)
        aid = ids.auth_id(cnt.next("auth"))
        T["return_authorization"].append(dict(authorization_id=aid, return_request_id=rid, decision="PARTIALLY_APPROVED" if partial else "APPROVED",
                                              decided_at=d_dec.isoformat(), expires_at=(d_dec + timedelta(C.AUTH_VALID_DAYS)).isoformat(),
                                              authorized_by=mgr if has_override else "SYSTEM"))
        ev("RETURN_REQUEST", rid, "AUTHORIZED", d_dec, 1, "AGENT" if has_override else "SYSTEM")
        if partial:
            sc("RETURN_REQUEST", rid, "PARTIAL_APPROVAL")

        # ---- shipments
        two = len(approved) >= 2 and rng.random() < .12
        cut = int(rng.integers(1, len(approved))) if two else len(approved)
        groups = [approved[:cut], approved[cut:]] if two else [approved]
        will_ship = rng.random() >= .10
        lost = (not two) and will_ship and rng.random() < .015
        expires = d_dec + timedelta(C.AUTH_VALID_DAYS)
        parcels = []
        for pi, grp in enumerate(groups):
            sid = ids.rts_id(cnt.next("rts"))
            carrier = C.CARRIERS[int(rng.integers(0, 3))]
            trk = f"TRK{carrier[0]}{sid[-6:]}{int(rng.integers(100000, 999999))}"
            assert trk not in used_tracking
            used_tracking.add(trk)
            pc = dict(id=sid, lines=grp, shipped=None, received=None, lost=None, status="LABEL_ISSUED")
            ev("RETURN_SHIPMENT", sid, "LABEL_ISSUED", d_dec, 1, "SYSTEM")
            if will_ship:
                sh = d_dec + timedelta(1 + int(rng.integers(0, 12)) + pi * int(rng.integers(0, 3)))
                transit = 2 + int(rng.integers(0, 7))
                if sh <= SNAP:
                    pc["shipped"] = sh
                    ev("RETURN_SHIPMENT", sid, "IN_TRANSIT", sh, 2, "CARRIER")
                    if lost:
                        if sh + timedelta(10) <= SNAP:
                            pc["lost"] = sh + timedelta(10)
                            ev("RETURN_SHIPMENT", sid, "LOST", pc["lost"], 3, "CARRIER", "NO_SCAN_10_DAYS")
                    elif sh + timedelta(transit) <= SNAP:
                        pc["received"] = sh + timedelta(transit)
                        ev("RETURN_SHIPMENT", sid, "RECEIVED", pc["received"], 3, "WAREHOUSE")
            elif expires <= SNAP:
                ev("RETURN_SHIPMENT", sid, "VOIDED", expires, 2, "SYSTEM", "LABEL_UNUSED")
            parcels.append(pc)
            T["return_shipment"].append(dict(shipment_id=sid, authorization_id=aid, carrier=carrier, tracking_number=trk,
                                             label_issued_at=d_dec.isoformat(), shipped_at=pc["shipped"].isoformat() if pc["shipped"] else None,
                                             received_at=pc["received"].isoformat() if pc["received"] else None, status=None))
            for k, ln in enumerate(grp, start=1):
                qa = ln["dec"].qty_approved
                qs = None
                if pc["shipped"]:
                    qs = qa if (qa < 2 or rng.random() >= .06) else int(rng.integers(1, qa))
                    if qs < qa:
                        sc("RETURN_LINE", ln["id"], "PARTIAL_SHIPMENT")
                ln["qty_shipped"] = qs
                ln["parcel"] = pc
                T["shipment_line"].append(dict(shipment_line_id=ids.rts_line_id(sid, k), shipment_id=sid, return_line_id=ln["id"],
                                               qty_expected=qa, qty_shipped=qs, qty_received=qs if pc["received"] else None))
        shipped_ds = [pc["shipped"] for pc in parcels if pc["shipped"]]
        if shipped_ds:
            ev("RETURN_REQUEST", rid, "SHIPPED", min(shipped_ds), 2, "CUSTOMER")
        if not will_ship:
            sc("RETURN_REQUEST", rid, "MISSING_SHIPMENT")
            if expires <= SNAP:
                ev("RETURN_REQUEST", rid, "EXPIRED", expires, 2, "SYSTEM", "LABEL_UNUSED")
        lost_ds = [pc["lost"] for pc in parcels if pc["lost"]]
        if lost_ds:
            sc("RETURN_REQUEST", rid, "CARRIER_LOST")
            if lost_ds[0] + timedelta(1) <= SNAP:
                ev("RETURN_REQUEST", rid, "CLAIM_OPENED", lost_ds[0] + timedelta(1), 3, "AGENT", "CARRIER_LOSS")
                if lost_ds[0] + timedelta(4) <= SNAP:
                    ev("RETURN_REQUEST", rid, "CLOSED", lost_ds[0] + timedelta(4), 6, "AGENT", "CARRIER_LOSS_CLAIM")
        if not all(pc["received"] for pc in parcels):
            continue
        ev("RETURN_REQUEST", rid, "RECEIVED", max(pc["received"] for pc in parcels), 3, "WAREHOUSE")

        # ---- inspection / disposition / movement
        insp = []
        for pc in parcels:
            for ln in pc["lines"]:
                lag = int(rng.choice([0, 1, 2, 3], p=[.30, .35, .25, .10]))
                idt = pc["received"] + timedelta(lag)
                ol, qa = ln["ol"], ln["dec"].qty_approved
                found = _weighted(rng, FOUND[ln["reason"] if ln["reason"] in FOUND else ln["cond"]])
                dday = int(rng.choice([0, 1], p=[.7, .3]))
                mday = int(rng.integers(0, 3))
                inspector = f"INSP-OP-{int(rng.integers(1, 13)):02d}"
                insp.append(dict(ln=ln, idt=idt, found=found, dday=dday, mday=mday, inspector=inspector, pc=pc))
        for i in insp:
            ln = i["ln"]
            ol = ln["ol"]
            prod = ctx.prod[ol["product_id"]]
            grade = rules.grade_for(i["found"], ol["category"])
            fault = rules.fault_party(ln["reason"], i["found"])
            elig = rules.refund_eligible(fault, grade)
            disp = rules.disposition_for(grade, prod["unit_cost_cents"])
            i.update(grade=grade, fault=fault, elig=elig, disp=disp, qty=ln["qty_shipped"], prod=prod, policy=ctx.policy(ol))
            i["ddate"] = i["idt"] + timedelta(i["dday"])
            i["mdate"] = i["ddate"] + timedelta(i["mday"])
            ln["exp_disp"] = None if ln["flip"] else disp
            if i["found"] in ("DAMAGED_MINOR", "DAMAGED_SEVERE"):
                sc("RETURN_LINE", ln["id"], "DAMAGED_GOODS")
            if i["idt"] > SNAP:
                continue
            iid = ids.insp_id(cnt.next("insp"))
            T["inspection"].append(dict(inspection_id=iid, return_line_id=ln["id"], shipment_id=i["pc"]["id"], inspected_at=i["idt"].isoformat(),
                                        inspector_id=i["inspector"], qty_inspected=i["qty"], condition_found=i["found"], grade=grade,
                                        fault_party=fault, refund_eligible=int(elig)))
            i["iid"] = iid
            if i["ddate"] <= SNAP:
                did = ids.disp_id(cnt.next("disp"))
                T["inventory_disposition"].append(dict(disposition_id=did, inspection_id=iid, return_line_id=ln["id"], product_id=prod["product_id"],
                                                       disposition=disp, qty=i["qty"], destination_location=C.DISPOSITION_LOCATION[disp],
                                                       decided_at=i["ddate"].isoformat(),
                                                       est_recovery_cents=prod["unit_price_cents"] * i["qty"] * C.RECOVERY_FACTOR_BPS[disp] // 10000))
                if i["mdate"] <= SNAP:
                    T["inventory_movement"].append(dict(movement_id=ids.mov_id(cnt.next("mov")), disposition_id=did, return_line_id=ln["id"],
                                                        product_id=prod["product_id"], movement_type=C.MOVEMENT_TYPE[disp],
                                                        location=C.DISPOSITION_LOCATION[disp], qty=i["qty"],
                                                        sellable_qty_delta=i["qty"] if disp == "RESTOCK" else 0, posted_at=i["mdate"].isoformat()))
        if any(i["idt"] > SNAP for i in insp):
            continue
        max_idt = max(i["idt"] for i in insp)
        ev("RETURN_REQUEST", rid, "INSPECTED", max_idt, 4, "WAREHOUSE")
        plan_dates = [max_idt] + [i["mdate"] for i in insp]

        # ---- exchange replacements
        if r["resolution"] == "EXCHANGE":
            for i in insp:
                if not i["elig"]:
                    continue
                odate = i["idt"] + timedelta(1 + int(rng.integers(0, 2)))
                plan_dates.append(odate)
                if odate <= SNAP:
                    T["inventory_movement"].append(dict(movement_id=ids.mov_id(cnt.next("mov")), disposition_id=None, return_line_id=i["ln"]["id"],
                                                        product_id=i["prod"]["product_id"], movement_type="EXCHANGE_OUTBOUND", location="SELLABLE",
                                                        qty=i["qty"], sellable_qty_delta=-i["qty"], posted_at=odate.isoformat()))
        # ---- refund
        refund_date = None
        refund_pending = False
        if r["resolution"] == "REFUND":
            elig = [i for i in insp if i["elig"]]
            amounts = []
            for i in elig:
                ol = i["ln"]["ol"]
                a = rules.refund_line_amounts(ol, refunded_qty[ol["order_line_id"]], i["qty"], i["grade"], i["fault"], i["found"], i["policy"])
                amounts.append((i, a))
            total = sum(a["refund_cents"] for _, a in amounts)
            fee = rules.return_shipping_fee([i["fault"] for i in elig], tier, total)
            amount = total - fee
            if amount > 0:
                rdate = max_idt + timedelta(1 + int(rng.integers(0, 3)))
                dup = rng.random() < .02
                ddate = rdate + timedelta(int(rng.integers(0, 4)))
                if rdate > SNAP:
                    refund_pending = True
                else:
                    refund_date = rdate
                    fid = ids.ref_id(cnt.next("ref"))
                    key = rules.idempotency_key(rid)
                    status, paid = ledger.attempt(key, amount)
                    T["refund"].append(dict(refund_id=fid, return_request_id=rid, idempotency_key=key, attempt_no=1, method=r["method"], status=None,
                                            refund_date=rdate.isoformat(), refund_amount_cents=amount, paid_cents=paid,
                                            return_shipping_fee_cents=fee, currency="USD"))
                    ev("REFUND", fid, "INITIATED", rdate, 5, "FINANCE", minute=int(rng.integers(0, 15)))
                    ev("REFUND", fid, status, rdate, 5, "FINANCE", minute=15 + int(rng.integers(0, 15)))
                    for k, (i, a) in enumerate(amounts, start=1):
                        ol = i["ln"]["ol"]
                        T["refund_line"].append(dict(refund_line_id=ids.ref_line_id(fid, k), refund_id=fid, return_line_id=i["ln"]["id"],
                                                     order_line_id=ol["order_line_id"], **a))
                        refunded_qty[ol["order_line_id"]] += a["qty_refunded"]
                        if not i["ln"]["flip"]:
                            i["ln"]["exp_refund"] = a["refund_cents"]
                    ev("RETURN_REQUEST", rid, "REFUNDED", rdate, 5, "FINANCE", minute=20)
                    if dup and ddate <= SNAP:
                        fid2 = ids.ref_id(cnt.next("ref"))
                        st2, paid2 = ledger.attempt(key, amount)
                        T["refund"].append(dict(refund_id=fid2, return_request_id=rid, idempotency_key=key, attempt_no=2, method=r["method"], status=None,
                                                refund_date=ddate.isoformat(), refund_amount_cents=amount, paid_cents=paid2,
                                                return_shipping_fee_cents=fee, currency="USD"))
                        ev("REFUND", fid2, "INITIATED", ddate, 5, "FINANCE", minute=int(rng.integers(0, 15)))
                        ev("REFUND", fid2, st2, ddate, 5, "FINANCE", "IDEMPOTENCY_KEY_REPLAY", minute=15 + int(rng.integers(0, 15)))
                        sc("REFUND", fid2, "BLOCKED_DUPLICATE_ATTEMPT")
        if not refund_pending:
            end = max(plan_dates + ([refund_date] if refund_date else [])) + timedelta(1)
            if end <= SNAP:
                ev("RETURN_REQUEST", rid, "CLOSED", end, 6, "SYSTEM")

    # derived state columns
    for t, et, col in (("return_request", "RETURN_REQUEST", "return_request_id"), ("return_shipment", "RETURN_SHIPMENT", "shipment_id"),
                       ("refund", "REFUND", "refund_id")):
        for row in T[t]:
            row["status"] = last[(et, row[col])]

    for r in reqs:
        for ln in r["lines"]:
            e = ln["exp"]
            if e is None:
                continue
            gt_dec.append(dict(return_line_id=ln["id"], expected_line_decision=e.decision, expected_decision_reason=e.reason,
                               expected_qty_approved=e.qty_approved, expected_override_code=e.override_code,
                               expected_disposition=ln["exp_disp"], expected_refund_cents=ln["exp_refund"]))
    T["_decisions_gt"], T["_scenarios"], T["_refunded_qty"], T["_ledger"] = gt_dec, scen, refunded_qty, ledger
    return T
