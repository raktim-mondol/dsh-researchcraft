"""T4: coherence. Terminology, scope, mirrored facts, and absence claims (design 6.5, 6.3)."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from ..context import Context, unit_ref
from ..tex.text import RE_FACT
from ..util import collapse_ws, sha1
from .base import Finding, make
from .t1_numeric import _plain


def check_t4(ctx: Context) -> list[Finding]:
    cfg, out = ctx.cfg, []

    def add(*a):
        f = make(cfg, *a)
        if f:
            out.append(f)

    # ---- COH-01: banned terms ----
    for term in ctx.glossary:
        banned = term.get("banned") or []
        for u in ctx.units:
            text = _plain(u.raw)
            for b in banned:
                pat = b if term.get("regex") else re.escape(b)
                m = re.search(pat, text, re.I)
                if m:
                    add("COH-01", unit_ref(u), u.file, u.start, f"term:{b}",
                        f"'{m.group(0)}' should be '{term.get('canonical')}'" + (f" ({term['note']})" if term.get("note") else ""))

    # ---- COH-02: scope of cited sources per file ----
    scope = cfg.get("scope") or {}
    if scope and ctx.registry:
        for i in ctx.inv:
            u = i.unit
            allowed = None
            for pat, tags in scope.items():
                if fnmatch.fnmatch(u.file, pat):
                    allowed = set(tags)
            if allowed is None:
                continue
            for key, _s in i.cites:
                src = ctx.registry.get(key)
                if not src:
                    continue
                tags = set(src.get("tags") or [])
                if src.get("class") == "context":
                    tags.add("context")
                allow = [k for pat, ks in (cfg.get("scope_allow") or {}).items() if fnmatch.fnmatch(u.file, pat) for k in ks]
                if key in allow:
                    continue                      # an exception the author accepted in ah.yaml (a protected file), not an agent's
                if not (tags & allowed):
                    add("COH-02", unit_ref(u), u.file, u.start, f"scope:{key}",
                        f"'{key}' has tags {sorted(tags) or ['(none)']}; this file allows {sorted(allowed)}")

    # ---- COH-03: each mirror group must state the fact in at least one of its files ----
    for m in cfg.get("mirrors", []):
        ref = m["fact"]
        try:
            want = ctx.facts.number_text(ref)
        except Exception:
            continue
        for pat in m.get("files", []):
            members = [rel for rel in sorted(ctx.tex_texts) if fnmatch.fnmatch(rel, pat)]
            if not members:
                add("COH-03", None, pat, None, f"mirror:{ref}:{pat}", f"no file matches '{pat}', which must state {ref}")
                continue
            ok = False
            for rel in members:
                text = ctx.tex_texts[rel]
                keys = [k.strip() for k in RE_FACT.findall(text)]
                macro_hit = any(k == ref or (k.partition(".")[0] == ref.partition(".")[0] and
                                             (k.partition(".")[2] or ctx.facts.facts[k.partition(".")[0]].default_variant()) ==
                                             (ref.partition(".")[2] or ctx.facts.facts[ref.partition(".")[0]].default_variant()))
                                for k in keys if k.partition(".")[0] in ctx.facts.facts)
                lit_hit = bool(re.search(r"(?<![\d.])" + re.escape(want) + r"(?![\d]|\.\d)", _plain(text)))
                ok = ok or macro_hit or lit_hit
            if not ok:
                add("COH-03", None, pat, None, f"mirror:{ref}:{pat}", f"no file in '{pat}' states {ref} ({ctx.facts.plain(ref)})")

    # ---- CLM-04: absence and count claims, checked by search over the sources ----
    root = ctx.project.root
    for a in cfg.get("absence", []):
        terms = [t for t in a.get("terms", []) if t]
        if not terms:
            continue
        pat = re.compile("|".join(re.escape(t) for t in terms), re.I)
        need = re.compile(a["near"], re.I | re.S) if a.get("near") else None
        files = []
        for g in a.get("corpus_glob", []) if isinstance(a.get("corpus_glob"), list) else [a.get("corpus_glob")]:
            if g:
                files += sorted(root.glob(g))
        ft = a.get("files_from_tsv")      # restrict to the studies a table lists, e.g. the included ones
        if ft:
            import csv
            tp = root / ft["file"]
            if tp.exists():
                with tp.open(newline="", encoding="utf-8") as fh:
                    for r in csv.DictReader(fh, delimiter="\t"):
                        cell = (r.get(ft["column"]) or "").strip()
                        if cell:
                            files.append(root / ft.get("root", "") / cell)
        excl = a.get("exclude", [])
        hits = []
        for f in sorted(set(files)):
            rel = f.relative_to(root).as_posix()
            if any(fnmatch.fnmatch(rel, e) for e in excl) or not f.is_file():
                continue
            text = f.read_text(errors="replace")
            for m in pat.finditer(text):
                win = text[max(0, m.start() - 160): m.end() + 160]
                if need and not need.search(win):
                    continue
                hits.append((rel, text.count("\n", 0, m.start()) + 1, collapse_ws(win)))
                break  # one hit per file
        limit = int(a.get("max", 0))
        if len(hits) > limit:
            shown = "; ".join(f"{h[0]}:{h[1]}" for h in hits[:5])
            add("CLM-04", a.get("unit"), a.get("file"), None, f"absence:{a['id']}",
                f"claim '{a.get('claim', a['id'])}' allows at most {limit} source(s); found {len(hits)}: {shown}")
    return out
