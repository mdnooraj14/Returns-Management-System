"""Phase 5: independent SQL validator. Loads the exported CSVs into SQLite and runs structural checks (derived from the
schema metadata) plus sql/validation_checks.sql. Business checks must match ground truth exactly; all others must be zero."""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

from . import schema
from .config import SNAPSHOT_DATE
from .ids import PATTERNS

ROOT = Path(__file__).resolve().parent.parent
CHECK_FILE = ROOT / "sql" / "validation_checks.sql"
DATE_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
TS_GLOB = DATE_GLOB + "T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]"


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.create_function("regexp", 2, lambda pat, s: 1 if s is not None and re.search(pat, s) else 0)
    return con


def read_csv(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r)
        for row in r:
            yield [None if v == "" else v for v in row]


def load_relaxed(data_dir: Path) -> sqlite3.Connection:
    """Constraint-free copy, so broken data is *reported* by queries instead of rejected at load."""
    con = _connect()
    for t in schema.TABLES:
        con.execute(f"CREATE TABLE {t.name} (" + ", ".join(f"{c.name} {schema.SQL_TYPE[c.type]}" for c in t.cols) + ")")
        q = f"INSERT INTO {t.name} VALUES ({','.join('?' * len(t.cols))})"
        con.executemany(q, read_csv(data_dir / f"{t.name}.csv"))
    con.commit()
    return con


def strict_load(data_dir: Path) -> str | None:
    con = _connect()
    try:
        con.executescript(schema.sql_ddl())
        for t in schema.TABLES:
            con.executemany(f"INSERT INTO {t.name} VALUES ({','.join('?' * len(t.cols))})", read_csv(data_dir / f"{t.name}.csv"))
        con.commit()
        return None
    except sqlite3.Error as e:
        return str(e)


def structural_checks() -> list[dict]:
    out = []

    def add(cid, desc, sql):
        out.append(dict(id=cid, layer="structural", expect="zero", desc=desc, sql=sql))

    for t in schema.TABLES:
        add(f"PK_{t.name}", f"{t.name}.{t.pk} unique and not null", f"SELECT {t.pk} AS entity_id FROM {t.name} GROUP BY {t.pk} HAVING COUNT(*) > 1 OR {t.pk} IS NULL")
        for u in t.uniques:
            cols = ", ".join(u)
            add(f"UQ_{t.name}_{'_'.join(u)}", f"{t.name} unique ({cols})", f"SELECT {u[0]} AS entity_id FROM {t.name} GROUP BY {cols} HAVING COUNT(*) > 1")
        for c in t.cols:
            n = f"{t.name}.{c.name}"
            if c.required:
                add(f"NN_{t.name}_{c.name}", f"{n} not null", f"SELECT {t.pk} AS entity_id FROM {t.name} WHERE {c.name} IS NULL")
            if c.unique and c.name != t.pk:
                add(f"UQ_{t.name}_{c.name}", f"{n} unique", f"SELECT {c.name} AS entity_id FROM {t.name} WHERE {c.name} IS NOT NULL GROUP BY {c.name} HAVING COUNT(*) > 1")
            if c.name in PATTERNS:
                add(f"ID_{t.name}_{c.name}", f"{n} matches ID format", f"SELECT {t.pk} AS entity_id FROM {t.name} WHERE {c.name} IS NOT NULL AND NOT regexp('{PATTERNS[c.name]}', {c.name})")
            if c.fk:
                pt, pc = c.fk.split(".")
                add(f"FK_{t.name}_{c.name}", f"{n} -> {c.fk}", f"SELECT c.{t.pk} AS entity_id FROM {t.name} c LEFT JOIN {pt} p ON p.{pc} = c.{c.name} WHERE c.{c.name} IS NOT NULL AND p.{pc} IS NULL")
            if c.allowed:
                vals = ", ".join("'" + a + "'" for a in c.allowed)
                add(f"EN_{t.name}_{c.name}", f"{n} in allowed enum", f"SELECT {t.pk} AS entity_id FROM {t.name} WHERE {c.name} IS NOT NULL AND {c.name} NOT IN ({vals})")
            if c.type == "bool":
                add(f"BL_{t.name}_{c.name}", f"{n} is 0/1", f"SELECT {t.pk} AS entity_id FROM {t.name} WHERE {c.name} IS NOT NULL AND {c.name} NOT IN (0, 1)")
            if c.type in ("int", "cents"):
                mn = c.minv if c.minv is not None else (0 if c.type == "cents" else None)
                add(f"TY_{t.name}_{c.name}", f"{n} integer" + (f" >= {mn}" if mn is not None else ""),
                    f"SELECT {t.pk} AS entity_id FROM {t.name} WHERE {c.name} IS NOT NULL AND (typeof({c.name}) <> 'integer'" + (f" OR {c.name} < {mn}" if mn is not None else "") + ")")
            if c.type == "date":
                add(f"DT_{t.name}_{c.name}", f"{n} ISO date", f"SELECT {t.pk} AS entity_id FROM {t.name} WHERE {c.name} IS NOT NULL AND {c.name} NOT GLOB '{DATE_GLOB}'")
            if c.type == "ts":
                add(f"TS_{t.name}_{c.name}", f"{n} ISO timestamp", f"SELECT {t.pk} AS entity_id FROM {t.name} WHERE {c.name} IS NOT NULL AND {c.name} NOT GLOB '{TS_GLOB}'")
    return out


def parse_check_file(path: Path = CHECK_FILE) -> list[dict]:
    checks, cur = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("-- check:"):
            if cur:
                checks.append(cur)
            parts = [x.strip() for x in line[len("-- check:"):].split("|")]
            cur = dict(id=parts[0], layer=parts[1], expect=parts[2].split("=", 1)[1], desc=parts[3], sql="")
        elif cur is not None and not line.startswith("--"):
            cur["sql"] += line + "\n"
    if cur:
        checks.append(cur)
    for c in checks:
        c["sql"] = c["sql"].strip().rstrip(";")
    return checks


def load_gt(dataset_dir: Path) -> dict[str, set[str]]:
    gt: dict[str, set[str]] = {}
    for row in csv.DictReader(open(dataset_dir / "ground_truth" / "anomalies.csv", newline="", encoding="utf-8")):
        gt.setdefault(row["issue_type"], set()).add(row["entity_id"])
    return gt


def validate(dataset_dir: Path) -> dict:
    dataset_dir = Path(dataset_dir)
    con = load_relaxed(dataset_dir / "data")
    gt = load_gt(dataset_dir)
    results = []
    err = strict_load(dataset_dir / "data")
    results.append(dict(id="S00_STRICT_SCHEMA_LOAD", layer="structural", expect="zero", desc="all CSVs load into the constrained schema.sql (PK/FK/CHECK enforced)",
                        violations=0 if err is None else 1, status="PASS" if err is None else "FAIL", sample=[] if err is None else [err]))
    for c in structural_checks() + parse_check_file():
        rows = [r[0] for r in con.execute(c["sql"]).fetchall()]
        got = set(rows)
        res = dict(id=c["id"], layer=c["layer"], expect=c["expect"], desc=c["desc"], violations=len(got))
        if c["expect"].startswith("gt:"):
            exp = gt.get(c["expect"][3:], set())
            res.update(expected_in_ground_truth=len(exp), true_positive=len(got & exp), false_positive=len(got - exp), false_negative=len(exp - got))
            res["status"] = "PASS" if got == exp else "FAIL"
        else:
            res["status"] = "PASS" if not got else "FAIL"
        res["sample"] = sorted(got)[:5] if res["status"] == "FAIL" or c["expect"].startswith("gt:") else []
        results.append(res)
    layers = {}
    for r in results:
        l = layers.setdefault(r["layer"], dict(checks=0, passed=0))
        l["checks"] += 1
        l["passed"] += r["status"] == "PASS"
    rows = {t.name: con.execute(f"SELECT COUNT(*) FROM {t.name}").fetchone()[0] for t in schema.TABLES}
    summary = dict(dataset=str(dataset_dir.name), snapshot_date=SNAPSHOT_DATE.isoformat(), row_counts=rows, layers=layers,
                   total_checks=len(results), passed=sum(r["status"] == "PASS" for r in results),
                   failed=[r["id"] for r in results if r["status"] == "FAIL"], overall="PASS" if all(r["status"] == "PASS" for r in results) else "FAIL")
    report = dict(summary=summary, checks=results)
    rep = dataset_dir / "reports"
    rep.mkdir(exist_ok=True)
    (rep / "validation_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    (rep / "validation_summary.md").write_text(to_markdown(report), encoding="utf-8", newline="\n")
    return report


def to_markdown(rep: dict) -> str:
    s = rep["summary"]
    o = [f"# Validation summary ({s['dataset']})", "", f"**Overall: {s['overall']}** - {s['passed']}/{s['total_checks']} checks passed.", "",
         "| Layer | Checks | Passed |", "|---|---|---|"]
    o += [f"| {k} | {v['checks']} | {v['passed']} |" for k, v in s["layers"].items()]
    o += ["", "## Business checks vs ground truth (must match exactly)", "",
          "| Check | Description | Flagged | In ground truth | TP | FP | FN | Status |", "|---|---|---|---|---|---|---|---|"]
    for r in rep["checks"]:
        if r["expect"].startswith("gt:"):
            o.append(f"| {r['id']} | {r['desc']} | {r['violations']} | {r['expected_in_ground_truth']} | {r['true_positive']} | {r['false_positive']} | {r['false_negative']} | {r['status']} |")
    o += ["", "## Invariant checks (must be zero)", "", "| Check | Description | Violations | Status |", "|---|---|---|---|"]
    for r in rep["checks"]:
        if r["layer"] == "invariant" and not r["expect"].startswith("gt:"):
            o.append(f"| {r['id']} | {r['desc']} | {r['violations']} | {r['status']} |")
    o += ["", f"Structural checks (PK/NOT NULL/unique/ID format/FK/enum/type/date format): {s['layers'].get('structural', {}).get('checks', 0)} generated from the schema, "
          f"{s['layers'].get('structural', {}).get('passed', 0)} passed.", "", "Row counts: " + ", ".join(f"{k}={v}" for k, v in s["row_counts"].items())]
    if s["failed"]:
        o += ["", "## Failed", ", ".join(s["failed"])]
    return "\n".join(o) + "\n"
