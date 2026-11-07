import pandas as pd
import pytest

from rma import config as C
from rma import detect, export, generate, metrics


@pytest.fixture(scope="module")
def ds(tmp_path_factory):
    d = tmp_path_factory.mktemp("det")
    export.write_dataset(generate.generate(C.Params(scale=0.2)), d)
    return d


def test_detector_matches_ground_truth_with_no_unlabelled_flags(ds):
    det = detect.run(ds)
    m = metrics.detection(ds, det)
    for t in C.ISSUE_TYPES:
        assert m[t]["fp"] == 0 and m[t]["fn"] == 0 and m[t]["labelled"] > 0, (t, m[t])
    assert m["_unlabelled_flags"] == {}


def test_detector_does_not_read_ground_truth_dir(ds, monkeypatch):
    seen = []
    orig = pd.read_csv
    monkeypatch.setattr(pd, "read_csv", lambda p, *a, **k: (seen.append(str(p)), orig(p, *a, **k))[1])
    detect.run(ds)
    assert seen and not any("ground_truth" in s for s in seen)


def test_metrics_compute_and_reconcile(ds):
    res = metrics.compute(ds, detect.run(ds))
    assert res["controls"]["duplicate_block_rate"] < 1.0 and res["controls"]["duplicates_blocked"] > 0
    assert res["controls"]["refund_header_reconciliation_rate"] == 1.0
    assert res["decision_accuracy"]["eligibility_mismatches"] > 0  # exactly the injected decision anomalies
    assert (ds / "reports" / "metrics.md").exists()
