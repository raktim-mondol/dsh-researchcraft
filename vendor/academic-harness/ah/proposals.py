"""Facts proposed by an agent; only the author accepts them (design 8.6, 10.6 ah_fact_propose).

A proposal is a fact spec plus a reason. It is validated by actually computing it against the data, so the author
reviews a real value, not a promise. Accepting appends it to the facts file and rebuilds the macros.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .facts.model import FactError, _build_one, build_facts, load_fact_entries
from .project import Project


def pdir(p: Project) -> Path:
    return p.root / p.cfg["proposals"] / "facts"


def validate(p: Project, entry: dict) -> dict:
    """Compute the proposed fact on top of the existing ones. Returns its variants; raises FactError."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(entry.get("id", ""))):
        raise FactError("fact id must be letters, digits and underscores, starting with a letter")
    if "kind" not in entry:
        raise FactError("a fact needs a kind (count, proportion, derived, value)")
    existing = load_fact_entries(p)
    if any(e.get("id") == entry["id"] for e in existing):
        raise FactError(f"fact '{entry['id']}' already exists")
    fs, errs = build_facts(p)
    if errs:
        raise FactError("existing facts do not build: " + "; ".join(errs[:2]))
    by_id = {e["id"]: e for e in existing if "id" in e}
    f = _build_one(p, entry, dict(fs.facts), by_id)
    return {v: d["plain"] for v, d in f.variants.items()}


def propose(p: Project, entry: dict, why: str, by: str = "agent") -> dict:
    values = validate(p, entry)
    d = pdir(p)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{entry['id']}.yaml"
    if f.exists():
        raise FactError(f"a proposal for '{entry['id']}' is already pending")
    f.write_text(yaml.safe_dump({"proposal": entry, "why": why, "proposed_by": by, "computed": values}, sort_keys=False, allow_unicode=True))
    return {"id": entry["id"], "computed": values}


def list_pending(p: Project) -> list[dict]:
    d = pdir(p)
    return [yaml.safe_load(f.read_text()) for f in sorted(d.glob("*.yaml"))] if d.exists() else []


def accept(p: Project, fid: str) -> dict:
    f = pdir(p) / f"{fid}.yaml"
    if not f.exists():
        raise FactError(f"no pending proposal '{fid}'")
    rec = yaml.safe_load(f.read_text())
    entry = rec["proposal"]
    validate(p, entry)                                   # re-check against the data as it is now
    fp = p.path("facts")
    text = fp.read_text() if fp.exists() else "facts: []\n"
    block = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True).rstrip("\n")
    block = "\n".join("  " + l if l else l for l in block.split("\n"))
    if re.search(r"^facts:\s*\[\s*\]\s*$", text, re.M):
        text = re.sub(r"^facts:\s*\[\s*\]\s*$", "facts:\n" + block, text, count=1, flags=re.M)
    else:
        text = text.rstrip("\n") + "\n" + block + "\n"
    fp.write_text(text)
    f.unlink()
    return entry


def reject(p: Project, fid: str) -> None:
    f = pdir(p) / f"{fid}.yaml"
    if not f.exists():
        raise FactError(f"no pending proposal '{fid}'")
    f.unlink()
