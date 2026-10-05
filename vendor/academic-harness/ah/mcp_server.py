"""Stdio MCP front for non-Pi agents (design 10.2, D8).

JSON-RPC 2.0 with Content-Length framing (MCP 2024-11-05). Also accepts one JSON object
per line. Author-only acts (waive, approve, accept) are not exposed: same rule as the Pi
guard. The engine does not import Pi.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, BinaryIO

from . import __version__

PROTOCOL = "2024-11-05"
KNOWN_PROTOCOLS = {PROTOCOL, "2025-03-26", "2025-06-18"}

TOOLS: list[dict] = [
    {"name": "ah_config", "description": "Effective project configuration (paths, gate, profile).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ah_state", "description": "Paper-state card: conventions, facts, open findings, briefs.",
     "inputSchema": {"type": "object", "properties": {"unit": {"type": "string"}}}},
    {"name": "ah_inventory", "description": "Counts of units, numbers, citations, facts.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ah_catalogue", "description": "List of check ids, tiers and default levels.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ah_profile_list", "description": "Installed document-type profiles.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ah_check", "description": "Run deterministic checks without writing the ledger. Returns JSON.",
     "inputSchema": {"type": "object", "properties": {
         "tiers": {"type": "string", "description": "Comma list, e.g. T0,T1,T2,T4"},
         "files": {"type": "string", "description": "Comma list of files to restrict the report"},
     }}},
    {"name": "ah_audit", "description": "Run checks and reconcile with the ledger. Returns JSON.",
     "inputSchema": {"type": "object", "properties": {
         "tiers": {"type": "string"},
         "no_ledger": {"type": "boolean"},
     }}},
    {"name": "ah_findings", "description": "List ledger findings, optionally filtered by state.",
     "inputSchema": {"type": "object", "properties": {
         "state": {"type": "string", "description": "Comma list: open,waived,fixed,decision-needed"},
     }}},
    {"name": "ah_facts_list", "description": "List facts and their rendered variants.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ah_facts_build", "description": "Rebuild macros/facts.tex from facts.yaml.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ah_units_sync", "description": "Insert or refresh %% @unit anchors on prose files.",
     "inputSchema": {"type": "object", "properties": {"check": {"type": "boolean"}}}},
    {"name": "ah_source_list", "description": "List registered sources.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ah_plan_show", "description": "Show the locked outline and pending plan proposals.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ah_migrate", "description": "Plan (default) or apply an overlay that puts ah.yaml on an existing LaTeX tree. Apply needs confirm=true.",
     "inputSchema": {"type": "object", "properties": {
         "dir": {"type": "string", "description": "LaTeX tree; default is the MCP project root"},
         "profile": {"type": "string"},
         "apply": {"type": "boolean"},
         "confirm": {"type": "boolean", "description": "Required to apply"},
         "facts": {"type": "boolean"},
         "min_repeats": {"type": "integer"},
     }}},
    {"name": "ah_disclosure", "description": "Draft an AI-use statement from unit provenance. Does not approve it.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ah_provenance_list", "description": "List unit provenance records.",
     "inputSchema": {"type": "object", "properties": {
         "author_type": {"type": "string", "enum": ["human", "agent", "mixed", "unknown"]},
     }}},
    {"name": "ah_provenance_record", "description": "Record that an agent (or human) wrote the units in the named files.",
     "inputSchema": {"type": "object", "properties": {
         "files": {"type": "string", "description": "Comma list of prose files"},
         "author_type": {"type": "string", "enum": ["human", "agent", "mixed", "unknown"]},
         "model": {"type": "string"},
         "brief_id": {"type": "string"},
     }, "required": ["files"]}},
]


def _ok(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _err(id_, code, message, data=None):
    e: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        e["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": e}


def _text(obj: Any) -> dict:
    if isinstance(obj, str):
        body = obj
    else:
        body = json.dumps(obj, indent=1, default=str)
    return {"content": [{"type": "text", "text": body}]}


def _tool_error(msg: str) -> dict:
    return {"content": [{"type": "text", "text": msg}], "isError": True}


def _project(root: Path):
    from .project import Project
    return Project(root)


def dispatch_tool(root: Path, name: str, args: dict) -> dict:
    args = args or {}
    try:
        if name == "ah_config":
            p = _project(root)
            return _text({"root": str(p.root), "tex_root": str(p.tex_root), "project": p.cfg["project"],
                          "profile": p.cfg.get("profile"), "protected": p.protected_globs(),
                          "prose": [p.rel(f) for f in p.prose_files()], "views": [p.rel(f) for f in p.view_files()],
                          "gate": p.cfg["gate"]})
        if name == "ah_state":
            from .state import build_state
            return _text(build_state(_project(root), unit=args.get("unit")))
        if name == "ah_inventory":
            from .audit import coverage
            from .context import build_context
            return _text(coverage(build_context(_project(root))))
        if name == "ah_catalogue":
            from .checks.base import CATALOGUE
            return _text({cid: {"tier": t, "level": lvl, "title": title} for cid, (t, lvl, title) in CATALOGUE.items()})
        if name == "ah_profile_list":
            from . import profiles
            return _text([{"name": n, "description": profiles.load(n).description} for n in profiles.names()])
        if name in ("ah_check", "ah_audit"):
            from .audit import audit
            from .checks.base import DEFAULT_TIERS, TIERS
            p = _project(root)
            tiers = tuple(x.strip().upper() for x in str(args.get("tiers") or "").split(",") if x.strip()) or DEFAULT_TIERS
            bad = [t for t in tiers if t not in TIERS]
            if bad:
                return _tool_error(f"unknown tier(s): {bad}")
            use_ledger = name == "ah_audit" and not args.get("no_ledger")
            rep = audit(p, tiers, use_ledger=use_ledger)
            if args.get("files"):
                from .cli import _narrow
                rep = _narrow(rep, str(args["files"]).split(","), brief=True)
            return _text(rep)
        if name == "ah_findings":
            from .ledger.db import Ledger
            led = Ledger(_project(root))
            try:
                states = tuple(s.strip() for s in str(args.get("state") or "").split(",") if s.strip()) or None
                rows = led.list(states)
                return _text([{k: r[k] for k in ("fp", "state", "level", "check_id", "ref", "file", "message")} for r in rows])
            finally:
                led.close()
        if name == "ah_facts_list":
            from .facts.model import build_facts
            p = _project(root)
            fs, errs = build_facts(p)
            return _text({"facts": {fid: {"kind": f.kind, "variants": {v: d["plain"] for v, d in f.variants.items()}}
                                    for fid, f in fs.facts.items()}, "errors": errs})
        if name == "ah_facts_build":
            from .facts.model import build_facts
            from .facts.render import write_build
            p = _project(root)
            fs, errs = build_facts(p)
            if errs:
                return _tool_error("fact errors: " + "; ".join(errs))
            d = write_build(p, fs)
            return _text(d)
        if name == "ah_units_sync":
            from .tex.units import sync_project
            s = sync_project(_project(root), write=not args.get("check"))
            return _text(s)
        if name == "ah_source_list":
            from .sources.registry import load_registry
            return _text(load_registry(_project(root)))
        if name == "ah_plan_show":
            from .outline import load_outline
            from .plan import load_proposals
            p = _project(root)
            pending = [r.get("id") for r in load_proposals(p) if r.get("status") == "pending"]
            return _text({"outline": load_outline(p), "pending": pending})
        if name == "ah_migrate":
            from .migrate import apply, plan
            target = Path(args["dir"]).resolve() if args.get("dir") else root
            pl = plan(target, profile=args.get("profile"), facts=bool(args.get("facts")),
                      min_repeats=int(args.get("min_repeats") or 2))
            public = {k: pl[k] for k in pl if not k.startswith("_")}
            if args.get("apply"):
                if not args.get("confirm"):
                    return _tool_error("ah_migrate apply needs confirm=true (a person must confirm rewriting the overlay)")
                public["applied"] = apply(pl, force=True)
            return _text(public)
        if name == "ah_disclosure":
            from .provenance import draft
            return _text(draft(_project(root)))
        if name == "ah_provenance_list":
            from .ledger.db import Ledger
            led = Ledger(_project(root))
            try:
                rows = [dict(r) for r in led.provenance_list(args.get("author_type"))]
            finally:
                led.close()
            return _text(rows)
        if name == "ah_provenance_record":
            from .provenance import record_files
            files = [x.strip() for x in str(args.get("files") or "").split(",") if x.strip()]
            rows = record_files(_project(root), files, author_type=args.get("author_type") or "agent",
                                model=args.get("model"), brief_id=args.get("brief_id"), by="agent")
            return _text({"recorded": len(rows), "units": [r.get("unit") for r in rows]})
        return _tool_error(f"unknown tool {name}")
    except FileNotFoundError as e:
        return _tool_error(str(e))
    except Exception as e:
        return _tool_error(f"{type(e).__name__}: {e}")


def handle(msg: dict, root: Path) -> dict | None:
    """Handle one JSON-RPC message. Notifications return None."""
    method = msg.get("method")
    id_ = msg.get("id")
    params = msg.get("params") or {}
    if method is None:
        return _err(id_, -32600, "invalid request")
    if id_ is None and method.startswith("notifications/"):
        return None
    if method == "initialize":
        proto = params.get("protocolVersion") or PROTOCOL
        if proto not in KNOWN_PROTOCOLS:
            proto = PROTOCOL
        return _ok(id_, {
            "protocolVersion": proto,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "academic-harness", "version": __version__},
            "instructions": "Academic Harness MCP. Tools wrap the ah engine. Waiving findings and approving briefs/plans/disclosures stay on the CLI and need a human.",
        })
    if method == "ping":
        return _ok(id_, {})
    if method == "tools/list":
        return _ok(id_, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        if not name:
            return _err(id_, -32602, "tools/call needs name")
        return _ok(id_, dispatch_tool(root, name, params.get("arguments") or {}))
    if method in ("resources/list", "resources/templates/list"):
        return _ok(id_, {"resources": []})
    if method == "prompts/list":
        return _ok(id_, {"prompts": []})
    if method == "notifications/initialized":
        return None
    return _err(id_, -32601, f"method not found: {method}")


def _read_message(inp: BinaryIO) -> dict | None:
    first = inp.readline()
    if not first:
        return None
    if first.lstrip().startswith(b"{"):
        return json.loads(first)
    headers = first
    while True:
        line = inp.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        headers += line
    length = None
    for raw in headers.split(b"\n"):
        if raw.lower().startswith(b"content-length:"):
            length = int(raw.split(b":", 1)[1].strip())
    if length is None:
        raise ValueError("MCP message missing Content-Length")
    body = inp.read(length)
    return json.loads(body)


def _write_message(out: BinaryIO, msg: dict) -> None:
    raw = json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode()
    out.write(f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
    out.flush()


def serve(root: Path, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> int:
    inp = stdin or sys.stdin.buffer
    out = stdout or sys.stdout.buffer
    while True:
        try:
            msg = _read_message(inp)
        except Exception as e:
            _write_message(out, _err(None, -32700, f"parse error: {e}"))
            continue
        if msg is None:
            return 0
        try:
            reply = handle(msg, root)
        except Exception as e:
            reply = _err(msg.get("id"), -32603, f"{type(e).__name__}: {e}")
        if reply is not None:
            _write_message(out, reply)
