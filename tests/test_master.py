from collections import defaultdict

import pytest

from rma import config as C
from rma import master

P = C.Params(scale=0.05)


@pytest.fixture(scope="module")
def data():
    prods = master.build_products(P)
    return prods, *master.build_orders(P, prods)


def test_volumes_and_ids(data):
    prods, cust, orders, lines = data
    assert len(orders) == P.orders and len(cust) == P.customers
    assert orders[0]["order_id"] == "ORD-2026-000001"
    assert [o["order_date"] for o in orders] == sorted(o["order_date"] for o in orders)
    assert len({l["order_line_id"] for l in lines}) == len(lines)


def test_totals_reconcile(data):
    _, cust, orders, lines = data
    by = defaultdict(list)
    for l in lines:
        by[l["order_id"]].append(l)
        assert l["gross_cents"] == l["quantity"] * l["unit_price_cents"]
        assert l["net_cents"] == l["gross_cents"] - l["discount_cents"]
        assert l["paid_cents"] == l["net_cents"] + l["tax_cents"]
    for o in orders:
        ls = by[o["order_id"]]
        assert o["subtotal_cents"] == sum(l["gross_cents"] for l in ls)
        assert o["discount_cents"] == sum(l["discount_cents"] for l in ls)
        assert o["tax_cents"] == sum(l["tax_cents"] for l in ls)
        assert o["total_cents"] == o["subtotal_cents"] - o["discount_cents"] + o["shipping_cents"] + o["tax_cents"]
        assert (o["delivery_date"] is None) == (o["status"] == "CANCELLED")


def test_customer_created_before_first_order(data):
    _, cust, orders, _ = data
    first = {}
    for o in orders:
        first.setdefault(o["customer_id"], o["order_date"])
    for c in cust:
        if c["customer_id"] in first:
            assert c["created_date"] <= first[c["customer_id"]]


def test_deterministic():
    a = master.build_orders(P, master.build_products(P))
    b = master.build_orders(P, master.build_products(P))
    assert a == b
