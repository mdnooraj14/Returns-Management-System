import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "dashboard" / "app.py")
pytestmark = pytest.mark.skipif(not (Path(APP).parent.parent / "output" / "starter" / "data").exists(), reason="dataset not generated")
LEAKS = ("DeltaGenerator", "st.dataframe", "hide_index", "Display a dataframe", "streamlit.delta_generator")


def _texts(at):
    """Every piece of text Streamlit rendered, across all element types."""
    out = []
    for coll in (at.markdown, at.caption, at.text, at.code, at.subheader, at.header, at.title, at.warning, at.info, at.success, at.error):
        out += [str(getattr(e, "value", "")) for e in coll]
    return out


def _assert_clean(at):
    assert not at.exception, [e.value for e in at.exception]
    bad = [t[:120] for t in _texts(at) if any(k in t for k in LEAKS)]
    assert not bad, bad


def test_no_bare_non_call_expression_statements():
    """Streamlit 'magic' st.write()s any bare expression that is not a plain call, e.g. `st.dataframe(..) if x else st.caption(..)`,
    which prints the DeltaGenerator repr and its method docs into the page."""
    tree = ast.parse(Path(APP).read_text(encoding="utf-8"))
    bad = [(n.lineno, type(n.value).__name__) for n in ast.walk(tree)
           if isinstance(n, ast.Expr) and not isinstance(n.value, (ast.Call, ast.Constant))]
    assert not bad, f"magic-rendered expression statements at {bad}"


def test_dashboard_renders_without_exceptions():
    at = AppTest.from_file(APP, default_timeout=120).run()
    _assert_clean(at)
    assert len(at.tabs) == 6 and len(at.metric) >= 5


def test_trace_tab_clean_for_populated_and_sparse_requests():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("starter").run()
    _assert_clean(at)
    box = next(s for s in at.selectbox if s.label == "Return request")
    ids_ = list(box.options)
    for rid in (ids_[9], ids_[0], ids_[len(ids_) // 2], ids_[-1]):  # populated chains and rejected/pending ones with empty tables
        next(s for s in at.selectbox if s.label == "Return request").select(rid).run()
        _assert_clean(at)
        assert any(rid in t for t in _texts(at))
    assert len(at.dataframe) >= 5


def test_every_trace_table_is_a_real_dataframe():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("starter").run()
    next(s for s in at.selectbox if s.label == "Return request").select("RMA-2026-000010").run()
    titles = [t for t in _texts(at) if t.startswith("##### ")]
    for need in ("Authorization", "Shipments", "Shipment lines", "Inspections", "Dispositions", "Inventory movements",
                 "Refund attempts", "Refund lines", "Event history"):
        assert any(need in t for t in titles), need
    assert len(at.dataframe) >= 5
    _assert_clean(at)
