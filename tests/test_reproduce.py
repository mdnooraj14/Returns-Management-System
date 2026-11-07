from rma import config as C
from rma import export, generate, reproduce


def test_same_seed_identical_files_across_processes(tmp_path):
    d = tmp_path / "pub"
    export.write_dataset(generate.generate(C.Params(scale=0.02)), d)
    rep = reproduce.run(C.SEED, 0.02, d)
    assert rep["verdict"] == "REPRODUCIBLE"
    assert rep["run_a_vs_run_b"]["files_identical"] == rep["run_a_vs_run_b"]["files_compared"] > 30
    assert rep["different_seed_changes_output"]
