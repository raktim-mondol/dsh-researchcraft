from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from papermemory import __version__
from papermemory.citations import cite_check, lookup_cite
from papermemory.context import recap
from papermemory.db import Store
from papermemory.ingest import ingest_arxiv, ingest_doi, ingest_path
from papermemory.search import search as hybrid_search
from papermemory.util import loads

TOOLS = [
    {
        "name": "papermemory_search",
        "description": "Search academic memory: papers, claims, chunks, notes, lessons.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "kind": {"type": "string", "description": "all|paper|claim|chunk|observation|lesson"},
                "project": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "papermemory_ingest",
        "description": "Ingest a local PDF/BibTeX/markdown/manuscript path, or an arXiv id / DOI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "arxiv": {"type": "string"},
                "doi": {"type": "string"},
                "title": {"type": "string"},
                "pdf_path": {"type": "string", "description": "Attach markdown ingest to the paper for this PDF path"},
                "project": {"type": "string"},
                "kind": {"type": "string"},
            },
        },
    },
    {
        "name": "papermemory_get",
        "description": "Get a paper by id or bibtex key, including claims and chunks.",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
    {
        "name": "papermemory_cite",
        "description": "Find a stored paper to cite for a statement. Never invent citations.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
        },
    },
    {
        "name": "papermemory_cite_check",
        "description": "Check a manuscript's in-text citations against memory.",
        "inputSchema": {
            "type": "object",
            "properties": {"manuscript": {"type": "string"}},
            "required": ["manuscript"],
        },
    },
    {
        "name": "papermemory_remember",
        "description": "Save a paper-writing or paper-reading decision, claim, or note.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "concepts": {"type": "string", "description": "comma-separated tags"},
                "project": {"type": "string"},
                "tier": {"type": "string"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "papermemory_claim",
        "description": "Store a claim with evidence. Status extracted|verified|contradicted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "type": {"type": "string"},
                "paper": {"type": "string"},
                "manuscript": {"type": "string"},
                "evidence": {"type": "string"},
                "section": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "papermemory_recap",
        "description": "Writing-project briefing: venue, sections, contributions, citation gaps, recent notes.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
        },
    },
    {
        "name": "papermemory_lesson",
        "description": "Save a durable academic writing/reading rule.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "concepts": {"type": "string"},
                "project": {"type": "string"},
            },
            "required": ["content"],
        },
    },
]


def _ok(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, indent=2, default=str, ensure_ascii=False)}]}


def _err(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps({"error": message})}]}


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    store = Store()
    try:
        if name == "papermemory_search":
            return _ok(hybrid_search(store, args["query"], kind=args.get("kind") or "all", limit=int(args.get("limit") or 8), project_id=args.get("project")))
        if name == "papermemory_ingest":
            if args.get("arxiv"):
                return _ok(ingest_arxiv(store, args["arxiv"], project_id=args.get("project")))
            if args.get("path"):
                return _ok(
                    ingest_path(
                        store,
                        Path(args["path"]),
                        project_id=args.get("project"),
                        kind=args.get("kind") or "auto",
                        doi=args.get("doi"),
                        title=args.get("title"),
                        pdf_path=args.get("pdf_path"),
                    )
                )
            if args.get("doi"):
                return _ok(ingest_doi(store, args["doi"], project_id=args.get("project")))
            return _err("path, arxiv, or doi is required")
        if name == "papermemory_get":
            rec = store.get_paper(args["key"])
            if not rec:
                return _err("paper not found")
            rec["claims"] = store.list_claims(paper_id=rec["id"])
            rec["chunks"] = [
                dict(r)
                for r in store.conn.execute(
                    "SELECT id, section, page, chunk_index, substr(text,1,400) AS preview FROM chunks WHERE paper_id=? ORDER BY chunk_index LIMIT 40",
                    (rec["id"],),
                ).fetchall()
            ]
            return _ok(rec)
        if name == "papermemory_cite":
            return _ok(lookup_cite(store, args["query"], limit=int(args.get("limit") or 5)))
        if name == "papermemory_cite_check":
            return _ok(cite_check(store, args["manuscript"]))
        if name == "papermemory_remember":
            concepts = [c.strip() for c in (args.get("concepts") or "").split(",") if c.strip()]
            rec = store.remember(args["content"], concepts=concepts, project_id=args.get("project"), tier=args.get("tier") or "semantic")
            rec["concepts"] = loads(rec.get("concepts_json"), [])
            return _ok(rec)
        if name == "papermemory_claim":
            rec = store.add_claim(
                {
                    "claim_text": args["text"],
                    "claim_type": args.get("type") or "finding",
                    "paper_id": args.get("paper"),
                    "manuscript_id": args.get("manuscript"),
                    "evidence_quote": args.get("evidence"),
                    "section": args.get("section"),
                    "status": args.get("status") or "extracted",
                }
            )
            return _ok(rec)
        if name == "papermemory_recap":
            return _ok(recap(store, project=args.get("project")))
        if name == "papermemory_lesson":
            concepts = [c.strip() for c in (args.get("concepts") or "").split(",") if c.strip()]
            return _ok(store.add_lesson(args["content"], concepts=concepts, project_id=args.get("project")))
        return _err(f"unknown tool: {name}")
    except Exception as exc:
        return _err(str(exc))
    finally:
        store.close()


# MCP stdio framing: the current TypeScript SDK (DSH, recent Grok) writes
# newline-delimited JSON. Older clients use LSP Content-Length headers.
# Detect from the first inbound message and reply in the same framing.
_framing = "content-length"


def _read_message() -> dict[str, Any] | None:
    global _framing
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    if line.lstrip().startswith(b"{"):
        _framing = "ndjson"
        return json.loads(line.decode("utf-8"))
    _framing = "content-length"
    headers: dict[str, str] = {}
    while True:
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8")
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        line = sys.stdin.buffer.readline()
        if not line:
            return None
    length = int(headers.get("content-length") or 0)
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(payload: dict[str, Any]) -> None:
    blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if _framing == "ndjson":
        sys.stdout.buffer.write(blob + b"\n")
    else:
        sys.stdout.buffer.write(f"Content-Length: {len(blob)}\r\n\r\n".encode("ascii") + blob)
    sys.stdout.buffer.flush()


def run() -> None:
    while True:
        message = _read_message()
        if message is None:
            return
        method = message.get("method")
        msg_id = message.get("id")
        if method == "initialize":
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "papermemory", "version": __version__},
                    },
                }
            )
            continue
        if method == "notifications/initialized":
            continue
        if method == "tools/list":
            _write_message({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
            continue
        if method == "tools/call":
            params = message.get("params") or {}
            result = _call(params.get("name"), params.get("arguments") or {})
            _write_message({"jsonrpc": "2.0", "id": msg_id, "result": result})
            continue
        if method == "ping":
            _write_message({"jsonrpc": "2.0", "id": msg_id, "result": {}})
            continue
        if msg_id is not None:
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )
