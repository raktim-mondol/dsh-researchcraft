"""T5 document-level style lints (design 6.6). Code only; advisory (info) until a labelled eval promotes a lint.

A model-scored dimension (STY-02) is not emitted. It stays dropped until it passes the admission
test in 6.10 against `golden/t5_style_v0.jsonl`.
"""
from __future__ import annotations

import re

from ..context import Context, unit_ref
from .base import Finding, make

# Tight patterns from the example's human-read Jev items (jev_quality_check_2026-10-01.md).
# Broad words (should, must, clearly, needed) are not used on their own: they flagged 82/94
# paragraphs at the 0.5 model gate and do not discriminate.
LINTS: dict[str, tuple[str, str]] = {
    "mutually_reinforcing": (r"\bmutually reinforcing\b",
                             "unsourced interaction claim; a descriptive review can say the patterns are consistent"),
    "originates_in": (r"\boriginates in\b",
                      "causal origin verb; a descriptive review reports what the studies showed"),
    "directive": (r"\b(we urge|it is essential(?: that)?|must balance|equitable care requires|should be integrated)\b",
                  "directive wording in a descriptive document"),
    "intensifier": (r"\b(obviously|undoubtedly|unprecedented|conclusively)\b",
                    "unsupported intensifier"),
    "universal": (r"\b(always|never)\b",
                  "universal claim"),
    "prove": (r"\b(proves?|proved|proven)\b",
              "proof verb; empirical prose reports what the evidence shows"),
}

COMPILED = {name: re.compile(pat, re.I) for name, (pat, _) in LINTS.items()}


def enabled_lints(cfg: dict) -> list[str]:
    """Default: all code lints. `style.lints: []` turns them off; a list names a subset."""
    style = cfg.get("style") or {}
    if "lints" in style:
        names = list(style["lints"] or [])
        return [n for n in names if n in LINTS]
    return list(LINTS)


def lint_text(text: str, names: list[str] | None = None) -> list[tuple[str, str]]:
    """Return (lint name, matched text) for each hit. First match per lint."""
    names = names if names is not None else list(LINTS)
    out = []
    for name in names:
        m = COMPILED[name].search(text or "")
        if m:
            out.append((name, m.group(0)))
    return out


def check_style(ctx: Context) -> list[Finding]:
    cfg, out = ctx.cfg, []
    names = enabled_lints(cfg)
    if not names:
        return out
    level = (cfg.get("style") or {}).get("level", "info")
    recheck = getattr(ctx, "recheck", None)
    for u in ctx.units:
        if u.kind != "para" or u.words < 12:
            continue
        ref = unit_ref(u)
        if recheck is not None and ref not in recheck:
            continue
        for name, tok in lint_text(u.norm, names):
            why = LINTS[name][1]
            f = make(cfg, "STY-01", ref, u.file, u.start, f"lint:{name}:{tok.lower()}",
                     f"{name}: \"{tok}\" ({why})")
            if f:
                if "STY-01" not in (cfg.get("levels") or {}):
                    f.level = level
                out.append(f)
    return out
