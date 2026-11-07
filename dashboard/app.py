"""RMA dashboard: overview, decisions, exceptions, end-to-end traceability, financials, data quality.
Run: streamlit run dashboard/app.py"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"
FIXED = {  # color follows the entity, never its rank
    "RESTOCK": BLUE, "REFURBISH": ORANGE, "SCRAP": VIOLET, "QUARANTINE": MAGENTA,
    "ELIGIBLE": BLUE, "LATE_OVERRIDE": ORANGE, "FINAL_SALE_CATEGORY": AQUA, "LATE_REQUEST": YELLOW,
    "OPENED_NOT_RETURNABLE": MAGENTA, "QTY_EXHAUSTED": VIOLET}
ISSUE_COLOR = {"QTY_EXCEEDS_PURCHASED": BLUE, "REFUND_EXCEEDS_PAID": ORANGE, "RESTOCK_BEFORE_INSPECTION": AQUA,
               "LATE_NO_OVERRIDE": YELLOW, "DUPLICATE_REFUND": MAGENTA}
STATE_ORDER = ["SUBMITTED", "REJECTED", "AUTHORIZED", "EXPIRED", "SHIPPED", "CLAIM_OPENED", "RECEIVED", "INSPECTED", "REFUNDED", "CLOSED"]

st.set_page_config(page_title="RMA Returns Dashboard", layout="wide")


def style(fig, h=340):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=-0.2), title_font_size=15)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,.25)")
    return fig


datasets = [d.name for d in sorted(OUT.glob("*")) if (d / "data").exists()] if OUT.exists() else []
if not datasets:
    st.error("No dataset found. Run: python -m rma.cli all --scale 1 --out output/full")
    st.stop()
ds = st.sidebar.selectbox("Dataset", datasets, index=datasets.index("full") if "full" in datasets else 0)
base = OUT / ds


@st.cache_data
def load(name: str):
    b = OUT / name
    T = {p.stem: pd.read_csv(p) for p in (b / "data").glob("*.csv")}
    rep = {}
    for k in ("validation_summary", "metrics", "reproducibility"):
        f = b / "reports" / f"{k}.json"
        rep[k] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    det = pd.read_csv(b / "reports" / "detections.csv") if (b / "reports" / "detections.csv").exists() else pd.DataFrame()
    gt = pd.read_csv(b / "ground_truth" / "anomalies.csv") if (b / "ground_truth" / "anomalies.csv").exists() else pd.DataFrame()
    return T, rep, det, gt


T, rep, det, gt = load(ds)
m = rep["metrics"]
st.title("Returns management (RMA)")
st.caption(f"Dataset **{ds}** - snapshot 2026-10-22 - all data synthetic")
tabs = st.tabs(["Overview", "Decisions", "Exceptions", "Trace an RMA", "Financials", "Data quality"])

# ------------------------------------------------------------------ overview
with tabs[0]:
    rq, rl = T["return_request"], T["return_line"]
    if m:
        o, f, c = m["operational"], m["financial"], m["controls"]
        k = st.columns(3) + st.columns(2)
        k[0].metric("Return requests", f"{o['return_requests']:,}", f"{o['request_rate_per_delivered_order']:.1%} of delivered orders")
        k[1].metric("Line approval rate", f"{o['line_approval_rate']:.1%}")
        k[2].metric("Refunded", f"${f['refunded_cents'] / 100:,.0f}", f"{f['refund_pct_of_delivered_revenue']:.1%} of revenue")
        k[3].metric("Duplicate attempts blocked", f"{c['duplicates_blocked']} / {c['duplicate_attempts']}")
        k[4].metric("Median request-to-refund", f"{o['cycle_days']['request_to_refund']['median']:.0f} days")
    cnt = rq.status.value_counts().reindex(STATE_ORDER).dropna().reset_index()
    cnt.columns = ["status", "requests"]
    st.plotly_chart(style(px.bar(cnt, x="status", y="requests", title="Requests by current lifecycle state", color_discrete_sequence=[BLUE])), width='stretch')
    if m:
        cy = pd.DataFrame(m["operational"]["cycle_days"]).T.reset_index().rename(columns={"index": "stage"})
        fig = go.Figure()
        fig.add_bar(x=cy.stage, y=cy["median"], name="median days", marker_color=BLUE)
        fig.add_bar(x=cy.stage, y=cy["p90"], name="p90 days", marker_color=ORANGE)
        fig.update_layout(barmode="group", title="Stage cycle time (days)")
        st.plotly_chart(style(fig), width='stretch')
    with st.expander("Table view"):
        st.dataframe(cnt, hide_index=True)

# ------------------------------------------------------------------ decisions
with tabs[1]:
    d = rl[rl.line_decision != "PENDING"].merge(T["order_line"][["order_line_id", "category"]], on="order_line_id")
    g = d.groupby(["category", "decision_reason"]).size().reset_index(name="lines")
    fig = px.bar(g, x="category", y="lines", color="decision_reason", color_discrete_map=FIXED, title="Eligibility decisions by category and reason")
    fig.update_traces(marker_line_color="rgba(0,0,0,0)", marker_line_width=2)
    st.plotly_chart(style(fig, 380), width='stretch')
    ap = d.assign(approved=d.qty_approved > 0).groupby("category").approved.mean().reset_index()
    st.plotly_chart(style(px.bar(ap, x="category", y="approved", title="Approval rate by category", color_discrete_sequence=[BLUE]).update_yaxes(tickformat=".0%")), width='stretch')
    pol = T["return_policy"][["policy_id", "category", "window_days", "defect_extension_days", "final_sale", "requires_unopened", "restocking_fee_bps_opened", "effective_from", "effective_to"]]
    st.subheader("Policy in force")
    st.dataframe(pol, hide_index=True, width='stretch')

# ------------------------------------------------------------------ exceptions
with tabs[2]:
    st.caption("Flags come from replaying the rules engine on the stored data. Ground truth is used only in the evaluation section below.")
    if det.empty:
        st.info("Run `python -m rma.cli detect --out output/" + ds + "` to produce detections.")
    else:
        sel = st.multiselect("Issue types", sorted(det.issue_type.unique()), default=sorted(det.issue_type.unique()))
        q = det[det.issue_type.isin(sel)]
        cc = q.issue_type.value_counts().reset_index()
        cc.columns = ["issue_type", "flags"]
        st.plotly_chart(style(px.bar(cc, x="issue_type", y="flags", color="issue_type", color_discrete_map=ISSUE_COLOR, title="Flagged records"), 300), width='stretch')
        st.dataframe(q, hide_index=True, width='stretch')
        st.subheader("Evaluation against ground truth (not an input to detection)")
        if m:
            ev = pd.DataFrame(m["detection"]).drop(columns=["_unlabelled_flags"], errors="ignore").T.reset_index().rename(columns={"index": "issue_type"})
            st.dataframe(ev[ev.issue_type.isin(list(ISSUE_COLOR) + ["_overall"])], hide_index=True, width='stretch')
            st.caption("Perfect scores reflect rule consistency: the detector re-applies the same rules that generated the data.")

# ------------------------------------------------------------------ trace
with tabs[3]:
    ids_ = T["return_request"].return_request_id.tolist()
    flagged = det.merge(T["return_line"][["return_line_id", "return_request_id"]], left_on="entity_id", right_on="return_line_id", how="left") if not det.empty else det
    c1, c2 = st.columns([1, 2])
    pick = c1.selectbox("Return request", ids_, index=min(100, len(ids_) - 1))
    typed = c2.text_input("...or type an ID (RMA-2026-000123)")
    rid = typed.strip() if typed.strip() in ids_ else pick
    R = T["return_request"].query("return_request_id == @rid").iloc[0]
    L = T["return_line"].query("return_request_id == @rid")
    o = T["orders"].query("order_id == @R.order_id").iloc[0]
    st.markdown(f"**{rid}** - order `{R.order_id}` ({o.order_date} -> delivered {o.delivery_date}) - customer `{R.customer_id}` - **{R.status}** - {R.resolution_requested}")
    st.markdown("##### Return lines and decisions")
    st.dataframe(L.merge(T["order_line"][["order_line_id", "category", "quantity", "paid_cents"]], on="order_line_id"), hide_index=True, width='stretch')
    A = T["return_authorization"].query("return_request_id == @rid")
    S = T["return_shipment"].merge(A[["authorization_id"]], on="authorization_id")
    SL = T["shipment_line"][T["shipment_line"].shipment_id.isin(S.shipment_id)]
    I = T["inspection"][T["inspection"].return_line_id.isin(L.return_line_id)]
    D = T["inventory_disposition"][T["inventory_disposition"].return_line_id.isin(L.return_line_id)]
    M = T["inventory_movement"][T["inventory_movement"].return_line_id.isin(L.return_line_id)]
    F = T["refund"].query("return_request_id == @rid")
    FL = T["refund_line"][T["refund_line"].refund_id.isin(F.refund_id)]
    for title, df in (("Authorization", A), ("Shipments", S), ("Shipment lines", SL), ("Inspections", I), ("Dispositions", D), ("Inventory movements", M), ("Refund attempts", F), ("Refund lines", FL)):
        st.markdown(f"##### {title}")
        if len(df):
            st.dataframe(df, hide_index=True, width='stretch')
        else:
            st.caption("none")
    ents = [rid] + S.shipment_id.tolist() + F.refund_id.tolist()
    E = T["state_event"][T["state_event"].entity_id.isin(ents)].sort_values("event_ts")
    st.markdown("##### Event history (append-only)")
    E = E.assign(ts=pd.to_datetime(E.event_ts))
    fig = px.scatter(E, x="ts", y="entity_id", color="entity_type", text="to_state", color_discrete_sequence=[BLUE, ORANGE, AQUA], title="Lifecycle events")
    fig.update_traces(textposition="top center", marker=dict(size=10, line=dict(width=2, color="rgba(0,0,0,0)")))
    st.plotly_chart(style(fig, 320), width='stretch')
    st.dataframe(E.drop(columns="ts"), hide_index=True, width='stretch')
    if not det.empty:
        hit = det[det.entity_id.isin(set(L.return_line_id) | set(F.refund_id) | set(D.disposition_id))]
        if len(hit):
            st.warning("Rules replay flagged this RMA")
            st.dataframe(hit, hide_index=True, width='stretch')

# ------------------------------------------------------------------ financials
with tabs[4]:
    rf = T["refund"]
    iss = rf[(rf.status == "ISSUED") & (rf.attempt_no == 1)].assign(month=lambda x: x.refund_date.str[:7])
    mo = iss.groupby("month").paid_cents.sum().div(100).reset_index()
    st.plotly_chart(style(px.bar(mo, x="month", y="paid_cents", title="Refunds paid per month (USD)", color_discrete_sequence=[BLUE])), width='stretch')
    rl_ = T["refund_line"]
    fees = pd.DataFrame({"component": ["Restocking fees", "Condition deductions", "Return shipping fees"],
                         "usd": [rl_.restocking_fee_cents.sum() / 100, rl_.condition_deduction_cents.sum() / 100, iss.return_shipping_fee_cents.sum() / 100]})
    st.plotly_chart(style(px.bar(fees, x="component", y="usd", title="Amounts retained from refunds (USD)", color_discrete_sequence=[ORANGE])), width='stretch')
    dd = T["inventory_disposition"].groupby("disposition").agg(lines=("qty", "size"), units=("qty", "sum"), recovery=("est_recovery_cents", "sum")).reset_index()
    dd["recovery"] /= 100
    c1, c2 = st.columns(2)
    c1.plotly_chart(style(px.bar(dd, x="disposition", y="units", color="disposition", color_discrete_map=FIXED, title="Units by disposition")), width='stretch')
    c2.plotly_chart(style(px.bar(dd, x="disposition", y="recovery", color="disposition", color_discrete_map=FIXED, title="Estimated recovery (USD)")), width='stretch')
    if m:
        f = m["financial"]
        st.info(f"Exposure in this data: over-refund ${f['refund_exposure_over_paid_cents'] / 100:,.2f}; duplicate payouts that slipped through ${f['duplicate_payout_leak_cents'] / 100:,.2f}.")

# ------------------------------------------------------------------ data quality
with tabs[5]:
    v = rep["validation_summary"]
    if v:
        s = v["summary"]
        st.metric("SQL validation", s["overall"], f"{s['passed']}/{s['total_checks']} checks")
        st.dataframe(pd.DataFrame(s["layers"]).T, width='stretch')
        biz = pd.DataFrame([c for c in v["checks"] if c["expect"].startswith("gt:")])
        st.markdown("##### Business checks vs ground truth")
        st.dataframe(biz[["id", "desc", "violations", "expected_in_ground_truth", "true_positive", "false_positive", "false_negative", "status"]], hide_index=True, width='stretch')
        st.markdown("##### All checks")
        st.dataframe(pd.DataFrame(v["checks"])[["id", "layer", "desc", "violations", "status"]], hide_index=True, width='stretch')
    r = rep["reproducibility"]
    if r:
        st.metric("Reproducibility", r["verdict"], f"{r['run_a_vs_run_b']['files_identical']}/{r['run_a_vs_run_b']['files_compared']} files identical across runs")
    mf = base / "manifest.json"
    if mf.exists():
        st.json({k: val for k, val in json.loads(mf.read_text(encoding="utf-8")).items() if k != "files"}, expanded=False)
