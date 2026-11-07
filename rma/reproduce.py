"""Phase 8: regenerate twice with the same seed (separate processes, different PYTHONHASHSEED) and compare row counts + SHA-256
of every exported file; also compare with the published dataset, and show a different seed changes the output."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _gen(seed: int, scale: float, out: Path, hashseed: str) -> dict:
    env = dict(os.environ, PYTHONHASHSEED=hashseed)
    subprocess.run([sys.executable, "-m", "rma.cli", "generate", "--seed", str(seed), "--scale", str(scale), "--out", str(out)],
                   cwd=ROOT, env=env, check=True, capture_output=True)
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def _cmp(a: dict, b: dict) -> dict:
    fa, fb = a["files"], b["files"]
    diff = sorted(k for k in set(fa) | set(fb) if fa.get(k, {}).get("sha256") != fb.get(k, {}).get("sha256"))
    return dict(rows_equal=a["row_counts"] == b["row_counts"] and a["ground_truth_row_counts"] == b["ground_truth_row_counts"],
                files_compared=len(fa), files_identical=len(fa) - len(diff), differing_files=diff)


def run(seed: int, scale: float, dataset_dir: Path) -> dict:
    dataset_dir = Path(dataset_dir)
    tmp = dataset_dir.parent / f"_repro_{dataset_dir.name}"
    shutil.rmtree(tmp, ignore_errors=True)
    a = _gen(seed, scale, tmp / "run_a", "1")
    b = _gen(seed, scale, tmp / "run_b", "424242")
    c = _gen(seed + 1, scale, tmp / "run_other_seed", "1")
    published = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8")) if (dataset_dir / "manifest.json").exists() else None
    rep = dict(seed=seed, scale=scale, run_a_vs_run_b=_cmp(a, b), run_a_vs_published=_cmp(a, published) if published else None,
               different_seed_changes_output=_cmp(a, c)["files_identical"] < _cmp(a, c)["files_compared"],
               row_counts=a["row_counts"], checksums={k: v["sha256"] for k, v in a["files"].items()})
    ok = rep["run_a_vs_run_b"]["rows_equal"] and not rep["run_a_vs_run_b"]["differing_files"]
    ok = ok and (published is None or (rep["run_a_vs_published"]["rows_equal"] and not rep["run_a_vs_published"]["differing_files"]))
    rep["verdict"] = "REPRODUCIBLE" if ok and rep["different_seed_changes_output"] else "NOT REPRODUCIBLE"
    shutil.rmtree(tmp, ignore_errors=True)
    out = dataset_dir / "reports"
    out.mkdir(exist_ok=True)
    (out / "reproducibility.json").write_text(json.dumps(rep, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    (out / "reproducibility.md").write_text(to_markdown(rep), encoding="utf-8", newline="\n")
    return rep


def to_markdown(r: dict) -> str:
    ab, ap = r["run_a_vs_run_b"], r["run_a_vs_published"]
    L = [f"# Reproducibility ({r['verdict']})", "",
         f"Seed {r['seed']}, scale {r['scale']}. Run A and run B are separate processes with different `PYTHONHASHSEED` values.", "",
         "| Comparison | Row counts equal | Files compared | Identical | Differing |", "|---|---|---|---|---|",
         f"| run A vs run B | {ab['rows_equal']} | {ab['files_compared']} | {ab['files_identical']} | {len(ab['differing_files'])} |"]
    if ap:
        L.append(f"| run A vs published dataset | {ap['rows_equal']} | {ap['files_compared']} | {ap['files_identical']} | {len(ap['differing_files'])} |")
    L += ["", f"Control: a different seed changes the output: **{r['different_seed_changes_output']}**.", "",
          "## Row counts", "", "| Table | Rows |", "|---|---|"] + [f"| {k} | {v} |" for k, v in r["row_counts"].items()]
    L += ["", "## SHA-256 (run A)", "", "| File | SHA-256 |", "|---|---|"] + [f"| {k} | `{v}` |" for k, v in r["checksums"].items()]
    return "\n".join(L) + "\n"
