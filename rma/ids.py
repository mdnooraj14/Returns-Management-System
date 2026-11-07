"""Deterministic, zero-padded, immutable ID builders and the regex each ID must satisfy."""
from __future__ import annotations

from .config import YEAR

PATTERNS = {
    "customer_id": r"^CUST-\d{6}$",
    "product_id": r"^SKU-\d{6}$",
    "policy_id": r"^POL-[A-Z_]+-V\d+$",
    "order_id": rf"^ORD-{YEAR}-\d{{6}}$",
    "order_line_id": rf"^ORDL-ORD-{YEAR}-\d{{6}}-\d{{2}}$",
    "return_request_id": rf"^RMA-{YEAR}-\d{{6}}$",
    "return_line_id": rf"^RMAL-RMA-{YEAR}-\d{{6}}-\d{{2}}$",
    "authorization_id": rf"^AUTH-{YEAR}-\d{{6}}$",
    "shipment_id": rf"^RTS-{YEAR}-\d{{6}}$",
    "shipment_line_id": rf"^RTSL-RTS-{YEAR}-\d{{6}}-\d{{2}}$",
    "inspection_id": rf"^INSP-{YEAR}-\d{{6}}$",
    "disposition_id": rf"^DISP-{YEAR}-\d{{6}}$",
    "movement_id": rf"^MOV-{YEAR}-\d{{6}}$",
    "refund_id": rf"^REF-{YEAR}-\d{{6}}$",
    "refund_line_id": rf"^REFL-REF-{YEAR}-\d{{6}}-\d{{2}}$",
    "event_id": r"^EVT-\d{9}$",
}


def customer_id(n): return f"CUST-{n:06d}"
def product_id(n): return f"SKU-{n:06d}"
def policy_id(cat, v): return f"POL-{cat}-V{v}"
def order_id(n): return f"ORD-{YEAR}-{n:06d}"
def order_line_id(oid, k): return f"ORDL-{oid}-{k:02d}"
def rma_id(n): return f"RMA-{YEAR}-{n:06d}"
def rma_line_id(rma, k): return f"RMAL-{rma}-{k:02d}"
def auth_id(n): return f"AUTH-{YEAR}-{n:06d}"
def rts_id(n): return f"RTS-{YEAR}-{n:06d}"
def rts_line_id(rts, k): return f"RTSL-{rts}-{k:02d}"
def insp_id(n): return f"INSP-{YEAR}-{n:06d}"
def disp_id(n): return f"DISP-{YEAR}-{n:06d}"
def mov_id(n): return f"MOV-{YEAR}-{n:06d}"
def ref_id(n): return f"REF-{YEAR}-{n:06d}"
def ref_line_id(ref, k): return f"REFL-{ref}-{k:02d}"
def event_id(n): return f"EVT-{n:09d}"


class Counter:
    """Monotonic per-entity counters; IDs are allocated in generator processing order and never reused."""

    def __init__(self):
        self.n: dict[str, int] = {}

    def next(self, key: str) -> int:
        self.n[key] = self.n.get(key, 0) + 1
        return self.n[key]
