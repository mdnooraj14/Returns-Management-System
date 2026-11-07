import shutil

import pandas as pd
import pytest

from rma import config as C
from rma import export, generate, validate


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    d = tmp_path_factory.mktemp("clean")
    export.write_dataset(generate.generate(C.Params(scale=0.05)), d)
    return d


def test_clean_dataset_passes_everything(clean):
    rep = validate.validate(clean)
    assert rep["summary"]["overall"] == "PASS", rep["summary"]["failed"]
    assert rep["summary"]["layers"]["business"]["checks"] == 6


def _mutate(clean, tmp_path, table, fn):
    d = tmp_path / "m"
    shutil.copytree(clean, d)
    p = d / "data" / f"{table}.csv"
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    fn(df)
    df.to_csv(p, index=False, lineterminator="\n")
    return validate.validate(d)["summary"]["failed"]


def test_detects_broken_order_total(clean, tmp_path):
    def f(df): df.loc[0, "total_cents"] = str(int(df.loc[0, "total_cents"]) + 1)
    assert "A03" in _mutate(clean, tmp_path, "orders", f)


def test_detects_duplicate_pk(clean, tmp_path):
    def f(df): df.loc[1, "customer_id"] = df.loc[0, "customer_id"]
    failed = _mutate(clean, tmp_path, "customer", f)
    assert "PK_customer" in failed and "S00_STRICT_SCHEMA_LOAD" in failed


def test_detects_orphan_fk(clean, tmp_path):
    def f(df): df.loc[0, "product_id"] = "SKU-999999"
    assert "FK_order_line_product_id" in _mutate(clean, tmp_path, "order_line", f)


def test_detects_bad_enum(clean, tmp_path):
    def f(df): df.loc[0, "grade"] = "Z"
    assert "EN_inspection_grade" in _mutate(clean, tmp_path, "inspection", f)


def test_detects_invalid_transition_and_broken_history(clean, tmp_path):
    def f(df):
        i = df.index[df.to_state == "INSPECTED"][0]
        df.loc[i, "to_state"] = "CLOSED"
    failed = _mutate(clean, tmp_path, "state_event", f)
    assert "L01" in failed and "L02" in failed


def test_detects_status_not_matching_last_event(clean, tmp_path):
    def f(df):
        i = df.index[df.status == "CLOSED"][0]
        df.loc[i, "status"] = "SUBMITTED"
    assert "L03" in _mutate(clean, tmp_path, "return_request", f)


def test_detects_refund_before_inspection(clean, tmp_path):
    def f(df): df.loc[0, "refund_date"] = "2026-01-01"
    assert "D09" in _mutate(clean, tmp_path, "refund", f)


def test_detects_refund_formula_break(clean, tmp_path):
    def f(df): df.loc[0, "restocking_fee_cents"] = str(int(df.loc[0, "restocking_fee_cents"]) + 5)
    failed = _mutate(clean, tmp_path, "refund_line", f)
    assert "A05" in failed


def test_detects_disposition_not_following_grade(clean, tmp_path):
    def f(df):
        i = df.index[df.disposition == "RESTOCK"][0]
        df.loc[i, "disposition"] = "SCRAP"
    assert "B10" in _mutate(clean, tmp_path, "inventory_disposition", f)


def test_unlabelled_duplicate_payout_is_a_false_positive(clean, tmp_path):
    def f(df):
        i = df.index[(df.status == "ISSUED") & (df.attempt_no == "1")][0]
        row = df.loc[i].copy()
        row["refund_id"], row["attempt_no"] = "REF-2026-999999", "2"
        df.loc[len(df)] = row
    failed = _mutate(clean, tmp_path, "refund", f)
    assert "B05" in failed
