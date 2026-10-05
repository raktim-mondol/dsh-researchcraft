"""The audit pipeline: build context, run tiers, reconcile with the ledger, report (design 6.7).

An audit is a function of (snapshot, rubric version). With no input change a second run gives an
identical findings list (DET-01) and every new finding carries a stated cause.
"""
from __future__ import annotations

import time
from collections import Counter

from . import RUBRIC_VERSION, __version__
from .checks.base import CATALOGUE, DEFAULT_TIERS, TIERS, Finding, sort_key
from .checks.t0_structure import check_t0
from .checks.t1_numeric import check_t1
from .checks.t2_bib import check_t2
from .checks.t4_claims import check_claims
from .checks.t4_coherence import check_t4
from .checks.t5_authoring import check_t5
from .profiles.rules import check_profile
from .context import Context, build_context, unit_ref
from .ledger.db import Ledger
from .project import Project
from .util import canonical_json, sha1

BASIS_KEYS = ("facts", "sources", "bindings", "glossary", "bib", "config", "rubric")

TIER_FUNCS = {"T0": check_t0, "T1": check_t1, "T2": check_t2, "T4": lambda c: check_t4(c) + check_claims(c), "T5": check_t5, "T6": check_profile}


def run_checks(ctx: Context, tiers: tuple[str, ...] = DEFAULT_TIERS, extra: list[Finding] | None = None, backend=None,
               evidence: dict | None = None, **t3kw) -> list[Finding]:
    found: list[Finding] = []
    for t in tiers:
        if t == "T3":
            from .checks.t3_evidence import run_t3
            f3, stats = run_t3(ctx, backend, **t3kw)
            found += f3
            if evidence is not None:
                evidence.update(stats)
        else:
            found += TIER_FUNCS[t](ctx)
    found += extra or []
    # one finding per fingerprint, deterministic order
    uniq = {f.fingerprint(): f for f in found}
    return sorted(uniq.values(), key=sort_key)


def coverage(ctx: Context) -> dict:
    nums = Counter(n.cls for i in ctx.inv if i.unit.kind == "para" for n in i.nums)
    fl = Counter(n.cls for i in ctx.inv if i.unit.kind != "para" for n in i.nums)
    return {
        "files": len(ctx.parsed),
        "units": len(ctx.units),
        "paragraph_units": sum(1 for u in ctx.units if u.kind == "para"),
        "float_units": sum(1 for u in ctx.units if u.kind != "para"),
        "units_with_anchor": sum(1 for u in ctx.units if u.uid),
        "numbers_in_paragraphs": dict(sorted(nums.items())),
        "numbers_in_floats": dict(sorted(fl.items())),
        "citations": sum(len(i.cites) for i in ctx.inv),
        "facts": len(ctx.facts.facts),
        "bindings": len(ctx.bindings),
        "bib_entries": len(ctx.bib),
        "registry_sources": len(ctx.registry),
    }


def report_hash(findings: list[Finding]) -> str:
    return sha1(canonical_json([f.to_dict() for f in findings]), 16)


def _basis_changed(prev_snap: dict, snap: dict) -> bool:
    return any(prev_snap.get(k) != snap.get(k) for k in BASIS_KEYS)


def _carry_t3(led: Ledger, unit_hashes: dict[str, str], prev_h: dict, changed: set[str]) -> list[Finding]:
    """Open T3 findings on unchanged units. Incremental T3 skips those units, so they must be replayed
    or reconcile would mark them fixed."""
    out: list[Finding] = []
    for r in led.list(("open", "decision-needed")):
        if r["tier"] != "T3":
            continue
        ref = r["ref"]
        if ref and ref in changed:
            continue
        if ref and prev_h.get(ref) != unit_hashes.get(ref):
            continue
        out.append(Finding(r["check_id"], r["level"], r["ref"], r["file"], None, r["key"], r["message"], "T3"))
    return out


def audit(project: Project, tiers: tuple[str, ...] = DEFAULT_TIERS, use_ledger: bool = True,
          extra_findings: list[Finding] | None = None, backend=None, incremental: bool = False, **t3kw) -> dict:
    t0 = time.perf_counter()
    ctx = build_context(project)
    unit_hashes = {unit_ref(u): u.hash for u in ctx.units}
    snap = project.snapshot()
    mode, note, changed = "full", "", None
    carried: list[Finding] = []
    if incremental:
        led_peek = Ledger(project)
        last = led_peek.last_run()
        if last is None:
            note = "no-prior-run"
        elif _basis_changed(last[1].get("snapshot") or {}, snap):
            note = "basis-changed"
        else:
            prev_h = last[1].get("unit_hashes") or {}
            changed = {r for r, h in unit_hashes.items() if prev_h.get(r) != h}
            ctx.recheck = changed
            if "T3" in tiers:
                t3kw = dict(t3kw, only_units=sorted(changed) or ["__none__"])
                carried = _carry_t3(led_peek, unit_hashes, prev_h, changed)
            mode, note = "incremental", f"{len(changed)}/{len(unit_hashes)} units changed"
        led_peek.close()
    evidence: dict = {}
    findings = run_checks(ctx, tiers, extra_findings, backend, evidence, **t3kw) + carried
    gate_levels = set(project.cfg["gate"]["blocking_levels"])
    report: dict = {
        "engine": __version__, "rubric": RUBRIC_VERSION, "project": project.cfg["project"],
        "tiers": list(tiers), "snapshot": snap, "coverage": coverage(ctx),
        "cost": {
            "seconds": round(time.perf_counter() - t0, 3),
            "mode": mode,
            "note": note,
            "units_total": len(unit_hashes),
            "units_changed": len(changed) if changed is not None else len(unit_hashes),
        },
    }
    if evidence:
        report["evidence"] = evidence
    states: dict[str, dict] = {}
    if use_ledger:
        led = Ledger(project)
        last = led.last_run()
        run_id = led.next_run_id()
        prev = last[1] if last else None
        rec = led.reconcile(run_id, findings, set(tiers), unit_hashes, prev, snap)
        for r in led.list():
            states[r["fp"]] = {"state": r["state"], "cause": r["cause"], "regression": bool(r["regression"]), "first_seen": r["first_seen"]}
        vcfg = project.cfg.get("verifier") or {}
        manifest = {"run": run_id, "engine": __version__, "snapshot": snap, "tiers_run": list(tiers), "unit_hashes": unit_hashes,
                    "coverage": report["coverage"], "stats": rec["stats"],
                    "verifier": {"backend": vcfg.get("backend"), "model": vcfg.get("model"),
                                 "provider": vcfg.get("provider")} if vcfg.get("backend") or vcfg.get("model") else None}
        report.update(run=run_id, ledger=rec["stats"], new_causes=Counter(rec["causes"].values()))
        out = []
        for f in findings:
            d = f.to_dict()
            d.update(states.get(d["fingerprint"], {"state": "open"}))
            out.append(d)
        report["findings"] = out
        report["new_causes"] = dict(report["new_causes"])
        report["unexplained"] = sorted(fp for fp, c in rec["causes"].items() if c == "UNEXPLAINED")
        led.save_run(run_id, manifest, report_hash(findings))
        led.close()
    else:
        report["findings"] = [dict(f.to_dict(), state="open") for f in findings]
    live = [d for d in report["findings"] if d["state"] in ("open", "decision-needed")]
    report["counts"] = dict(Counter(d["level"] for d in live))
    report["checks_fired"] = dict(Counter(d["check"] for d in live))
    blocking = [d for d in live if d["level"] in gate_levels]
    report["gate"] = {"passed": not blocking, "blocking": len(blocking), "levels": sorted(gate_levels)}
    report["report_hash"] = report_hash(findings)
    cost = report["cost"]
    cost["seconds"] = round(time.perf_counter() - t0, 3)
    if evidence:
        cost["t3_calls"] = evidence.get("calls", 0)
        cost["t3_cached"] = evidence.get("cached", 0)
        cost["tokens_in"] = evidence.get("tokens_in", 0)
        cost["tokens_out"] = evidence.get("tokens_out", 0)
    return report


def det_check(project: Project, tiers: tuple[str, ...] = DEFAULT_TIERS, backend=None) -> dict:
    """DET-01: two independent builds of the context must give identical findings."""
    a = run_checks(build_context(project), tiers, backend=backend)
    b = run_checks(build_context(project), tiers, backend=backend)
    ha, hb = report_hash(a), report_hash(b)
    return {"identical": ha == hb, "hash": ha, "findings": len(a)}
