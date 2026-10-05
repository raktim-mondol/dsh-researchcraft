"""T3: evidence. Cited claims against the cited sources (design 6.3, 6.4).

EVD-02 is deterministic: a number in a cited sentence that occurs nowhere in the cited sources.
EVD-01 needs a model backend: the verifier reads the best passages and its answer is quote-checked.
Neither closes a finding by itself; a model verdict is evidence for a person, not a verdict on the paper.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..claim_sidecar import load_all as load_sidecars
from ..claims import Claim, extract_claims
from ..context import Context
from ..sources.index import Index
from ..sources.registry import doi_index, load_registry, resolve_all, source_map
from ..verifier.backends import Backend
from ..verifier.verify import Cache, Result, number_found, verify
from .base import Finding, make

DEFAULT_KINDS = {"numeric-cited", "comparative", "causal", "attributive"}
LEVEL_BY_VERDICT = {"NOT_SUPPORTED": "major", "PARTIAL": "minor", "NOT_IN_SOURCE": "minor", "CONTESTED": "info"}


def run_t3(ctx: Context, backend: Backend | None = None, use_cache: bool = True, limit: int = 0,
           only_files: list[str] | None = None, only_units: list[str] | None = None) -> tuple[list[Finding], dict]:
    cfg, p = ctx.cfg, ctx.project
    vcfg = cfg.get("verifier") or {}
    kinds = set(vcfg.get("kinds") or DEFAULT_KINDS)
    claims = [c for c in extract_claims(ctx, kinds) if (not only_files or c.file in only_files) and (not only_units or c.unit in only_units)]
    if limit:
        claims = claims[:limit]
    reg, smap, idx, dois = load_registry(p), source_map(p), Index(p), doi_index(p)
    sidecars = {c["id"]: c for sc in load_sidecars(p).values() for c in sc.get("claims", [])}
    out: list[Finding] = []
    stats = {"claims": len(claims), "with_source": 0, "no_source": 0, "number_checked": 0, "number_missing": 0, "verified": 0,
             "verdicts": {}, "cached": 0, "calls": 0, "tokens_in": 0, "tokens_out": 0, "errors": 0}

    def add(check, claim: Claim, key, msg, level=None):
        f = make(cfg, check, claim.unit, claim.file, claim.line, key, msg)
        if f:
            if level and check not in (cfg.get("levels") or {}):
                f.level = level
            out.append(f)

    unresolved: set[str] = set()
    work: list[tuple[Claim, list]] = []
    for c in claims:
        srcs = []
        for k in c.cites:
            paths = resolve_all(p, k, reg, smap, ctx.bib, dois)
            if not paths:
                unresolved.add(k)
                continue
            idx.ensure(k, paths)
            srcs.append(k)
        c.sources = srcs
        if not srcs:
            stats["no_source"] += 1
            continue
        stats["with_source"] += 1
        # --- EVD-02 (no model): every number must occur somewhere in a cited source ---
        if c.numbers:
            stats["number_checked"] += 1
            have = set().union(*[idx.all_text_numbers(k) for k in srcs])
            rec = sidecars.get(c.id)
            if rec and rec.get("status") != "stale":      # numbers inside a bound passage count as found
                import re as _re
                for b in rec.get("bindings", []):
                    if b.get("type") == "passage":
                        have |= set(_re.findall(r"\d+(?:\.\d+)?", b["quote"].replace(",", "")))
            missing = [n for n in c.numbers if not number_found(n, have)]
            if missing:
                stats["number_missing"] += 1
                add("EVD-02", c, f"num:{c.id}", f"number(s) {', '.join(missing)} not found in {', '.join(srcs)}: \"{c.sentence[:140]}\"")
        rec = sidecars.get(c.id)
        if rec and rec.get("status") == "verified":
            stats["skipped_verified"] = stats.get("skipped_verified", 0) + 1       # the author has confirmed it as written
            continue
        if backend is not None:
            passages = idx.search(srcs, c.sentence, int(vcfg.get("top_k", 3)))
            if rec and rec.get("status") == "bound":      # bound passages are shown first
                from ..sources.index import Passage
                bound = [Passage(b["source"], b["start"], b["end"], b["quote"]) for b in rec.get("bindings", []) if b.get("type") == "passage"]
                passages = bound + [x for x in passages if x.text not in {y.text for y in bound}]
            work.append((c, passages))

    if backend is not None and work:
        cache = Cache(p) if use_cache else None

        def job(item):
            c, passages = item
            return c, passages, verify(c.sentence, c.numbers, passages, backend, cache, bool(vcfg.get("confirm", True)))

        with ThreadPoolExecutor(max_workers=int(vcfg.get("workers", 4))) as ex:
            results = list(ex.map(job, work))
        for c, passages, r in results:
            stats["verified"] += 1
            stats["verdicts"][r.verdict] = stats["verdicts"].get(r.verdict, 0) + 1
            stats["cached"] += int(r.cached)
            stats["calls"] += r.calls
            stats["tokens_in"] += r.tokens_in
            stats["tokens_out"] += r.tokens_out
            if r.verdict == "ERROR":
                stats["errors"] += 1
                add("EVD-03", c, f"err:{c.id}", f"verifier error ({r.error}); this claim was NOT checked: \"{c.sentence[:120]}\"")
            elif r.verdict in LEVEL_BY_VERDICT:
                add("EVD-01", c, f"claim:{c.id}",
                    f"{r.verdict}{' (' + ','.join(r.mismatch) + ')' if r.mismatch else ''} vs {', '.join(c.sources)}: \"{c.sentence[:150]}\""
                    f" | source says: \"{r.quote[:160]}\" [{r.locator}] | {r.note[:120]}", LEVEL_BY_VERDICT[r.verdict])
    if unresolved:
        f = make(cfg, "EVD-04", None, None, None, "no-text", f"{len(unresolved)} cited key(s) have no source text, so their claims cannot be checked: "
                 + ", ".join(sorted(unresolved)[:10]) + (" ..." if len(unresolved) > 10 else ""))
        if f:
            out.append(f)
    stats["unresolved_keys"] = len(unresolved)
    idx.close()
    return out, stats
