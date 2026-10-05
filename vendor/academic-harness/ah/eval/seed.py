"""Seeded-error evaluation (design 12.4).

Take a project, copy it, apply ONE realistic mutation, run the audit, and check that a *new*
finding of the expected check appears. Recall per class is the headline number. A mutation whose
site does not exist in the project is reported "n/a", not as a pass.

The project must audit clean at blocker/major before seeding, otherwise recall is meaningless.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

from ..audit import audit
from ..facts.model import wilson
from ..facts.render import write_build
from ..facts.model import build_facts
from ..project import Project
from ..tex.units import sync_project

Expect = dict  # {"check": id}


@dataclass
class Mutation:
    name: str
    cls: str
    check: str
    apply: Callable[[Project], bool]    # True if applied; False if no site


def _files(p: Project) -> list[Path]:
    return p.prose_files()


def _sub_first(p: Project, pattern: str, repl, flags=0, files=None) -> bool:
    rx = re.compile(pattern, flags)
    for f in files or _files(p):
        t = f.read_text()
        m = rx.search(t)
        if m:
            new = repl(m) if callable(repl) else repl
            f.write_text(t[: m.start()] + new + t[m.end():])
            return True
    return False


# ---------------- mutations ----------------

def m_macro_typo(p):
    return _sub_first(p, r"\\fact\{([^}.]+)([^}]*)\}", lambda m: f"\\fact{{{m.group(1)}zz{m.group(2)}}}")


def m_stale_literal(p):
    facts = yaml.safe_load(p.path("facts").read_text()).get("facts", [])
    for f in facts:
        for s in f.get("superseded") or []:
            pat = r"\\fact\{" + re.escape(f["id"]) + r"(?:\.pct)?\}"
            if _sub_first(p, pat, str(s["text"]) + r"\%"):
                return True
    return False


def m_pct_digit(p):
    def bump(s):
        d = len(s.split(".")[1]) if "." in s else 0
        return f"{float(s) + 7.3:.{d}f}"
    # "p% (a/b)"  or  "a/b (p%)"
    if _sub_first(p, r"(\d+(?:\.\d+)?)(\\?%)\s*\((\d+)/(\d+)\)", lambda m: f"{bump(m.group(1))}{m.group(2)} ({m.group(3)}/{m.group(4)})"):
        return True
    return _sub_first(p, r"(\d+)/(\d+)\s*\((\d+(?:\.\d+)?)(\\?%)\)", lambda m: f"{m.group(1)}/{m.group(2)} ({bump(m.group(3))}{m.group(4)})")


def m_ci_endpoint(p):
    def mut(m):
        lo = float(m.group(2)) - 2.0
        return f"{m.group(1)}{lo:.1f}--{m.group(3)}"
    return _sub_first(p, r"(CI[:=]?\s*\[?\s*)(\d+\.\d+)\s*--\s*(\d+\.\d+)", mut)


def m_sum_break(p):
    # macro sum: swap one operand for a duplicate; literal sum: bump the total
    def mac(m):
        keys = re.findall(r"\\fact\{[^}]+\}", m.group(0))
        return m.group(0).replace(keys[-2], keys[0], 1) if len(keys) >= 3 else m.group(0)
    if _sub_first(p, r"(?:\\fact\{[^}]+\}\+){2,}\\fact\{[^}]+\}=\\fact\{[^}]+\}", mac):
        return True
    return _sub_first(p, r"(\d+(?:\+\d+)+)=(\d+)", lambda m: f"{m.group(1)}={int(m.group(2)) + 3}")


def m_cite_missing(p):
    return _sub_first(p, r"(\\cite[a-z]*\{)([^},]+)", lambda m: m.group(1) + "nonexistent2099x")


def m_scope(p):
    scope = p.cfg.get("scope") or {}
    reg = {s["id"]: s for s in (yaml.safe_load(p.path("sources").read_text()) or {}).get("sources", [])} if p.path("sources").exists() else {}
    import fnmatch
    for pat, allowed in scope.items():
        for f in _files(p):
            if not fnmatch.fnmatch(p.rel(f), pat) or f.name == "index.tex":
                continue
            for sid, s in reg.items():
                tags = set(s.get("tags") or []) | ({"context"} if s.get("class") == "context" else set())
                if tags and not (tags & set(allowed)):
                    t = f.read_text()
                    f.write_text(re.sub(r"\.(\s*)$", f"~\\\\citep{{{sid}}}.\\1", t.rstrip("\n"), count=1) + "\n")
                    return True
    return False


def _anchored(p):
    sync_project(p)
    for f in _files(p):
        if re.search(r"^%% @unit", f.read_text(), re.M):
            yield f


def m_anchor_delete(p):
    for f in _anchored(p):
        lines = f.read_text().split("\n")
        for i, l in enumerate(lines):
            if l.startswith("%% @unit"):
                del lines[i]
                f.write_text("\n".join(lines))
                return True
    return False


def m_anchor_dup(p):
    for f in _anchored(p):
        lines = f.read_text().split("\n")
        idx = [i for i, l in enumerate(lines) if l.startswith("%% @unit")]
        if len(idx) >= 2:
            lines[idx[1]] = lines[idx[0]]
            f.write_text("\n".join(lines))
            return True
    # fall back: duplicate across files
    anchors = [(f, l) for f in _anchored(p) for l in f.read_text().split("\n") if l.startswith("%% @unit")]
    if len(anchors) >= 2:
        f2, _ = anchors[1]
        t = f2.read_text().replace(anchors[1][1], anchors[0][1], 1)
        f2.write_text(t)
        return True
    return False


def m_orphan(p):
    d = p.tex_root / "sections"
    d.mkdir(exist_ok=True)
    (d / "orphan_extra.tex").write_text("This file is not included from any view and nobody will ever read it, which is the point of the test.\n")
    return True


def m_label_in_prose(p):
    for f in _files(p):
        if f.name == "index.tex" or "figures" in f.parts or "tables" in f.parts:
            continue
        t = f.read_text()
        m = re.search(r"([A-Z][^.\n]{25,}\.)(\s)", t)
        if m:
            f.write_text(t[: m.end(1)] + " \\label{sec:moved}" + t[m.end(1):])
            return True
    return False


def m_label_dup(p):
    labs = [(f, l) for f in p.all_tex_files() for l in re.findall(r"\\label\{([^}]+)\}", f.read_text())]
    if not labs:
        return False
    f, lab = labs[0]
    other = next((g for g in _files(p) if g != f and "index" not in g.name), None) or f
    other.write_text(other.read_text().rstrip("\n") + f"\n\n\\label{{{lab}}}\n")
    return True


def m_ref_undefined(p):
    return _sub_first(p, r"\\ref\{([^}]+)\}", lambda m: f"\\ref{{{m.group(1)}_nope}}", files=p.all_tex_files())


def m_banned(p):
    g = yaml.safe_load(p.path("glossary").read_text()).get("terms", []) if p.path("glossary").exists() else []
    for t in g:
        for b in t.get("banned") or []:
            for f in _files(p):
                if f.name != "index.tex" and "tables" not in f.parts and "figures" not in f.parts:
                    f.write_text(f.read_text().rstrip("\n") + f" The {b} was reviewed twice by the authors.\n")
                    return True
    return False


def m_mirror(p):
    for mir in p.cfg.get("mirrors", []):
        fid, _, var = mir["fact"].partition(".")
        pat = r"\\fact\{" + re.escape(mir["fact"]) + r"\}" if var else r"\\fact\{" + re.escape(fid) + r"\}"
        import fnmatch
        done = False
        for g in mir.get("files", []):
            for f in _files(p):
                if fnmatch.fnmatch(p.rel(f), g):
                    t = f.read_text()
                    nt = re.sub(pat, r"\\fact{" + fid + ".n}", t)
                    if nt != t:
                        f.write_text(nt)
                        done = True
        if done:
            return True
    return False


def m_data_drift(p):
    facts = yaml.safe_load(p.path("facts").read_text()).get("facts", [])
    for f in facts:
        spec = (f.get("numerator") or f.get("count") or {}).get("from_tsv") if isinstance(f.get("numerator") or f.get("count"), dict) else None
        if spec and spec.get("where"):
            data = p.root / spec["file"]
            t = data.read_text()
            col, cond = next(iter(spec["where"].items()))
            rows = t.split("\n")
            head = rows[0].split("\t")
            ci = head.index(col)
            want = cond if not isinstance(cond, list) else cond[0]
            for i in range(1, len(rows)):
                cells = rows[i].split("\t")
                if len(cells) > ci and cells[ci] != str(want):
                    cells[ci] = str(want)
                    rows[i] = "\t".join(cells)
                    data.write_text("\n".join(rows))
                    return True
    return False


def _inside(p: Project, f: Path) -> bool:
    """Mutations may only touch files that really live in the scratch copy (never through a symlink)."""
    try:
        f.resolve().relative_to(p.root.resolve())
        return True
    except ValueError:
        return False


def m_absence(p):
    for a in p.cfg.get("absence", []):
        for g in a.get("corpus_glob", []):
            for f in sorted(p.root.glob(g)):
                if not _inside(p, f):
                    continue
                f.write_text(f.read_text().rstrip("\n") + f"\nThe study followed the {a['terms'][0]} guideline.\n")
                return True
    return False


def m_unbound_literal(p):
    for f in _files(p):
        if f.name != "index.tex" and "tables" not in f.parts and "figures" not in f.parts:
            f.write_text(f.read_text().rstrip("\n") + " Of these, 37 studies relied on private data.\n")
            return True
    return False


def m_bib_year(p):
    b = p.bib_files()
    if not b or not p.path("sources").exists():      # BIB-03 compares against a registry; none here
        return False
    t = b[0].read_text()
    m = re.search(r"year\s*=\s*\{(\d{4})\}", t)
    if not m:
        return False
    b[0].write_text(t[: m.start(1)] + str(int(m.group(1)) + 3) + t[m.end(1):])
    return True


def m_retracted(p):
    reg = p.path("sources")
    if not reg.exists():
        return False
    d = yaml.safe_load(reg.read_text())
    if not d.get("sources"):
        return False
    from ..context import build_context
    cited = {k for i in build_context(p).inv for k, _s in i.cites}       # a retraction only matters for a source the text cites
    target = next((x for x in d["sources"] if x["id"] in cited), None)
    if target is None:
        return False
    target["status"] = "retracted"
    reg.write_text(yaml.safe_dump(d, sort_keys=False))
    return True


def m_long_para(p):
    for f in _files(p):
        if f.name != "index.tex" and "tables" not in f.parts and "figures" not in f.parts:
            f.write_text(f.read_text().rstrip("\n") + " " + " ".join(["word"] * 260) + ".\n")
            return True
    return False


def m_macros_not_input(p):
    if not any("\\fact{" in f.read_text() for f in _files(p)):
        return False
    for v in p.view_files():
        t = v.read_text()
        nt = re.sub(r"\\input\{[^}]*macros/facts[^}]*\}\s*\n?", "", t)
        if nt != t:
            v.write_text(nt)
            return True
    return False


def _approved_briefs(p):
    from ..briefs import load_briefs
    return [b for b in load_briefs(p) if b.approved]


def _brief_files(p, b):
    from ..context import build_context
    ctx = build_context(p)
    from ..briefs import target_units
    return sorted({p.tex_root / u.file for u in target_units(ctx, b)})


def m_brief_fact(p):
    for b in _approved_briefs(p):
        fids = {str(f).split(".")[0] for c in b.data.get("claims") or [] for f in c.get("facts") or []}
        if not fids:
            continue
        hit = False
        for f in _brief_files(p, b):
            t = f.read_text()
            nt = t
            for fid in fids:
                nt = re.sub(r"\\fact\{" + re.escape(fid) + r"[^}]*\}", "(n/a)", nt)
            if nt != t:
                f.write_text(nt)
                hit = True
        if hit:
            return True
    return False


def m_brief_length(p):
    for b in _approved_briefs(p):
        if (b.data.get("length") or {}).get("words"):
            for f in _brief_files(p, b):
                f.write_text(f.read_text().rstrip("\n") + " " + " ".join(["word"] * 400) + ".\n")
                return True
    return False


def m_brief_must_not(p):
    for b in _approved_briefs(p):
        if b.data.get("must_not"):
            for f in _brief_files(p, b):
                f.write_text(f.read_text().rstrip("\n") + " This should clearly be required because it proves the point.\n")
                return True
    return False


def _bound_claims(p):
    from ..claim_sidecar import load_all
    return [(uid, c) for uid, sc in load_all(p).items() for c in sc.get("claims", []) if c.get("status") in ("bound", "verified")]


def m_bound_edit(p):
    from ..context import build_context
    ctx = build_context(p)
    for uid, c in _bound_claims(p):
        u = next((x for x in ctx.units if x.uid == uid), None)
        w = re.match(r"\W*(\w+)", c["clause"])
        if u and w:
            f = p.tex_root / u.file
            t = f.read_text()
            if w.group(1) in t:
                f.write_text(t.replace(w.group(1), "Notably " + w.group(1).lower(), 1))
                return True
    return False


def m_binding_source(p):
    from pathlib import Path as _P
    for _uid, c in _bound_claims(p):
        for b in c.get("bindings", []):
            if b.get("type") == "passage":
                src = p.root / b["file"] if not _P(b["file"]).is_absolute() else _P(b["file"])
                if src.exists() and p.root in src.resolve().parents:
                    src.chmod(0o644)
                    src.write_text("Unrelated text that no longer holds the bound passage. " * 5 + "\n")
                    return True
    return False


def m_outline_orphan(p):
    import yaml as _y
    f = p.root / p.cfg["outline"]
    if not f.exists():
        return False
    d = _y.safe_load(f.read_text()) or {}
    d.setdefault("claims", []).append({"id": "t9", "text": "a claim nothing supports", "units": []})
    f.write_text(_y.safe_dump(d, sort_keys=False))
    return True


def m_outline_no_thesis(p):
    import yaml as _y
    f = p.root / p.cfg["outline"]
    if not f.exists():
        return False
    d = _y.safe_load(f.read_text()) or {}
    claims = d.get("claims") or []
    if not claims:
        return False
    for c in claims:
        c["supports"] = [x for x in (c.get("supports") or []) if x != "thesis"]
    f.write_text(_y.safe_dump(d, sort_keys=False))
    return True


def m_outline_bad_supports(p):
    import yaml as _y
    f = p.root / p.cfg["outline"]
    if not f.exists():
        return False
    d = _y.safe_load(f.read_text()) or {}
    claims = d.get("claims") or []
    if not claims:
        return False
    claims[0].setdefault("supports", []).append("no-such-claim")
    f.write_text(_y.safe_dump(d, sort_keys=False))
    return True


def m_plan_stray(p):
    f = p.tex_root / "sections/09_extra/010_new.tex"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("A paragraph that the outline never named.\n")
    return True


def m_review_unchanged(p):
    from ..context import build_context
    from ..reviews import import_review, set_item
    ctx = build_context(p)
    u = next((x for x in ctx.units if x.uid and x.kind == "para"), None)
    if not u:
        return False
    src = p.state_dir / "seed_review.txt"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("1. Please strengthen the argument in this section with more careful wording and evidence.\n")
    import_review(ctx, src, "RS")
    set_item(p, "RS.1", units=[u.uid], status="addressed", response="We revised the section.")
    return True


def m_input_missing(p):
    files = [f for f in _files(p) if "tables" not in f.parts and "figures" not in f.parts]
    f = next((x for x in files if x.name == "index.tex"), files[0] if files else None)      # modular layout, or the first chapter file
    if f is None:
        return False
    f.write_text(f.read_text().rstrip("\n") + "\n\\input{sections/zz_missing_file}\n")
    return True


def m_stray_file(p):
    d = p.root / "sections"
    d.mkdir(exist_ok=True)
    (d / "stray_extra.tex").write_text("A paragraph that was written in the wrong directory, outside the TeX root of the project.\n")
    return p.tex_root != p.root


def m_style_prove(p):
    """Document-level STY-01: a proof verb in a descriptive paragraph."""
    f = p.tex_root / "sections/05_conclusion/010_summary.tex"
    if not f.exists():
        files = _files(p)
        f = files[0] if files else None
    if f is None:
        return False
    f.write_text(f.read_text().rstrip("\n") + " This result proves the finding.\n")
    return True


def m_fact_error(p):
    facts = yaml.safe_load(p.path("facts").read_text())
    for f in facts.get("facts", []):
        w = (f.get("numerator") or f.get("count"))
        if isinstance(w, dict) and w.get("from_tsv", {}).get("where"):
            col = next(iter(w["from_tsv"]["where"]))
            w["from_tsv"]["where"] = {col + "_missing": "Y"}
            p.path("facts").write_text(yaml.safe_dump(facts, sort_keys=False))
            return True
    return False


MUTATIONS = [
    Mutation("macro-key-typo", "undefined macro key", "NUM-005", m_macro_typo),
    Mutation("stale-literal", "stale basis (superseded value reappears)", "STALE-01", m_stale_literal),
    Mutation("percent-digit", "percentage no longer matches its fraction", "NUM-004", m_pct_digit),
    Mutation("ci-endpoint", "confidence interval endpoint wrong", "NUM-004", m_ci_endpoint),
    Mutation("sum-break", "sum does not close", "NUM-004", m_sum_break),
    Mutation("unbound-literal", "new literal number with no fact", "NUM-001", m_unbound_literal),
    Mutation("data-drift", "data changed, macros not rebuilt", "NUM-002", m_data_drift),
    Mutation("fact-build-error", "fact cannot be computed", "NUM-002", m_fact_error),
    Mutation("macros-not-input", "fact macros used but the macro file is not loaded", "NUM-007", m_macros_not_input),
    Mutation("cite-missing", "citation key not in bibliography", "BIB-01", m_cite_missing),
    Mutation("bib-year", "bibliography year differs from registry", "BIB-03", m_bib_year),
    Mutation("retracted-source", "cited source retracted", "BIB-04", m_retracted),
    Mutation("scope-violation", "out-of-scope source cited", "COH-02", m_scope),
    Mutation("banned-term", "banned term introduced", "COH-01", m_banned),
    Mutation("mirror-drop", "mirrored fact dropped from a section", "COH-03", m_mirror),
    Mutation("absence-counterexample", "'no study ...' claim gets a counterexample", "CLM-04", m_absence),
    Mutation("brief-fact-dropped", "a fact the approved brief requires is removed from the text", "BRF-01", m_brief_fact),
    Mutation("brief-too-long", "text far over the brief's length", "BRF-02", m_brief_length),
    Mutation("brief-must-not", "causal or recommending language the brief forbids", "STY-01", m_brief_must_not),
    Mutation("style-prove", "proof verb in descriptive prose", "STY-01", m_style_prove),
    Mutation("bound-claim-edited", "a bound claim is reworded", "CLM-05", m_bound_edit),
    Mutation("binding-source-changed", "the source passage a claim is bound to disappears", "EVD-05", m_binding_source),
    Mutation("outline-claim-unsupported", "outline claim loses its supporting unit", "ARG-01", m_outline_orphan),
    Mutation("outline-thesis-unsupported", "no outline claim supports the thesis", "ARG-03", m_outline_no_thesis),
    Mutation("outline-supports-unknown", "outline claim supports a missing id", "ARG-04", m_outline_bad_supports),
    Mutation("plan-stray-file", "new section file the outline does not name", "PLN-01", m_plan_stray),
    Mutation("review-addressed-unchanged", "a review item is marked addressed but nothing changed", "REV-01", m_review_unchanged),
    Mutation("anchor-delete", "unit anchor deleted", "UNIT-01", m_anchor_delete),
    Mutation("anchor-duplicate", "unit anchor duplicated", "UNIT-01", m_anchor_dup),
    Mutation("input-missing", "an \\input names a file that does not exist", "TEX-05", m_input_missing),
    Mutation("stray-file", "a TeX file written outside the TeX root", "LAT-11", m_stray_file),
    Mutation("orphan-file", "file not reachable from any view", "UNIT-02", m_orphan),
    Mutation("label-in-prose", "label moved into running prose", "LAT-06", m_label_in_prose),
    Mutation("label-duplicate", "label defined twice", "TEX-03", m_label_dup),
    Mutation("ref-undefined", "reference to a missing label", "TEX-02", m_ref_undefined),
    Mutation("paragraph-too-long", "paragraph far over the word limit", "LAT-03", m_long_para),
]


def _copy(src: Path, dst: Path):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".ah", "build", "__pycache__", ".git", "sources/fulltext"), symlinks=True)
    ledger = src / ".ah" / "ledger.sqlite"
    if ledger.exists():
        (dst / ".ah").mkdir(parents=True, exist_ok=True)
        shutil.copy2(ledger, dst / ".ah" / "ledger.sqlite")


def _prepare(work: Path) -> Project:
    p = Project(work)
    fs, errs = build_facts(p)
    if not errs and fs.facts:
        write_build(p, fs)
    sync_project(p)
    return p


def _fps(rep) -> dict:
    return {f["fingerprint"]: f for f in rep["findings"]}


def run_seed(project_dir: Path, only: str | None = None, json_out: bool = False) -> int:
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        base_dir = Path(tmp) / "base"
        _copy(Path(project_dir), base_dir)
        base = _prepare(base_dir)
        base_rep = audit(base, use_ledger=True)
        base_fps = _fps(base_rep)
        bad = [f for f in base_rep["findings"] if f["level"] in ("blocker", "major") and f.get("state") in ("open", "decision-needed")]
        for mu in MUTATIONS:
            if only and mu.name != only:
                continue
            work = Path(tmp) / mu.name
            _copy(Path(project_dir), work)
            p = _prepare(work)
            applied = False
            try:
                applied = mu.apply(p)
            except Exception as e:  # a crashing mutation is a harness bug, report it
                results.append({"mutation": mu.name, "class": mu.cls, "expected": mu.check, "status": "ERROR", "detail": repr(e)})
                continue
            if not applied:
                results.append({"mutation": mu.name, "class": mu.cls, "expected": mu.check, "status": "n/a"})
                continue
            rep = audit(Project(work), use_ledger=True)
            new = [f for fp, f in _fps(rep).items() if fp not in base_fps and f.get("state") in ("open", "decision-needed")]
            hit = [f for f in new if f["check"] == mu.check]
            results.append({"mutation": mu.name, "class": mu.cls, "expected": mu.check,
                            "status": "detected" if hit else "MISSED",
                            "also": sorted({f["check"] for f in new} - {mu.check}),
                            "example": hit[0]["message"][:140] if hit else ""})
    app = [r for r in results if r["status"] in ("detected", "MISSED")]
    det = [r for r in app if r["status"] == "detected"]
    summary = {"baseline_blocker_major": len(bad), "applicable": len(app), "detected": len(det),
               "recall": (len(det) / len(app)) if app else None, "not_applicable": sum(r["status"] == "n/a" for r in results),
               "errors": sum(r["status"] == "ERROR" for r in results), "results": results}
    if json_out:
        print(json.dumps(summary, indent=1))
    else:
        print(f"baseline findings at blocker/major: {len(bad)} (must be 0)")
        for r in results:
            print(f"  {r['status']:9} {r['mutation']:24} expect {r['expected']:9} {r['class']}" + (f"  [+{','.join(r['also'])}]" if r.get("also") else ""))
        print(f"recall: {len(det)}/{len(app)} applicable"
              + (f" = {100 * len(det) / len(app):.0f}%" if app else "") + f"; not applicable: {summary['not_applicable']}; errors: {summary['errors']}")
    return 0 if (not bad and app and len(det) == len(app) and not summary["errors"]) else 1
