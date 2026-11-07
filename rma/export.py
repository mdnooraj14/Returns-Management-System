"""Exports: CSV, JSON, SQL seed, ground truth (separate folder), manifest with checksums."""
from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import schema

ROOT = Path(__file__).resolve().parent.parent
GT_FILES = {"anomalies": "anomalies", "decisions": "decisions", "scenarios": "scenario_labels"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sql_literal(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
        return "NULL"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return "'" + str(v).replace("'", "''") + "'"


def df_rows(df: pd.DataFrame):
    o = df.astype(object).where(df.notna(), None)
    return list(o.itertuples(index=False, name=None))


def write_seed_sql(tables: dict[str, pd.DataFrame], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("-- Seed data (SQLite). Schema first, then parents before children.\n")
        f.write(schema.sql_ddl().replace("PRAGMA foreign_keys = ON;", "PRAGMA foreign_keys = OFF;") + "\nBEGIN;\n")
        for t in schema.TABLES:
            df = tables[t.name]
            cols = ", ".join(t.colnames)
            rows = df_rows(df)
            for i in range(0, len(rows), 500):
                vals = ",\n".join("(" + ", ".join(sql_literal(v) for v in r) + ")" for r in rows[i:i + 500])
                f.write(f"INSERT INTO {t.name} ({cols}) VALUES\n{vals};\n")
        f.write("COMMIT;\nPRAGMA foreign_keys = ON;\n")


def write_dataset(result: dict, out: Path) -> dict:
    out = Path(out)
    for sub in ("data", "json", "sql", "ground_truth", "reports"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    tables, gt = result["tables"], result["ground_truth"]
    for name, df in tables.items():
        df.to_csv(out / "data" / f"{name}.csv", index=False, lineterminator="\n")
        df.to_json(out / "json" / f"{name}.json", orient="records")
    write_seed_sql(tables, out / "sql" / "seed.sql")
    (out / "sql" / "schema.sql").write_text(schema.sql_ddl(), encoding="utf-8", newline="\n")
    for key, fname in GT_FILES.items():
        gt[key].to_csv(out / "ground_truth" / f"{fname}.csv", index=False, lineterminator="\n")
        gt[key].to_json(out / "ground_truth" / f"{fname}.json", orient="records")
    return build_manifest(result, out)


def build_manifest(result: dict, out: Path) -> dict:
    p = result["params"]
    files = {}
    for f in sorted(out.rglob("*")):
        if f.is_file() and f.parent.name != "reports" and f.name != "manifest.json" and f.suffix != ".sqlite":
            files[f.relative_to(out).as_posix()] = {"sha256": sha256(f), "bytes": f.stat().st_size}
    manifest = {
        "project": "RMA returns synthetic dataset",
        "generator_command": f"python -m rma.cli generate --seed {p.seed} --scale {p.scale} --out <dir>",
        "seed": p.seed, "scale": p.scale, "snapshot_date": C.SNAPSHOT_DATE.isoformat(),
        "row_counts": {k: int(len(v)) for k, v in result["tables"].items()},
        "ground_truth_row_counts": {k: int(len(v)) for k, v in result["ground_truth"].items()},
        "environment": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
        "external_data": {"used": False, "sources": [], "licence_notes": "No external or public data used. All records are synthetic; "
                          "emails use the reserved example.com domain; no personal information was collected."},
        "files": files,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return manifest
