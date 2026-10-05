"""Plan workflow (design 8.1): the agent proposes an outline; the author approves; nothing is written yet.

plans/<id>.yaml is a pending outline. `ah plan approve` (human-only) writes outline.yaml
and records a file snapshot so PLN-01 can see prose that appeared afterwards.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from .briefs import load_briefs
from .context import Context
from .outline import load_outline, save_outline, section_matches
from .project import Project
from .util import sha1


def plans_dir(p: Project) -> Path:
    return p.root / p.cfg.get("plans", "plans")


def lock_path(p: Project) -> Path:
    return p.state_dir / "plan_lock.json"


def outline_sha(p: Project) -> str:
    f = p.root / p.cfg["outline"]
    return sha1(f.read_bytes()) if f.exists() else ""


def current_prose(p: Project) -> list[str]:
    return sorted(p.rel(f) for f in p.prose_files())


def load_lock(p: Project) -> dict:
    f = lock_path(p)
    if f.exists():
        return json.loads(f.read_text())
    return {}


def write_lock(p: Project, files: list[str] | None = None, sha: str | None = None) -> dict:
    p.state_dir.mkdir(parents=True, exist_ok=True)
    lock = load_lock(p)
    if files is not None:
        lock["files"] = list(files)
    if sha is not None:
        lock["outline_sha"] = sha
    lock_path(p).write_text(json.dumps(lock, indent=1) + "\n")
    return lock


def ensure_lock(p: Project) -> dict:
    """Grandfather the current prose files the first time Plan checks run."""
    lock = load_lock(p)
    if "files" not in lock:
        lock = write_lock(p, files=current_prose(p))
    return lock


def load_proposals(p: Project) -> list[dict]:
    d = plans_dir(p)
    out = []
    for f in sorted(d.glob("*.yaml")) if d.exists() else []:
        rec = yaml.safe_load(f.read_text()) or {}
        rec.setdefault("id", f.stem)
        rec["_path"] = str(f)
        out.append(rec)
    return out


def get_proposal(p: Project, pid: str) -> dict | None:
    return next((r for r in load_proposals(p) if r.get("id") == pid), None)


def propose(p: Project, data: dict) -> dict:
    """Write a pending proposal. Does not touch outline.yaml."""
    pid = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(data.get("id") or "")).strip("-")
    if not pid:
        raise ValueError("a plan proposal needs an id")
    outline = data.get("outline") or {k: v for k, v in data.items() if k not in ("id", "outline")}
    if not outline:
        raise ValueError("a plan proposal needs an outline (thesis, sections, claims)")
    d = plans_dir(p)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{pid}.yaml"
    if path.exists():
        raise ValueError(f"plan proposal '{pid}' already exists")
    rec = {"id": pid, "status": "pending", "outline": outline}
    path.write_text(yaml.safe_dump(rec, sort_keys=False, allow_unicode=True))
    return rec


def new_outline(p: Project, data: dict) -> dict:
    """Create or replace a missing outline as a draft. Will not overwrite an existing file."""
    f = p.root / p.cfg["outline"]
    if f.exists():
        raise ValueError(f"{p.cfg['outline']} already exists; propose a change with `ah plan propose`")
    ol = {**data, "status": "draft"}
    save_outline(p, ol)
    write_lock(p, files=current_prose(p))
    return ol


def approve(p: Project, pid: str) -> dict:
    rec = get_proposal(p, pid)
    if rec is None:
        raise ValueError(f"no plan proposal '{pid}'")
    if rec.get("status") != "pending":
        raise ValueError(f"proposal '{pid}' is {rec.get('status')}, not pending")
    ol = dict(rec.get("outline") or {})
    ol["status"] = "approved"
    save_outline(p, ol)
    rec["status"] = "accepted"
    Path(rec["_path"]).write_text(yaml.safe_dump({k: v for k, v in rec.items() if k != "_path"},
                                                 sort_keys=False, allow_unicode=True))
    write_lock(p, files=current_prose(p), sha=outline_sha(p))
    return ol


def diff_text(p: Project, pid: str) -> str:
    rec = get_proposal(p, pid)
    if rec is None:
        raise ValueError(f"no plan proposal '{pid}'")
    cur = load_outline(p)
    new = rec.get("outline") or {}
    return ("--- outline.yaml\n" + yaml.safe_dump(cur, sort_keys=False, allow_unicode=True)
            + "+++ proposal " + pid + "\n" + yaml.safe_dump(new, sort_keys=False, allow_unicode=True))


def _brief_files(p: Project) -> set[str]:
    out = set()
    for b in load_briefs(p):
        if not b.approved:
            continue
        f = str(b.data.get("file") or "").lstrip("./")
        if f:
            out.add(f)
    return out


def check_plan(ctx: Context) -> list[dict]:
    """PLN-01 stray or early prose under sections/; PLN-02 approved outline edited outside approve."""
    p, out = ctx.project, []
    o = load_outline(p)
    lock = load_lock(p)
    approved = o.get("status") == "approved"
    allowed_briefs = _brief_files(p)
    sections = o.get("sections") or []
    draft = o.get("status") == "draft"

    for rel in current_prose(p):
        if not rel.startswith("sections/"):
            continue
        if rel in allowed_briefs:
            continue
        matched = [s for s in sections if section_matches(rel, s.get("file", ""))]
        if not matched:
            out.append({"check": "PLN-01", "level": "blocker", "key": f"new:{rel}", "ref": None, "file": rel,
                        "message": f"new prose file {rel} is not in the approved outline and has no approved brief"})
            continue
        if draft and matched and all(s.get("planned") for s in matched):
            out.append({"check": "PLN-01", "level": "blocker", "key": f"early:{rel}", "ref": None, "file": rel,
                        "message": f"{rel} is planned but the outline is still a draft; do not write it yet"})

    if approved and lock.get("outline_sha") and lock["outline_sha"] != outline_sha(p):
        out.append({"check": "PLN-02", "level": "major", "key": "outline-hash", "ref": None, "file": p.cfg["outline"],
                    "message": "approved outline.yaml changed outside `ah plan approve`"})
    return out
