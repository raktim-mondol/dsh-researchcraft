"""Facts: derived or curated values with their computation (design 4.4).

A fact has variants (n, d, pct, ci, ...). Prose reaches them through \\fact{id.variant}, so a
value lives in one place. Facts are computed from data files declaratively (from_tsv), from
literals, or from other facts, never from prose.
"""
from __future__ import annotations

import ast
import csv
import math
import operator
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..project import Project
from ..util import sha256_file

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval in percent."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (100 * max(0.0, centre - half), 100 * min(1.0, centre + half))


def fmt(x: float, decimals: int) -> str:
    return f"{x:.{decimals}f}"


@dataclass
class Fact:
    id: str
    kind: str
    spec: dict
    decimals: int = 1
    variants: dict[str, dict[str, str]] = field(default_factory=dict)   # name -> {"plain", "tex"}
    numbers: dict[str, float] = field(default_factory=dict)             # name -> numeric value
    inputs: dict[str, str] = field(default_factory=dict)                # input file -> sha256
    superseded: list[dict] = field(default_factory=list)
    note: str = ""

    def default_variant(self) -> str:
        return self.spec.get("default") or {"value": "value", "count": "n", "proportion": "pct",
                                            "derived": "value"}[self.kind]


class FactError(Exception):
    pass


# ---------- TSV conditions ----------

def _cond_ok(cell: str, cond: Any) -> bool:
    cell = cell.strip()
    if isinstance(cond, list):
        return cell in [str(c) for c in cond]
    if isinstance(cond, dict):
        ok = True
        if "contains" in cond:
            ok &= str(cond["contains"]).lower() in cell.lower()
        if "not" in cond:
            ok &= cell != str(cond["not"])
        if "nonempty" in cond:
            ok &= bool(cell) == bool(cond["nonempty"])
        if "in" in cond:
            ok &= cell in [str(c) for c in cond["in"]]
        return ok
    return cell == str(cond)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _joined_rows(project: Project, spec: dict, inputs: dict[str, str]) -> list[dict[str, str]]:
    p = project.root / spec["file"]
    if not p.exists():
        raise FactError(f"data file not found: {spec['file']}")
    inputs[spec["file"]] = sha256_file(p)
    rows = read_tsv(p)
    for j in ([spec["join"]] if isinstance(spec.get("join"), dict) else spec.get("join") or []):
        jp = project.root / j["file"]
        if not jp.exists():
            raise FactError(f"join file not found: {j['file']}")
        inputs[j["file"]] = sha256_file(jp)
        key = j.get("on", j.get(True))          # YAML 1.1 reads an unquoted `on:` key as boolean True
        if key is None:
            raise FactError("join needs an 'on' column")
        other = {r[key]: r for r in read_tsv(jp)}
        for r in rows:
            for col, val in (other.get(r.get(key, ""), {}) or {}).items():
                r.setdefault(col, val)
    return rows


def _matches(r: dict, where: dict) -> bool:
    return all(_cond_ok(r.get(c, ""), cond) for c, cond in where.items())


def count_tsv(project: Project, spec: dict, inputs: dict[str, str], extra_where: dict | None = None) -> int:
    rows = _joined_rows(project, spec, inputs)
    where = dict(spec.get("where") or {})
    where.update(extra_where or {})
    for col in where:
        if rows and col not in rows[0]:
            raise FactError(f"column '{col}' not in {spec['file']}")
    any_of = spec.get("where_any") or []
    n = 0
    for r in rows:
        if _matches(r, where) and (not any_of or any(_matches(r, w) for w in any_of)):
            n += 1
    return n


def run_script_nd(project: Project, script: dict, inputs: dict[str, str], extra_args: list[str] | None = None) -> tuple[int, int]:
    """Run a project script and read numerator/denominator from its output (named groups n and d)."""
    import re as _re
    import subprocess
    cmd = list(script["cmd"]) + list(extra_args or [])
    try:
        out = subprocess.run(cmd, cwd=project.root, capture_output=True, text=True, timeout=int(script.get("timeout", 120)))
    except (OSError, subprocess.TimeoutExpired) as e:
        raise FactError(f"script failed: {' '.join(cmd)}: {e}")
    if out.returncode != 0:
        raise FactError(f"script exited {out.returncode}: {' '.join(cmd)}: {out.stderr.strip()[-200:]}")
    m = _re.search(script["pattern"], out.stdout)
    if not m:
        raise FactError(f"pattern not found in output of {' '.join(cmd)}")
    for f in [script["cmd"][-1]] + list(script.get("inputs") or []):
        fp = project.root / f
        if fp.is_file():
            inputs[f] = sha256_file(fp)
    return int(m.group("n")), int(m.group("d"))


# ---------- expression evaluation (restricted) ----------

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg}


def _eval_ast(node, env):
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body, env)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise FactError(f"unknown name in expression: {node.id}")
        return env[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_ast(node.left, env), _eval_ast(node.right, env))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_ast(node.operand, env))
    raise FactError("only + - * / and numbers are allowed in expr")


# ---------- the fact set ----------

class FactSet:
    def __init__(self, facts: dict[str, Fact]):
        self.facts = facts

    def get(self, ref: str) -> tuple[Fact, str]:
        fid, _, var = ref.partition(".")
        if fid not in self.facts:
            raise FactError(f"unknown fact '{fid}'")
        f = self.facts[fid]
        var = var or f.default_variant()
        if var not in f.variants:
            raise FactError(f"fact '{fid}' has no variant '{var}' (has: {', '.join(sorted(f.variants))})")
        return f, var

    def plain(self, ref: str) -> str:
        f, v = self.get(ref)
        return f.variants[v]["plain"]

    def tex(self, ref: str) -> str:
        f, v = self.get(ref)
        return f.variants[v]["tex"]

    def number_text(self, ref: str) -> str:
        """The variant's digits only (no %, no sign), for comparison with literals in prose."""
        return re.sub(r"[^0-9./,-]", "", self.plain(ref)).lstrip("-+")


def _operand(project: Project, op: Any, inputs: dict, fs: dict[str, Fact], extra: dict | None = None, entries: dict | None = None) -> float:
    if isinstance(op, (int, float)):
        return float(op)
    if isinstance(op, dict) and "from_tsv" in op:
        return float(count_tsv(project, op["from_tsv"], inputs, extra))
    if isinstance(op, dict) and "ref" in op and extra and entries is not None:
        # old-basis evaluation of a referenced fact: recompute it under the same extra filter
        fid, _, var = op["ref"].partition(".")
        e = entries[fid]
        return _old_basis_value(project, e, var or "n", inputs, extra, entries)
    if isinstance(op, dict) and "ref" in op:
        fid, _, var = op["ref"].partition(".")
        if fid not in fs:
            raise FactError(f"ref to unknown or later fact '{fid}' (order facts so dependencies come first)")
        f = fs[fid]
        var = var or f.default_variant()
        inputs.update(f.inputs)
        return f.numbers[var]
    raise FactError(f"bad operand: {op!r}")


def _old_basis_value(project, entry, var, inputs, extra, entries) -> float:
    if entry["kind"] == "count":
        return float(_operand(project, entry["count"], inputs, {}, extra, entries))
    if entry["kind"] == "proportion":
        n = _operand(project, entry["numerator"], inputs, {}, extra, entries)
        d = _operand(project, entry["denominator"], inputs, {}, extra, entries)
        return n if var == "n" else d
    raise FactError(f"old basis not defined for kind {entry['kind']}")


def _derive_superseded(project: Project, entry: dict, f: "Fact", entries: dict) -> None:
    """Values on the previous basis, computed from the same data (design 6.8). Mechanical, not hand-typed."""
    sb = entry.get("superseded_basis")
    if not sb:
        return
    near = sb.get("near") or []
    extra = sb.get("where") or {}
    scratch: dict[str, str] = {}
    cur = f.numbers
    if entry["kind"] == "count":
        old = int(_operand(project, entry["count"], scratch, {}, extra, entries))
        if old != cur["n"] and near:
            f.superseded.append({"text": str(old), "near": near, "allow_near": sb.get("allow_near") or [],
                                 "note": f"previous basis value ({sb.get('label', 'old basis')})"})
    elif entry["kind"] == "proportion":
        if entry.get("script"):
            n0, d0 = run_script_nd(project, entry["script"], scratch, sb.get("args"))
        else:
            n0 = int(_operand(project, entry["numerator"], scratch, {}, extra, entries))
            d0 = int(_operand(project, entry["denominator"], scratch, {}, extra, entries))
        if (n0, d0) != (cur["n"], cur["d"]) and d0 > 0:
            frac = f"{n0}/{d0}"
            allow = sb.get("allow_near") or []
            f.superseded.append({"text": frac, "allow_near": allow, "note": f"previous basis ({frac})"})
            if near:
                for dec in sb.get("decimals", [1]):
                    old_txt = fmt(100.0 * n0 / d0, dec)
                    if old_txt == fmt(cur["pct"], dec):
                        continue    # old and new values are the same at this rounding: not distinguishable, not stale
                    f.superseded.append({"text": old_txt, "near": near, "allow_near": allow, "pct": True,
                                         "note": f"previous basis ({frac})"})


def _build_one(project: Project, entry: dict, done: dict[str, Fact], entries: dict | None = None) -> Fact:
    fid, kind = entry["id"], entry["kind"]
    dec = int(entry.get("decimals", 1))
    f = Fact(fid, kind, entry, dec, superseded=entry.get("superseded") or [], note=entry.get("note", ""))

    def add(name: str, num: float, plain: str, tex: str | None = None):
        f.numbers[name] = num
        f.variants[name] = {"plain": plain, "tex": tex if tex is not None else plain}

    if kind == "value":
        v = entry["value"]
        d = 0 if float(v).is_integer() and "decimals" not in entry else dec
        add("value", float(v), fmt(float(v), d))
    elif kind == "count":
        n = int(_operand(project, entry["count"], f.inputs, done))
        add("n", n, str(n))
    elif kind == "proportion":
        if entry.get("script"):
            n, d = run_script_nd(project, entry["script"], f.inputs)
        else:
            n = int(_operand(project, entry["numerator"], f.inputs, done))
            d = int(_operand(project, entry["denominator"], f.inputs, done))
        if d <= 0:
            raise FactError(f"fact '{fid}': denominator is {d}")
        pct = 100.0 * n / d
        add("n", n, str(n))
        add("d", d, str(d))
        add("pct", pct, fmt(pct, dec) + "%", fmt(pct, dec) + "\\%")
        add("frac", n / d, f"{n}/{d}")
        if entry.get("ci", "wilson") == "wilson":
            lo, hi = wilson(n, d)
            add("ci_lo", lo, fmt(lo, dec))
            add("ci_hi", hi, fmt(hi, dec))
            add("ci", lo, f"{fmt(lo, dec)}--{fmt(hi, dec)}")
        add("full", pct, f"{fmt(pct, dec)}% ({n}/{d})", f"{fmt(pct, dec)}\\% ({n}/{d})")
    elif kind == "derived":
        env = {}
        expr = entry["expr"]

        def sub(m):
            ref = m.group(0)
            fid2, _, var = ref.partition(".")
            if fid2 not in done:
                raise FactError(f"fact '{fid}': expr refers to unknown or later fact '{fid2}'")
            f2 = done[fid2]
            var = var or f2.default_variant()
            name = f"v{len(env)}"
            env[name] = f2.numbers[var]
            f.inputs.update(f2.inputs)
            return name
        py = re.sub(r"[A-Za-z_][\w]*(?:\.[A-Za-z_]+)?", sub, expr)
        val = _eval_ast(ast.parse(py, mode="eval"), env)
        d = int(entry.get("decimals", 1))
        add("value", val, fmt(val, d))
        sign = "+" if val >= 0 else "-"
        add("signed", val, f"{sign}{fmt(abs(val), d)}", f"${sign}${fmt(abs(val), d)}")
    else:
        raise FactError(f"fact '{fid}': unknown kind '{kind}'")
    _derive_superseded(project, entry, f, entries or {})
    return f


def load_fact_entries(project: Project) -> list[dict]:
    p = project.path("facts")
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text()) or {}
    return data.get("facts", [])


def build_facts(project: Project) -> tuple[FactSet, list[str]]:
    """Compute every fact. Returns (FactSet, errors); a failing fact is reported, not skipped silently."""
    done: dict[str, Fact] = {}
    errors: list[str] = []
    all_entries = load_fact_entries(project)
    by_id = {e["id"]: e for e in all_entries if "id" in e}
    for entry in all_entries:
        try:
            if entry["id"] in done:
                raise FactError(f"duplicate fact id '{entry['id']}'")
            done[entry["id"]] = _build_one(project, entry, done, by_id)
        except FactError as e:
            errors.append(str(e))
        except KeyError as e:
            errors.append(f"fact '{entry.get('id', '?')}': missing field {e}")
    return FactSet(done), errors
