"""Snapshots of unit text and word-level diffs (design 8.5).

A snapshot records every unit's text under its anchor id. A diff against it says which units were changed, added
or removed, and shows the change word by word, so a response can only describe changes that really happened.
"""
from __future__ import annotations

import difflib
import json
import re
from datetime import datetime, timezone

from .context import Context, unit_ref
from .project import Project
from .tex.text import RE_ANCHOR, strip_comments
from .util import collapse_ws


def _dir(p: Project):
    d = p.state_dir / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def unit_text(u) -> str:
    return collapse_ws(strip_comments("\n".join(l for l in u.raw.split("\n") if not RE_ANCHOR.match(l))))


def save(ctx: Context, name: str, overwrite: bool = False) -> dict:
    f = _dir(ctx.project) / f"{name}.json"
    if f.exists() and not overwrite:
        raise ValueError(f"snapshot '{name}' already exists")
    units = {unit_ref(u): {"file": u.file, "hash": u.hash, "text": unit_text(u)} for u in ctx.units}
    f.write_text(json.dumps({"name": name, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "units": units}, indent=0))
    return {"name": name, "units": len(units)}


def load(p: Project, name: str) -> dict | None:
    f = _dir(p) / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else None


def names(p: Project) -> list[str]:
    return sorted(f.stem for f in _dir(p).glob("*.json"))


def word_diff(a: str, b: str, context: int = 8) -> str:
    """`[-old-]{+new+}` markers over words, with only `context` unchanged words around each change."""
    ta, tb = a.split(), b.split()
    sm = difflib.SequenceMatcher(a=ta, b=tb, autojunk=False)
    parts: list[str] = []
    ops = sm.get_opcodes()
    for i, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal":
            seg = ta[i1:i2]
            if len(seg) > 2 * context and 0 < i < len(ops) - 1:
                parts.append(" ".join(seg[:context]) + " … " + " ".join(seg[-context:]))
            elif i == 0 and len(seg) > context:
                parts.append("… " + " ".join(seg[-context:]))
            elif i == len(ops) - 1 and len(seg) > context:
                parts.append(" ".join(seg[:context]) + " …")
            else:
                parts.append(" ".join(seg))
        else:
            if i1 < i2:
                parts.append("[-" + " ".join(ta[i1:i2]) + "-]")
            if j1 < j2:
                parts.append("{+" + " ".join(tb[j1:j2]) + "+}")
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def diff(ctx: Context, name: str) -> dict:
    snap = load(ctx.project, name)
    if snap is None:
        raise ValueError(f"no snapshot '{name}'")
    old = snap["units"]
    cur = {unit_ref(u): u for u in ctx.units}
    changed, added, removed = [], [], []
    for uid, u in cur.items():
        if uid not in old:
            added.append({"unit": uid, "file": u.file, "after": unit_text(u)})
        elif old[uid]["hash"] != u.hash:
            t = unit_text(u)
            changed.append({"unit": uid, "file": u.file, "before": old[uid]["text"], "after": t, "diff": word_diff(old[uid]["text"], t)})
    for uid, o in old.items():
        if uid not in cur:
            removed.append({"unit": uid, "file": o["file"], "before": o["text"]})
    return {"snapshot": name, "created": snap.get("created"), "changed": changed, "added": added, "removed": removed}
