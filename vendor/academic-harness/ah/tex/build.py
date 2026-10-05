"""Build wrapper and compile-log parser (design 4.5).

Runs the project's build command and turns the log into findings. Errors carry file:line (via
-file-line-error) so they land on a unit. Warnings that carry no location are mapped by content
(a duplicate PDF destination, an undefined \\fact key) or reported at document level.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from ..checks.base import Finding, make
from ..context import Context, unit_ref
from ..project import Project

DEFAULT_CMD = ["latexmk", "-pdf", "-interaction=nonstopmode", "-file-line-error", "-output-directory=build"]


def run_build(project: Project, view: str | None = None, timeout: int = 600) -> dict:
    view = view or project.cfg["tex"]["views"][0]
    cmd = list(project.cfg.get("build", {}).get("cmd") or DEFAULT_CMD) + [view]
    if shutil.which(cmd[0]) is None:
        return {"ok": False, "error": f"{cmd[0]} not found", "log": ""}
    (project.tex_root / "build").mkdir(exist_ok=True)
    import os
    env = dict(os.environ)
    # latexmk runs bibtex inside the output directory, so point it back at the TeX root
    env["BIBINPUTS"] = f"{project.tex_root}:" + env.get("BIBINPUTS", "")
    env["TEXINPUTS"] = f"{project.tex_root}//:" + env.get("TEXINPUTS", "")
    env["max_print_line"] = "10000"      # TeX hard-wraps log lines at 79 chars, which cuts file paths in half
    env["error_line"] = "254"
    env["half_error_line"] = "238"
    p = subprocess.run(cmd, cwd=project.tex_root, capture_output=True, text=True, timeout=timeout, env=env)
    log_path = project.tex_root / "build" / (Path(view).stem + ".log")
    log = log_path.read_text(errors="replace") if log_path.exists() else p.stdout
    return {"ok": p.returncode == 0, "returncode": p.returncode, "log": log, "view": view}


def parse_log(log: str) -> dict:
    """Pure function over log text, so it is unit-testable without TeX."""
    errors = [{"file": m.group(1), "line": int(m.group(2)), "msg": m.group(3).strip()}
              for m in re.finditer(r"^(\S+?\.tex):(\d+): (.+)$", log, re.M)]
    bare = [m.group(1).strip() for m in re.finditer(r"^! (.+)$", log, re.M)] if not errors else []
    dest = sorted(set(re.findall(r"destination with the same identifier \(name\{([^}]+)\}\)", log)))
    undefined_facts = sorted(set(re.findall(r"AH warning: undefined fact (\S+)", log)))
    undef_refs = sorted(set(re.findall(r"Reference `([^']+)' on page \d+ undefined", log)))
    undef_cites = sorted(set(re.findall(r"Citation `([^']+)' on page \d+ undefined", log)))
    overfull = len(re.findall(r"^Overfull \\[hv]box", log, re.M))
    return {"errors": errors, "bare_errors": bare, "duplicate_destinations": dest, "undefined_facts": undefined_facts,
            "undefined_refs": undef_refs, "undefined_cites": undef_cites, "overfull": overfull}


def log_findings(ctx: Context, parsed: dict) -> list[Finding]:
    cfg, out = ctx.cfg, []

    def add(*a):
        f = make(cfg, *a)
        if f:
            out.append(f)

    known = sorted({u.file for u in ctx.units})
    for e in parsed["errors"]:
        rel = e["file"][2:] if e["file"].startswith("./") else e["file"]
        if rel not in known:                      # wrapped or odd path: accept a unique suffix match
            cand = [k for k in known if k.endswith(rel) or rel.endswith(k) or k.endswith(rel.lstrip("/"))]
            rel = cand[0] if len(cand) == 1 else rel
        ref = next((unit_ref(u) for u in ctx.units if u.file == rel and u.start <= e["line"] <= u.end), None)
        add("TEX-01", ref, rel, e["line"], f"err:{e['msg'][:60]}", f"LaTeX error: {e['msg']}")
    for m in parsed["bare_errors"]:
        add("TEX-01", None, None, None, f"err:{m[:60]}", f"LaTeX error: {m}")
    for d in parsed["duplicate_destinations"]:
        add("TEX-03", None, None, None, f"dest:{d}", f"duplicate PDF destination '{d}' (hyperref)")
    for k in parsed["undefined_facts"]:
        add("NUM-005", None, None, None, f"logfact:{k}", f"\\fact{{{k}}} is undefined in the compiled document")
    if parsed["overfull"]:
        add("TEX-04", None, None, None, "overfull", f"{parsed['overfull']} overfull box warning(s) in the log")
    return out
