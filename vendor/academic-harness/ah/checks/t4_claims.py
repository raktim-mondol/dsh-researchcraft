"""T4: claim bindings (design 6.3). A claim's record must still hold: its passage is in the source, its text has not drifted."""
from __future__ import annotations

from ..claim_sidecar import broken_bindings, load_all
from ..claims import extract_claims
from ..context import Context
from .base import Finding, make


def check_claims(ctx: Context) -> list[Finding]:
    cfg, p, out = ctx.cfg, ctx.project, []
    sidecars = load_all(p)

    def add(*a):
        f = make(cfg, *a)
        if f:
            out.append(f)

    current = {c.id for c in extract_claims(ctx, granularity="cite")}
    for uid, sc in sidecars.items():
        file = next((u.file for u in ctx.units if (u.uid or "") == uid), None)
        for c in sc.get("claims", []):
            relied_on = c.get("status") in ("bound", "verified", "stale") or c.get("bindings")
            # stale if the sidecar says so, or if the clause is no longer in the text (edited since, even if nobody re-ran extract)
            if relied_on and (c.get("status") == "stale" or c["id"] not in current):
                add("CLM-05", uid, file, None, f"stale:{c['id']}",
                    f"the clause changed after it was bound or verified; re-bind and re-verify: \"{c.get('clause', '')[:110]}\"")
    for uid, c, b, why in broken_bindings(ctx):
        file = next((u.file for u in ctx.units if (u.uid or "") == uid), None)
        add("EVD-05", uid, file, None, f"binding:{c['id']}:{b['source']}:{b['start']}",
            f"claim {c['id']} is bound to {b['source']} lines {b['start']}-{b['end']}, but {why}")
    if (cfg.get("claims_policy") or {}).get("require_binding"):
        ok = {c["id"] for sc in sidecars.values() for c in sc.get("claims", []) if c.get("status") in ("bound", "verified")}
        for c in extract_claims(ctx, {"numeric-cited", "comparative", "causal", "attributive"}):
            if c.id not in ok:
                add("CLM-02", c.unit, c.file, c.line, f"unbound:{c.id}", f"cited claim has no binding: \"{c.sentence[:110]}\" ({', '.join(c.cites)})")
    return out
