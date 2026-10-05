"""Unit provenance and AI-use disclosure drafts (design 13.2).

Every unit may record who wrote it (human, agent, mixed), which model, which brief, and when.
``ah disclosure`` turns that ledger into a venue-agnostic draft the author edits and approves.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import RUBRIC_VERSION, __version__
from .ledger.db import Ledger
from .project import Project
from .tex.units import load_units

AUTHOR_TYPES = ("human", "agent", "mixed", "unknown")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _units(project: Project) -> list:
    return load_units(project)[0]


def record(project: Project, unit: str, *, author_type: str, model: str | None = None,
           brief_id: str | None = None, by: str = "agent", unit_hash: str | None = None,
           note: str = "") -> dict:
    if author_type not in AUTHOR_TYPES:
        raise ValueError(f"author_type must be one of {AUTHOR_TYPES}")
    led = Ledger(project)
    try:
        existing = led.provenance_get(unit)
        if existing and existing["author_type"] != author_type and {existing["author_type"], author_type} <= {"human", "agent"}:
            author_type = "mixed"
        row = led.provenance_set(unit, author_type=author_type, model=model, brief_id=brief_id,
                                 by_whom=by, recorded_at=_now(), unit_hash=unit_hash, note=note)
        return dict(row)
    finally:
        led.close()


def record_files(project: Project, files: list[str], **kw) -> list[dict]:
    """Record provenance for every unit whose file is in ``files`` (TeX-root or project relative)."""
    want = {f.strip().lstrip("./") for f in files if f and f.strip()}
    if not want:
        return []
    out = []
    for u in _units(project):
        if u.file in want or any(u.file.endswith("/" + w) or w.endswith("/" + u.file) or w == u.file for w in want):
            if not u.uid:
                continue
            out.append(record(project, u.uid, unit_hash=u.hash, **kw))
    return out


def fill_missing(project: Project, *, author_type: str, by: str, note: str = "filled unrecorded units") -> int:
    led = Ledger(project)
    try:
        have = {r["unit"] for r in led.provenance_list()}
    finally:
        led.close()
    n = 0
    for u in _units(project):
        if u.uid and u.uid not in have:
            record(project, u.uid, author_type=author_type, by=by, unit_hash=u.hash, note=note)
            n += 1
    return n


def summary(project: Project) -> dict[str, Any]:
    units = [u for u in _units(project) if u.uid]
    led = Ledger(project)
    try:
        rows = [dict(r) for r in led.provenance_list()]
        runs = led.all_run_manifests()
        disc = led.disclosure_latest()
    finally:
        led.close()
    by_unit = {r["unit"]: r for r in rows}
    counts = {t: 0 for t in AUTHOR_TYPES}
    counts["unrecorded"] = 0
    models, briefs = set(), set()
    for u in units:
        r = by_unit.get(u.uid)
        if not r:
            counts["unrecorded"] += 1
            continue
        counts[r["author_type"]] = counts.get(r["author_type"], 0) + 1
        if r.get("model"):
            models.add(r["model"])
        if r.get("brief_id"):
            briefs.add(r["brief_id"])
    verifier = []
    for m in runs:
        v = (m.get("verifier") or m.get("backend") or {})
        if isinstance(v, str):
            verifier.append(v)
        elif isinstance(v, dict) and (v.get("model") or v.get("backend")):
            verifier.append(v.get("model") or v.get("backend"))
    return {
        "units": len(units),
        "recorded": len(units) - counts["unrecorded"],
        "counts": counts,
        "models": sorted(models),
        "briefs": sorted(briefs),
        "verifier_models": sorted({x for x in verifier if x}),
        "disclosure": {"status": disc["status"], "at": disc["recorded_at"]} if disc else None,
        "rows": rows,
    }


def draft(project: Project) -> dict[str, Any]:
    s = summary(project)
    c = s["counts"]
    agentish = c.get("agent", 0) + c.get("mixed", 0)
    lines = [
        f"# AI-use disclosure (draft — the author must edit and approve)",
        "",
        f"This document was prepared with Academic Harness {__version__} (rubric {RUBRIC_VERSION}).",
        "",
        "## Writing assistance",
        f"Of {s['units']} prose units with stable ids, {agentish} record agent assistance"
        + (f" (models: {', '.join(s['models'])})" if s["models"] else " (model id not recorded)")
        + f", {c.get('mixed', 0)} mixed human/agent, {c.get('human', 0)} human-only, and {c.get('unrecorded', 0)} unrecorded.",
    ]
    if s["briefs"]:
        lines.append(f"Approved briefs used as writing instructions: {', '.join(s['briefs'])}.")
    lines += [
        "The author remains responsible for the scientific content. Agent-written units were reviewed before inclusion.",
        "",
        "## Verification",
        "Deterministic checks (structure, numbers, bibliography, profile rules) were run by code and do not use a language model.",
        "The T3 evidence verifier, when used, is advisory and does not gate the document.",
    ]
    if s["verifier_models"]:
        lines.append(f"Verifier model recorded in run manifests: {', '.join(s['verifier_models'])}.")
    else:
        lines.append("No T3 verifier model is recorded in the ledger run manifests.")
    lines += [
        "",
        "## Citations",
        "Bibliography entries are not generated by a language model. Citation keys must exist in the project's bibliography; empirical claims about sources must be traceable to a registered source.",
        "",
        "## How to use this draft",
        "Edit the text to match the venue's AI-disclosure policy, then run `ah disclosure approve --yes`. Approval records the hash of the approved text in the ledger; it does not submit anything.",
    ]
    text = "\n".join(lines) + "\n"
    return {"text": text, "summary": {k: s[k] for k in ("units", "recorded", "counts", "models", "briefs",
                                                        "verifier_models", "disclosure")}}


def approve(project: Project, text: str, *, by: str) -> dict:
    from .util import sha1
    led = Ledger(project)
    try:
        row = led.disclosure_approve(text, by=by, recorded_at=_now(), text_hash=sha1(text))
        return dict(row)
    finally:
        led.close()
