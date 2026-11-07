"""Command line: generate | validate | detect | reproduce | all.   python -m rma.cli all --scale 1 --out output/full"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import config as C
from . import export, generate, validate


def cmd_generate(a):
    t = time.time()
    res = generate.generate(C.Params(seed=a.seed, scale=a.scale))
    m = export.write_dataset(res, Path(a.out))
    print(f"generated {sum(m['row_counts'].values())} rows in {time.time() - t:.1f}s -> {a.out}")
    return res


def cmd_validate(a):
    rep = validate.validate(Path(a.out))
    s = rep["summary"]
    print(f"validation {s['overall']}: {s['passed']}/{s['total_checks']} checks; failed={s['failed']}")
    return rep


def cmd_detect(a):
    from . import detect, metrics
    out = Path(a.out)
    det = detect.run(out)
    m = metrics.compute(out, det)
    print(json.dumps({k: v for k, v in m["detection"].items()}, indent=1)[:1500])
    return m


def cmd_reproduce(a):
    from . import reproduce
    rep = reproduce.run(a.seed, a.scale, Path(a.out))
    print(f"reproducibility: {rep['verdict']}")
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rma")
    ap.add_argument("command", choices=["generate", "validate", "detect", "reproduce", "all"])
    ap.add_argument("--seed", type=int, default=C.SEED)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--out", default="output/full")
    a = ap.parse_args(argv)
    if a.command in ("generate", "all"):
        cmd_generate(a)
    if a.command in ("validate", "all"):
        cmd_validate(a)
    if a.command in ("detect", "all"):
        cmd_detect(a)
    if a.command == "reproduce":
        cmd_reproduce(a)


if __name__ == "__main__":
    main()
