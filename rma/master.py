"""Phase 2: master data (customers, products, policies) and orders/order lines."""
from __future__ import annotations

import zlib
from datetime import date, timedelta

import numpy as np

from . import config as C
from . import ids, rules

FIRST = ["Ava", "Liam", "Noah", "Emma", "Olivia", "Mason", "Sophia", "Lucas", "Mia", "Ethan", "Isla", "Aria", "Leo", "Zoe",
         "Ezra", "Nora", "Kai", "Maya", "Omar", "Priya", "Chen", "Sara", "Diego", "Anika", "Tariq", "Yuki", "Ines", "Femi", "Hana", "Ravi"]
LAST = ["Smith", "Johnson", "Lee", "Garcia", "Brown", "Davis", "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Patel",
        "Nguyen", "Kim", "Lopez", "Clark", "Lewis", "Walker", "Hall", "Young", "Allen", "King", "Wright", "Scott", "Green", "Baker",
        "Adams", "Nelson", "Hill"]
BRANDS = ["Northwind", "Alder", "Kestrel", "Juniper", "Harbor", "Summit", "Willow", "Ember"]


def stream(seed: int, name: str, *extra: int) -> np.random.Generator:
    """Independent, named, reproducible RNG stream."""
    return np.random.default_rng([seed, zlib.crc32(name.encode()), *extra])


def pick(rng, n, p):
    p = np.asarray(p, dtype=float)
    return rng.choice(n, p=p / p.sum())


def build_policies() -> list[dict]:
    return [dict(policy_id=ids.policy_id(r[0], r[1]), category=r[0], window_days=r[2], defect_extension_days=r[3],
                 final_sale=r[4], requires_unopened=r[5], restocking_fee_bps_opened=r[6], effective_from=r[7], effective_to=r[8])
            for r in C.POLICY_ROWS]


def build_products(p: C.Params) -> list[dict]:
    rng = stream(p.seed, "products")
    cats = rng.choice(len(C.CATEGORIES), size=p.products, p=np.array(C.CATEGORY_LINE_WEIGHT) / sum(C.CATEGORY_LINE_WEIGHT))
    cats[: len(C.CATEGORIES)] = np.arange(len(C.CATEGORIES))  # every category has at least one SKU
    out = []
    for i, ci in enumerate(sorted(cats.tolist()), start=1):
        cat = C.CATEGORIES[ci]
        if cat == "GIFT_CARDS":
            price = int(C.GIFT_CARD_VALUES_CENTS[int(rng.integers(0, 3))])
        else:
            med, lo, hi = C.PRICE_SHAPE[cat]
            dollars = float(np.clip(rng.lognormal(np.log(med), 0.55), lo, hi))
            price = int(dollars) * 100 + 99
        cost = max(1, min(price - 1, int(round(price * float(rng.uniform(0.35, 0.70))))))
        out.append(dict(product_id=ids.product_id(i), name=f"{BRANDS[int(rng.integers(0, len(BRANDS)))]} {cat.title().replace('_', ' ')} {i:04d}",
                        category=cat, unit_price_cents=price, unit_cost_cents=cost))
    return out


def _month_day_weights():
    days = (C.ORDER_END - C.ORDER_START).days + 1
    mw = {1: 0.9, 2: 0.85, 3: 1.0, 4: 1.0, 5: 1.05, 6: 1.0, 7: 1.1, 8: 1.0, 9: 1.1}
    w = np.array([mw[(C.ORDER_START + timedelta(d)).month] for d in range(days)], dtype=float)
    return days, w / w.sum()


def build_orders(p: C.Params, products: list[dict]):
    """Returns customers, orders, order_lines (lists of dicts). All order/line totals derived from line inputs."""
    rng = stream(p.seed, "orders")
    n, nc = p.orders, p.customers
    ndays, dw = _month_day_weights()
    day = np.sort(rng.choice(ndays, size=n, p=dw))
    cw = rng.gamma(0.9, size=nc)
    cust = rng.choice(nc, size=n, p=cw / cw.sum())
    nlines = rng.choice(np.arange(1, 7), size=n, p=[0.30, 0.30, 0.20, 0.10, 0.06, 0.04])
    cancelled = rng.random(n) < 0.02
    ship_lag = rng.choice([2, 3, 4, 5, 6, 7], size=n, p=[0.15, 0.25, 0.25, 0.15, 0.12, 0.08])
    coupon = rng.choice(len(C.COUPONS), size=n, p=C.COUPON_WEIGHT)
    pay = rng.choice(len(C.PAYMENT_METHODS), size=n, p=[0.7, 0.2, 0.1])

    # customers
    crng = stream(p.seed, "customers")
    states = list(C.STATE_TAX_BPS)
    c_state = crng.choice(len(states), size=nc, p=np.array(C.STATE_WEIGHT) / sum(C.STATE_WEIGHT))
    c_tier = crng.choice(3, size=nc, p=[0.80, 0.14, 0.06])
    c_first = crng.integers(0, len(FIRST), size=nc)
    c_last = crng.integers(0, len(LAST), size=nc)
    c_back = crng.integers(0, 366, size=nc)
    c_free = crng.integers(0, 420, size=nc)

    # lines
    L = int(nlines.sum())
    lrng = stream(p.seed, "order_lines")
    line_cat = lrng.choice(len(C.CATEGORIES), size=L, p=np.array(C.CATEGORY_LINE_WEIGHT) / sum(C.CATEGORY_LINE_WEIGHT))
    qty = lrng.choice([1, 2, 3, 4, 5], size=L, p=[0.62, 0.20, 0.10, 0.05, 0.03])
    prod_by_cat = {c: [pr for pr in products if pr["category"] == c] for c in C.CATEGORIES}
    line_prod = np.zeros(L, dtype=int)
    for ci, cat in enumerate(C.CATEGORIES):
        m = np.where(line_cat == ci)[0]
        if len(m):
            w = 1.0 / np.arange(1, len(prod_by_cat[cat]) + 1) ** 0.6
            line_prod[m] = lrng.choice(len(prod_by_cat[cat]), size=len(m), p=w / w.sum())

    orders, lines = [], []
    first_order_date: dict[int, date] = {}
    pos = 0
    for i in range(n):
        oid = ids.order_id(i + 1)
        od = C.ORDER_START + timedelta(int(day[i]))
        ci = int(cust[i])
        first_order_date.setdefault(ci, od)
        state = states[int(c_state[ci])]
        bps = C.STATE_TAX_BPS[state]
        raw = []
        for k in range(int(nlines[i])):
            cat = C.CATEGORIES[int(line_cat[pos])]
            pr = prod_by_cat[cat][int(line_prod[pos])]
            q = 1 if cat == "GIFT_CARDS" else int(qty[pos])
            raw.append((cat, pr, q))
            pos += 1
        gross = [q * pr["unit_price_cents"] for _, pr, q in raw]
        elig = [0 if cat in C.DISCOUNT_EXCLUDED_CATEGORIES else g for (cat, _, _), g in zip(raw, gross)]
        code, pct = C.COUPONS[int(coupon[i])]
        disc_total = (sum(elig) * pct + 50) // 100
        disc = rules.allocate(disc_total, elig)
        sub = sum(gross)
        tax_tot = 0
        for k, ((cat, pr, q), g, d) in enumerate(zip(raw, gross, disc), start=1):
            net = g - d
            rate = 0 if cat in C.TAX_EXEMPT_CATEGORIES else bps
            tax = rules.bps_round(net, rate)
            tax_tot += tax
            lines.append(dict(order_line_id=ids.order_line_id(oid, k), order_id=oid, line_no=k, product_id=pr["product_id"], category=cat,
                              quantity=q, unit_price_cents=pr["unit_price_cents"], gross_cents=g, discount_cents=d, net_cents=net,
                              tax_rate_bps=rate, tax_cents=tax, paid_cents=net + tax))
        shipping = 0 if sub - disc_total >= C.FREE_SHIPPING_THRESHOLD_CENTS else C.SHIPPING_FEE_CENTS
        canc = bool(cancelled[i])
        orders.append(dict(order_id=oid, customer_id=ids.customer_id(ci + 1), order_date=od.isoformat(),
                           status="CANCELLED" if canc else "DELIVERED",
                           delivery_date=None if canc else (od + timedelta(int(ship_lag[i]))).isoformat(),
                           ship_state=state, payment_method=C.PAYMENT_METHODS[int(pay[i])], coupon_code=code,
                           subtotal_cents=sub, discount_cents=disc_total, shipping_cents=shipping, tax_cents=tax_tot,
                           total_cents=sub - disc_total + shipping + tax_tot))

    customers = []
    for ci in range(nc):
        if ci in first_order_date:
            created = first_order_date[ci] - timedelta(int(c_back[ci]))
        else:
            created = date(2025, 1, 1) + timedelta(int(c_free[ci]))
        f, l = FIRST[int(c_first[ci])], LAST[int(c_last[ci])]
        customers.append(dict(customer_id=ids.customer_id(ci + 1), first_name=f, last_name=l,
                              email=f"{f.lower()}.{l.lower()}{ci + 1}@example.com", state=states[int(c_state[ci])],
                              loyalty_tier=C.LOYALTY_TIERS[int(c_tier[ci])], created_date=created.isoformat()))
    return customers, orders, lines
