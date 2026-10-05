"""Tier T6: the declarative rule kinds a profile can use (design 9, 9.2).

sections    required headings (alternatives with "A|B")
identities  arithmetic relations between facts, e.g. a PRISMA flow that must close
checklist   every item of a reporting guideline maps to existing units, to text matched in a named file, or to "n/a" with a reason
limit       word limits over chosen files
patterns    forbidden regular expressions (anonymisation, tone) in text or in review responses
table_rows  rows in a table equal facts (per-study table = number of included studies)
records     a record graph in YAML: references, children, ranges, ordering, sums (grant budget, thesis chapters)
coverage    every item (criterion, outcome, contribution) is covered by existing units, optionally in each of several file groups
reviews_closed  every reviewer item is answered

All checks are code. Whether a mapped paragraph really addresses a checklist item or criterion is a semantic question these
rules do not answer; they check that it exists, where it is, and that nothing is left unmapped.
"""
from __future__ import annotations

import ast
import fnmatch
import operator
import re
from pathlib import Path

import yaml

from . import project_rules
from ..checks.base import CATALOGUE, Finding
from ..context import Context, unit_ref
from ..facts.model import FactError
from ..tex.text import strip_comments

HEADING_RX = re.compile(r"\\(?:chapter|section|subsection|subsubsection|paragraph)\*?\{([^}]*)\}")
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
CMP = {ast.Eq: lambda a, b, t: abs(a - b) <= t, ast.LtE: lambda a, b, t: a <= b + t, ast.GtE: lambda a, b, t: a >= b - t,
       ast.Lt: lambda a, b, t: a < b, ast.Gt: lambda a, b, t: a > b}


def _match(path: str, globs) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in ([globs] if isinstance(globs, str) else globs or ["*"]))


def _load_yaml(ctx: Context, rel: str):
    f = ctx.project.root / rel
    if not f.is_file():
        return None
    try:
        return yaml.safe_load(f.read_text()) or {}
    except yaml.YAMLError:
        return False


class Run:
    """Collects findings for one rule; honours the project's per-check level overrides."""

    def __init__(self, ctx: Context, rule: dict, out: list[Finding]):
        self.ctx, self.rule, self.out = ctx, rule, out
        self.rid = rule.get("id") or rule["kind"]

    def add(self, check: str, ref, file, key: str, msg: str, line=None):
        tier, level, _ = CATALOGUE[check]
        over = (self.ctx.cfg.get("levels") or {}).get(check)
        level = over or self.rule.get("level") or level
        if level != "off":
            self.out.append(Finding(check, level, ref, file, line, f"{self.rid}:{key}", f"[{self.rid}] {msg}", tier))

    def bad(self, msg: str, key: str = "config"):
        self.add("PRF-08", None, self.rule.get("file") or self.rule.get("map"), key, msg)

    def data(self, rel: str | None, what: str):
        if not rel:
            self.bad(f"rule has no {what} file")
            return None
        d = _load_yaml(self.ctx, rel)
        if d is None:
            if self.rule.get("optional"):
                return None
            self.bad(f"{what} file {rel} does not exist", f"missing:{rel}")
        elif d is False:
            self.bad(f"{what} file {rel} is not valid YAML", f"yaml:{rel}")
            return None
        return d or None


def _headings(ctx: Context) -> list[tuple[str, str]]:
    out = []
    for rel in sorted(ctx.reachable or ctx.tex_texts):
        for m in HEADING_RX.finditer(ctx.tex_texts.get(rel, "")):
            out.append((re.sub(r"\s+", " ", m.group(1)).strip().lower(), rel))
    return out


def run_sections(r: Run):
    heads = [h for h, _ in _headings(r.ctx)]
    for req in r.rule.get("required") or []:
        alts = [a.strip().lower() for a in str(req).split("|")]
        if not any(h == a or h.startswith(a + " ") or h.endswith(" " + a) for h in heads for a in alts):
            r.add("PRF-01", None, None, f"section:{req}", f"no heading matching '{req}' in the document")


def _eval(node, env, r: Run):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        ref = node.id
    elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        ref = f"{node.value.id}.{node.attr}"
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand, env, r)
    elif isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.left, env, r), _eval(node.right, env, r))
    else:
        raise FactError("only numbers, fact ids, + - * / and one comparison are allowed")
    fid, _, var = ref.partition(".")
    if fid not in env.facts:
        raise FactError(f"unknown fact '{fid}'")
    f = env.facts[fid]
    var = var or f.default_variant()
    if var not in f.numbers:
        raise FactError(f"fact '{fid}' has no variant '{var}'")
    return f.numbers[var]


def run_identities(r: Run):
    for expr in r.rule.get("expr") or []:
        try:
            tree = ast.parse(expr, mode="eval").body
            if not (isinstance(tree, ast.Compare) and len(tree.ops) == 1 and type(tree.ops[0]) in CMP):
                raise FactError("write one comparison, for example 'a - b == c'")
            a, b = _eval(tree.left, r.ctx.facts, r), _eval(tree.comparators[0], r.ctx.facts, r)
        except (FactError, SyntaxError) as e:
            r.bad(f"identity '{expr}' cannot be evaluated: {e}", f"expr:{expr}")
            continue
        if not CMP[type(tree.ops[0])](a, b, float(r.rule.get("tol", 0))):
            r.add("PRF-02", None, None, f"expr:{expr}", f"{expr} does not hold: {a:g} against {b:g}")


def run_checklist(r: Run):
    items_rel = r.rule.get("items")
    items_doc = _load_yaml(r.ctx, items_rel) if items_rel else None      # the project's own list wins; else the one shipped with the profile
    if items_doc is None:
        items_doc = _packaged(r)
    if items_doc is None:
        if not r.rule.get("optional"):
            r.bad(f"checklist items file {items_rel} does not exist", f"missing:{items_rel}")
        return
    if items_doc is False:
        r.bad(f"checklist items file {items_rel} is not valid YAML", f"yaml:{items_rel}")
        return
    items = items_doc.get("items") or []
    mapping = r.data(r.rule.get("map"), "mapping")
    if mapping is None:
        return
    known = {unit_ref(u) for u in r.ctx.units}
    m = mapping["items"] if "items" in mapping else mapping
    m = m or {}
    for it in items:
        iid = str(it["id"])
        ent = m.get(iid) if isinstance(m, dict) else None
        label = f"item {iid} ({it.get('topic') or it.get('text', '')[:40]})"
        if not ent:
            r.add("PRF-03", None, r.rule.get("map"), f"item:{iid}", f"{label} is not mapped")
        elif ent.get("file"):                       # reported outside any paragraph unit (title, front matter): the text must be there
            text = r.ctx.tex_texts.get(ent["file"])
            if text is None:
                r.add("PRF-03", None, r.rule.get("map"), f"file:{iid}", f"{label} is mapped to {ent['file']}, which is not a TeX file of this project")
            elif ent.get("re") and not re.search(ent["re"], text, re.I | re.S):
                r.add("PRF-03", None, r.rule.get("map"), f"text:{iid}", f"{label}: no text matching /{ent['re']}/ in {ent['file']}")
        elif ent.get("na"):
            if not str(ent["na"]).strip() or len(str(ent["na"]).split()) < 3:
                r.add("PRF-03", None, r.rule.get("map"), f"na:{iid}", f"{label} is marked n/a without a reason")
        else:
            units = ent.get("units") or []
            if not units:
                r.add("PRF-03", None, r.rule.get("map"), f"item:{iid}", f"{label} is mapped to no unit")
            for u in units:
                if u not in known:
                    r.add("PRF-03", None, r.rule.get("map"), f"unit:{iid}:{u}", f"{label} is mapped to unit {u}, which does not exist")
    for iid in (m if isinstance(m, dict) else {}):
        if str(iid) not in {str(i["id"]) for i in items}:
            r.add("PRF-03", None, r.rule.get("map"), f"unknown:{iid}", f"mapping has item {iid}, which is not in the checklist")


def _packaged(r: Run):
    prof = r.ctx.project.profile
    f = (prof.dir / Path(r.rule["items"]).name) if prof else None
    return yaml.safe_load(f.read_text()) if f and f.is_file() else None


def run_limit(r: Run):
    files, skip = r.rule.get("files"), r.rule.get("exclude")
    us = [u for u in r.ctx.units if u.kind == "para" and _match(u.file, files) and not (skip and _match(u.file, skip))
          and (not r.ctx.reachable or u.file in r.ctx.reachable)]
    if files and not us:
        return
    words = sum(u.words for u in us)
    mx = r.rule.get("max_words")
    if mx and words > int(mx):
        r.add("PRF-04", None, None, f"words:{r.rule.get('label', 'document')}", f"{r.rule.get('label', 'document')} has {words} words (limit {mx})")


def run_patterns(r: Run):
    pats = [(re.compile(p["re"], re.I), p.get("why", p["re"])) for p in r.rule.get("lexicon") or []]
    if r.rule.get("in") == "reviews":
        from .. import reviews
        for rev in reviews.load_all(r.ctx.project):
            for it in rev["items"]:
                for rx, why in pats:
                    m = rx.search(it.get("response") or "")
                    if m:
                        r.add("PRF-05", None, None, f"{it['id']}:{rx.pattern}", f"{it['id']}: '{m.group(0)[:50]}' ({why})")
        return
    for u in r.ctx.units:
        if not _match(u.file, r.rule.get("files")):
            continue
        body = strip_comments(u.raw)
        for rx, why in pats:
            m = rx.search(body)
            if m:
                r.add("PRF-05", unit_ref(u), u.file, f"{rx.pattern}", f"'{m.group(0)[:50]}' ({why})", u.start)


def _path(doc: dict, path: str):
    cur = doc
    for p in str(path).split("."):
        cur = cur.get(p) if isinstance(cur, dict) else None
    return cur


def _num(r: Run, doc: dict, spec):
    if isinstance(spec, (int, float)):
        return float(spec)
    if isinstance(spec, str):
        v = _path(doc, spec)
        return float(v) if isinstance(v, (int, float)) else None
    if isinstance(spec, dict) and "fact" in spec:
        try:
            return _eval(ast.parse(spec["fact"], mode="eval").body, r.ctx.facts, r)
        except (FactError, SyntaxError):
            return None
    if isinstance(spec, dict) and "sum" in spec:
        t, _, f = spec["sum"].partition(".")
        return float(sum(x.get(f) or 0 for x in doc.get(t) or []))
    return None


def run_records(r: Run):
    doc = r.data(r.rule.get("file"), "records")
    if not doc:
        return
    file = r.rule["file"]
    ids: dict[str, set] = {}
    for table, rows in doc.items():
        if isinstance(rows, list):
            seen = set()
            for row in rows:
                rid = str(row.get("id"))
                if rid in seen:
                    r.add("PRF-06", None, file, f"dup:{table}:{rid}", f"{table}: id '{rid}' is used twice")
                seen.add(rid)
            ids[table] = seen
    for c in r.rule.get("checks") or []:
        t, typ = c.get("table"), c.get("type")
        rows = doc.get(t) or []
        if typ == "min_rows":
            if len(rows) < int(c.get("min", 1)):
                r.add("PRF-06", None, file, f"empty:{t}", f"{t} has {len(rows)} record(s), at least {c.get('min', 1)} expected")
        elif typ == "ref":
            for row in rows:
                vals = row.get(c["field"])
                for v in (vals if isinstance(vals, list) else [vals]):
                    if v is None or str(v) not in ids.get(c["to"], set()):
                        r.add("PRF-06", None, file, f"ref:{t}.{row.get('id')}.{c['field']}:{v}",
                              f"{t} '{row.get('id')}' has {c['field']} '{v}', which is not in {c['to']}")
        elif typ == "has_child":
            ch = doc.get(c["child"]) or []
            where = c.get("where") or {}
            for row in (x for x in rows if all(x.get(k) == v for k, v in where.items())):
                if not any(str(row.get("id")) in [str(x) for x in (k.get(c["field"]) if isinstance(k.get(c["field"]), list) else [k.get(c["field"])])] for k in ch):
                    r.add("PRF-06", None, file, f"nochild:{t}.{row.get('id')}.{c['child']}", f"{t} '{row.get('id')}' has no {c['child']}")
        elif typ == "range":
            lo, hi = _num(r, doc, c.get("min", 0)), _num(r, doc, c.get("max"))
            for row in rows:
                v = row.get(c["field"])
                if not isinstance(v, (int, float)) or (lo is not None and v < lo) or (hi is not None and v > hi):
                    r.add("PRF-06", None, file, f"range:{t}.{row.get('id')}.{c['field']}", f"{t} '{row.get('id')}': {c['field']} {v} is outside {lo:g}..{hi:g}")
        elif typ == "order":
            for row in rows:
                a, b = row.get(c["lo"]), row.get(c["hi"])
                if not (isinstance(a, (int, float)) and isinstance(b, (int, float)) and a <= b):
                    r.add("PRF-06", None, file, f"order:{t}.{row.get('id')}", f"{t} '{row.get('id')}': {c['lo']} {a} is not before {c['hi']} {b}")
        elif typ == "sum":
            total = float(sum(x.get(c["field"]) or 0 for x in rows))
            want = _num(r, doc, c["equals"])
            if want is None:
                r.bad(f"sum over {t}.{c['field']}: cannot resolve 'equals'", f"sumref:{t}.{c['field']}")
            elif abs(total - want) > float(c.get("tol", 0)):
                r.add("PRF-06", None, file, f"sum:{t}.{c['field']}", f"{t}.{c['field']} sums to {total:g}, expected {want:g}")
        else:
            r.bad(f"unknown record check type '{typ}'", f"type:{typ}")


def run_coverage(r: Run):
    doc = r.data(r.rule.get("file"), "coverage")
    if not doc:
        return
    file, known = r.rule["file"], {unit_ref(u): u for u in r.ctx.units}
    groups = r.rule.get("groups") or [None]
    label = r.rule.get("label", "item")
    if r.rule.get("ids_from"):                      # every id in an author-owned table must have an item here
        src = r.data(r.rule["ids_from"]["file"], "records") or {}
        have = {str(i["id"]) for i in doc.get("items") or []}
        for row in src.get(r.rule["ids_from"]["table"]) or []:
            if str(row.get("id")) not in have:
                r.add("PRF-07", None, file, f"missing:{row.get('id')}", f"{label} {row.get('id')} (from {r.rule['ids_from']['file']}) has no entry here")
    for it in doc.get("items") or []:
        iid, units = str(it["id"]), it.get("units") or []
        if it.get("na"):
            continue
        if not units:
            r.add("PRF-07", None, file, f"none:{iid}", f"{label} {iid} is covered by no unit")
            continue
        for u in units:
            if u not in known:
                r.add("PRF-07", None, file, f"gone:{iid}:{u}", f"{label} {iid} names unit {u}, which does not exist")
        for g in groups:
            if g and not any(u in known and _match(known[u].file, g) for u in units):
                r.add("PRF-07", None, file, f"group:{iid}:{g[0] if isinstance(g, list) else g}",
                      f"{label} {iid} has no unit in {g if isinstance(g, str) else ' or '.join(g)}")


def run_reviews_closed(r: Run):
    from .. import reviews
    for rev in reviews.load_all(r.ctx.project):
        for it in rev["items"]:
            if it["status"] in ("open", "decision-needed"):
                r.add("PRF-09", None, None, f"{it['id']}", f"reviewer item {it['id']} is {it['status']}")


def table_row_counts(text: str, env: str, start: str | None, rows: list[dict]) -> list[tuple[dict, int]]:
    """Data rows of the first `env` environment (rows with a column separator, after `start` if given), counted overall and per regexp."""
    b = re.search(r"\\begin\{" + re.escape(env) + r"\*?\}", text)
    e = re.search(r"\\end\{" + re.escape(env) + r"\*?\}", text)
    if not b or not e:
        return []
    body = text[b.end():e.start()]
    if start and start in body:
        body = body[body.index(start) + len(start):]
    pieces = re.split(r"\\\\(?:\[[^\]]*\])?[ \t]*(?:\n|$)", body)
    data = [x for x in pieces if "&" in x and not re.match(r"\s*(?:\\(?:top|mid|bottom)rule\s*)*\\(multicolumn|caption|label)", x)]
    return [(spec, sum(1 for x in data if not spec.get("re") or re.search(spec["re"], x))) for spec in rows]


def run_table_rows(r: Run):
    rel = r.rule.get("table")
    text = r.ctx.tex_texts.get(rel or "")
    if text is None:
        r.bad(f"table file {rel} was not found among the TeX files", f"missing:{rel}")
        return
    counted = table_row_counts(text, r.rule.get("env", "longtable"), r.rule.get("start"), r.rule.get("rows") or [])
    if not counted:
        r.bad(f"no {r.rule.get('env', 'longtable')} environment in {rel}", f"env:{rel}")
        return
    for spec, n in counted:
        try:
            want = _eval(ast.parse(spec["fact"], mode="eval").body, r.ctx.facts, r)
        except (FactError, SyntaxError) as e:
            r.bad(f"row count '{spec.get('label')}': {e}", f"fact:{spec.get('label')}")
            continue
        if n != want:
            r.add("PRF-02", None, rel, f"rows:{spec.get('label')}", f"{rel} has {n} {spec.get('label', 'rows')}; the facts say {want:g} ({spec['fact']})")


KINDS = {"sections": run_sections, "identities": run_identities, "checklist": run_checklist, "limit": run_limit,
         "patterns": run_patterns, "records": run_records, "table_rows": run_table_rows, "coverage": run_coverage, "reviews_closed": run_reviews_closed}


def check_profile(ctx: Context) -> list[Finding]:
    out: list[Finding] = []
    for rule in project_rules(ctx.project):
        fn = KINDS.get(rule.get("kind"))
        r = Run(ctx, rule, out)
        if fn is None:
            r.bad(f"unknown rule kind '{rule.get('kind')}'", f"kind:{rule.get('kind')}")
        else:
            fn(r)
    return out
