"""Sweep: find every place a value, term or fact is used (design 6.8).

The point is to remove the "one more stale passage" cycle. After a fact changes, the sweep lists
every unit that uses the new value, still holds the old value, or holds a declared superseded
value, across all views, appendices and supplementary files, in one pass.
"""
from __future__ import annotations

import re

from .checks.t1_numeric import _plain
from .context import Context, unit_ref
from .tex.text import RE_FACT, strip_comments


def _occurrences(ctx: Context, pattern: re.Pattern, label: str) -> list[dict]:
    hits = []
    seen_units = set()
    for u in ctx.units:
        text = _plain(u.raw)
        for m in pattern.finditer(text):
            seen_units.add(unit_ref(u))
            hits.append({"unit": unit_ref(u), "file": u.file, "line": u.start, "why": label,
                         "snippet": text[max(0, m.start() - 50): m.end() + 50]})
            break
    # files (views, preamble, anything outside units) that mention it
    for rel, text in sorted(ctx.tex_texts.items()):
        if any(u.file == rel for u in ctx.units):
            continue
        plain = _plain(text)
        m = pattern.search(plain)
        if m:
            hits.append({"unit": None, "file": rel, "line": None, "why": label, "snippet": plain[max(0, m.start() - 50): m.end() + 50]})
    return hits


def value_pattern(value: str, regex: bool = False) -> re.Pattern:
    if regex:
        return re.compile(value)
    return re.compile(r"(?<![\d./])" + re.escape(value) + r"(?![\d.]*\d|/\d)")


def sweep_value(ctx: Context, value: str, regex: bool = False) -> list[dict]:
    return _occurrences(ctx, value_pattern(value, regex), f"value {value}")


def sweep_fact(ctx: Context, fact_id: str, old: dict | None = None) -> dict:
    """Units that use a fact (macro or binding), plus units holding old or superseded values."""
    uses = []
    for i in ctx.inv:
        for key in i.facts_used:
            if key.partition(".")[0] == fact_id:
                uses.append({"unit": unit_ref(i.unit), "file": i.unit.file, "line": i.unit.start, "why": f"\\fact{{{key}}}"})
    for b in ctx.bindings:
        if str(b.get("fact", "")).partition(".")[0] == fact_id:
            u = ctx.unit_by_ref().get(b.get("unit"))
            uses.append({"unit": b.get("unit"), "file": u.file if u else None, "line": u.start if u else None, "why": f"bound literal {b.get('token')}"})
    stale = []
    f = ctx.facts.facts.get(fact_id)
    if f:
        for s in f.superseded:
            stale += _occurrences(ctx, value_pattern(str(s["text"])), f"superseded {s['text']}")
    if old and fact_id in old:
        for var, oldv in old[fact_id].items():
            old_val = oldv[0] if isinstance(oldv, (list, tuple)) else oldv
            if old_val:
                digits = re.sub(r"[^0-9./]", "", old_val)
                if digits:
                    stale += _occurrences(ctx, value_pattern(digits), f"previous value of {fact_id}.{var} ({old_val})")
    return {"fact": fact_id, "uses": uses, "stale_or_old": stale}
