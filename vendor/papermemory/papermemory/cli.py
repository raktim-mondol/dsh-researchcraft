from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from papermemory.config import VERSION, db_path
from papermemory.db import Store
from papermemory.util import loads


def _store() -> Store:
    return Store()


def _emit(data: Any, as_json: bool, text: str | None = None) -> int:
    if as_json:
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
    elif text is not None:
        print(text)
    else:
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
    return 0


def _fmt_paper(p: dict[str, Any]) -> str:
    authors = p.get("authors") or loads(p.get("authors_json"), [])
    who = ", ".join(authors[:3])
    if len(authors) > 3:
        who += " et al."
    flag = "verified" if p.get("verified") else "UNVERIFIED"
    key = p.get("bibtex_key") or p.get("id")
    year = p.get("year") or "?"
    return f"[{key}] {p.get('title')} ({year}; {who}) [{flag}]"


def cmd_init(args: argparse.Namespace) -> int:
    store = _store()
    stats = store.stats()
    return _emit(
        {"db": str(store.path), "stats": stats, "version": VERSION},
        args.json,
        f"PaperMemory {VERSION}\nDB: {store.path}\n{json.dumps(stats, indent=2)}",
    )


def cmd_ingest(args: argparse.Namespace) -> int:
    from papermemory.ingest import ingest_arxiv, ingest_doi, ingest_path

    store = _store()
    if args.arxiv:
        rec = ingest_arxiv(store, args.arxiv, project_id=args.project)
        return _emit(rec, args.json, _fmt_paper(rec))
    if args.path:
        result = ingest_path(
            store,
            Path(args.path),
            project_id=args.project,
            kind=args.kind,
            doi=args.doi,
            title=args.title,
            pdf_path=args.pdf_path,
        )
        return _emit(result, args.json)
    if args.doi:
        rec = ingest_doi(store, args.doi, project_id=args.project)
        return _emit(rec, args.json, _fmt_paper(rec))
    print("ingest requires PATH, --arxiv, or --doi", file=sys.stderr)
    return 2


def cmd_search(args: argparse.Namespace) -> int:
    from papermemory.search import search

    hits = search(_store(), args.query, kind=args.kind, limit=args.limit, project_id=args.project)
    if args.json:
        return _emit(hits, True)
    if not hits:
        print("No matches.")
        return 0
    lines = []
    for i, hit in enumerate(hits, 1):
        flag = ""
        if hit.get("kind") == "paper":
            flag = " VERIFIED" if hit.get("verified") else " UNVERIFIED"
        lines.append(f"{i}. ({hit['kind']}{flag}, {hit['score']:.3f}) {hit.get('label')}\n   {hit.get('snippet')}")
    print("\n".join(lines))
    return 0


def cmd_paper(args: argparse.Namespace) -> int:
    store = _store()
    rec = store.get_paper(args.key)
    if not rec:
        print(f"paper not found: {args.key}", file=sys.stderr)
        return 1
    rec["chunks"] = store.conn.execute(
        "SELECT id, section, page, chunk_index, substr(text,1,240) AS preview FROM chunks WHERE paper_id=? ORDER BY chunk_index",
        (rec["id"],),
    ).fetchall()
    rec["chunks"] = [dict(r) for r in rec["chunks"]]
    rec["claims"] = store.list_claims(paper_id=rec["id"])
    rec["relations"] = store.neighbors("paper", rec["id"])
    if args.json:
        return _emit(rec, True)
    print(_fmt_paper(rec))
    if rec.get("doi"):
        print(f"DOI: {rec['doi']}")
    if rec.get("arxiv_id"):
        print(f"arXiv: {rec['arxiv_id']}")
    if rec.get("abstract"):
        print("\nAbstract:\n" + rec["abstract"][:1200])
    if rec["claims"]:
        print("\nClaims:")
        for claim in rec["claims"][:12]:
            print(f"- [{claim['status']}/{claim['claim_type']}] {claim['claim_text']}")
    return 0


def cmd_understand(args: argparse.Namespace) -> int:
    store = _store()
    rec = store.get_paper(args.key)
    if not rec:
        print(f"paper not found: {args.key}", file=sys.stderr)
        return 1
    from papermemory.understand import understand_text

    text = rec.get("abstract") or ""
    chunks = store.conn.execute(
        "SELECT text FROM chunks WHERE paper_id=? ORDER BY chunk_index",
        (rec["id"],),
    ).fetchall()
    if chunks:
        text = "\n\n".join(r["text"] for r in chunks)
    summary = understand_text(text)
    if args.save:
        store.replace_chunks(rec["id"], summary["chunks"])
        existing = {c["claim_text"] for c in store.list_claims(paper_id=rec["id"])}
        for claim in summary["claims"]:
            if claim["claim_text"] not in existing:
                store.add_claim({**claim, "paper_id": rec["id"]})
    return _emit({"paper": rec, "understand": summary}, args.json)


def cmd_cite(args: argparse.Namespace) -> int:
    from papermemory.citations import lookup_cite

    hits = lookup_cite(_store(), args.query, limit=args.limit)
    if args.json:
        return _emit(hits, True)
    if not hits:
        print("No citable papers. Do not invent a citation.")
        return 0
    for hit in hits:
        flag = "verified" if hit["verified"] else "UNVERIFIED — do not cite until verified"
        print(f"- {hit.get('suggested_cite') or hit['title']}  key={hit.get('bibtex_key')}  [{flag}]")
        print(f"  {hit['title']}")
    return 0


def cmd_cite_check(args: argparse.Namespace) -> int:
    from papermemory.citations import cite_check

    report = cite_check(_store(), args.manuscript)
    if args.json:
        return _emit(report, True)
    print(f"Manuscript: {report['manuscript']}")
    print(f"Cited keys: {len(report['cited_keys'])} ({report['cite_count']} in-text cites)")
    if report["missing_from_memory"]:
        print("Missing from memory:")
        for key in report["missing_from_memory"]:
            print(f"  - {key}")
    if report["unverified_cited"]:
        print("Cited but UNVERIFIED:")
        for item in report["unverified_cited"]:
            print(f"  - {item['key']}: {item['title']}")
    if not report["missing_from_memory"] and not report["unverified_cited"]:
        print("All in-text citations are in memory.")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from papermemory.scholar import fetch_arxiv, fetch_crossref

    store = _store()
    if args.all:
        rows = store.conn.execute("SELECT * FROM papers WHERE verified=0").fetchall()
    elif args.key:
        rec = store.get_paper(args.key)
        rows = [rec] if rec else []
    else:
        print("verify requires a paper key or --all", file=sys.stderr)
        return 2
    results = []
    for row in rows:
        rec = dict(row) if not isinstance(row, dict) else row
        try:
            if rec.get("doi"):
                meta = fetch_crossref(rec["doi"])
            elif rec.get("arxiv_id"):
                meta = fetch_arxiv(rec["arxiv_id"])
            else:
                results.append({"id": rec["id"], "ok": False, "reason": "no doi/arxiv"})
                continue
            updated = store.upsert_paper({**rec, **meta, "authors": meta.get("authors") or rec.get("authors")})
            results.append({"id": rec["id"], "ok": True, "title": updated["title"]})
        except Exception as exc:
            results.append({"id": rec.get("id"), "ok": False, "reason": str(exc)})
    return _emit(results, args.json)


def cmd_remember(args: argparse.Namespace) -> int:
    concepts = [c.strip() for c in (args.concepts or "").split(",") if c.strip()]
    rec = _store().remember(args.text, concepts=concepts, project_id=args.project, tier=args.tier)
    return _emit(rec, args.json, f"Saved {rec['id']} concepts={loads(rec['concepts_json'])}")


def cmd_recall(args: argparse.Namespace) -> int:
    from papermemory.search import search

    hits = search(_store(), args.query, kind=args.kind, limit=args.limit, project_id=args.project)
    return _emit(hits, args.json) if args.json else cmd_search(args)


def cmd_lesson(args: argparse.Namespace) -> int:
    concepts = [c.strip() for c in (args.concepts or "").split(",") if c.strip()]
    rec = _store().add_lesson(args.text, concepts=concepts, project_id=args.project)
    return _emit(rec, args.json, f"Lesson {rec['id']} saved.")


def cmd_recap(args: argparse.Namespace) -> int:
    from papermemory.context import recap

    data = recap(_store(), project=args.project)
    if args.json:
        return _emit(data, True)
    stats = data["stats"]
    print(f"PaperMemory  papers={stats['papers']} (verified {stats['verified_papers']}/{stats['papers']})  claims={stats['claims']}  observations={stats['observations']}")
    if data.get("manuscript"):
        ms = data["manuscript"]
        print(f"\nManuscript: {ms['title']}")
        print(f"  slug={ms['slug']}  venue={ms.get('target_venue')}  style={ms.get('citation_style')}  status={ms['status']}")
        for sec in data.get("sections") or []:
            print(f"  section {sec['name']}: {sec.get('word_count') or 0} words ({sec.get('status')})")
        if data.get("contributions"):
            print("  contributions:")
            for item in data["contributions"]:
                print(f"    - {item}")
        cc = data.get("cite_check") or {}
        if cc:
            print(f"  citations: {len(cc.get('cited_keys') or [])} keys, missing={cc.get('missing_from_memory')}, unverified={len(cc.get('unverified_cited') or [])}")
    if data.get("lessons"):
        print("\nLessons:")
        for les in data["lessons"]:
            print(f"- {les['content']}")
    if data.get("observations"):
        print("\nRecent memory:")
        for obs in data["observations"][:5]:
            print(f"- {obs['content'][:240]}")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    return cmd_recap(args)


def cmd_manuscript(args: argparse.Namespace) -> int:
    store = _store()
    if args.ms_cmd == "init":
        from papermemory.util import slugify

        slug = args.slug or slugify(args.title)
        rec = store.upsert_manuscript(
            {
                "title": args.title,
                "slug": slug,
                "target_venue": args.venue,
                "citation_style": args.style,
                "root_path": str(Path(args.path).resolve()) if args.path else None,
            }
        )
        return _emit(rec, args.json)
    if args.ms_cmd == "status":
        args.project = args.slug
        return cmd_recap(args)
    if args.ms_cmd == "comment":
        ms = store.get_manuscript(args.slug)
        if not ms:
            print("manuscript not found", file=sys.stderr)
            return 1
        rec = store.add_reviewer_comment(ms["id"], args.text, reviewer=args.reviewer)
        return _emit(rec, args.json)
    if args.ms_cmd == "term":
        ms = store.get_manuscript(args.slug)
        if not ms:
            print("manuscript not found", file=sys.stderr)
            return 1
        avoid = [x.strip() for x in (args.avoid or "").split(",") if x.strip()]
        store.add_term(ms["id"], args.canonical, avoid=avoid, notes=args.notes)
        return _emit({"ok": True}, args.json, f"term {args.canonical}")
    print("unknown manuscript subcommand", file=sys.stderr)
    return 2


def cmd_claim(args: argparse.Namespace) -> int:
    store = _store()
    rec = store.add_claim(
        {
            "claim_text": args.text,
            "claim_type": args.type,
            "paper_id": args.paper,
            "manuscript_id": args.manuscript,
            "evidence_quote": args.evidence,
            "section": args.section,
            "status": args.status,
            "confidence": args.confidence,
        }
    )
    return _emit(rec, args.json, f"Claim {rec['id']} [{rec['status']}] {rec['claim_text']}")


def cmd_doctor(args: argparse.Namespace) -> int:
    store = _store()
    stats = store.stats()
    issues = []
    if stats["unverified_papers"]:
        issues.append(f"{stats['unverified_papers']} papers have no DOI/arXiv verification")
    empty_abs = store.conn.execute("SELECT COUNT(*) FROM papers WHERE abstract IS NULL OR abstract=''").fetchone()[0]
    if empty_abs:
        issues.append(f"{empty_abs} papers have no abstract")
    report = {"db": str(store.path), "stats": stats, "issues": issues, "ok": not issues}
    return _emit(report, args.json, json.dumps(report, indent=2))


def cmd_mcp(_args: argparse.Namespace) -> int:
    from papermemory.mcp_server import run

    run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--json", action="store_true", help="machine-readable output")
    p = argparse.ArgumentParser(
        prog="papermemory",
        description="Academic paper memory for understanding and writing",
        parents=[shared],
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create the local database", parents=[shared])
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("ingest", help="ingest a paper, bibliography, PDF, or manuscript tree", parents=[shared])
    s.add_argument("path", nargs="?")
    s.add_argument("--arxiv")
    s.add_argument("--doi")
    s.add_argument("--title")
    s.add_argument("--pdf-path", dest="pdf_path", help="attach markdown/tex ingest to an existing PDF record")
    s.add_argument("--project")
    s.add_argument("--kind", default="auto", choices=["auto", "pdf", "bibtex", "markdown", "tex", "dir", "manuscript"])
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("search", help="hybrid search across papers, claims, chunks, notes", parents=[shared])
    s.add_argument("query")
    s.add_argument("--kind", default="all")
    s.add_argument("--project")
    s.add_argument("--limit", type=int, default=8)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("paper", help="show a paper by id or bibtex key", parents=[shared])
    s.add_argument("key")
    s.set_defaults(func=cmd_paper)

    s = sub.add_parser("understand", help="split sections and extract candidate claims", parents=[shared])
    s.add_argument("key")
    s.add_argument("--save", action="store_true")
    s.set_defaults(func=cmd_understand)

    s = sub.add_parser("cite", help="find a citable paper for a statement", parents=[shared])
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=5)
    s.set_defaults(func=cmd_cite)

    s = sub.add_parser("cite-check", help="compare manuscript in-text cites to memory", parents=[shared])
    s.add_argument("manuscript")
    s.set_defaults(func=cmd_cite_check)

    s = sub.add_parser("verify", help="look up DOI/arXiv metadata", parents=[shared])
    s.add_argument("key", nargs="?")
    s.add_argument("--all", action="store_true")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("remember", help="save a writing or reading decision", parents=[shared])
    s.add_argument("text")
    s.add_argument("--concepts", default="")
    s.add_argument("--project")
    s.add_argument("--tier", default="semantic")
    s.set_defaults(func=cmd_remember)

    s = sub.add_parser("recall", help="retrieve notes and papers", parents=[shared])
    s.add_argument("query")
    s.add_argument("--kind", default="all")
    s.add_argument("--project")
    s.add_argument("--limit", type=int, default=8)
    s.set_defaults(func=cmd_recall)

    s = sub.add_parser("lesson", help="save a durable writing/reading rule", parents=[shared])
    s.add_argument("text")
    s.add_argument("--concepts", default="")
    s.add_argument("--project")
    s.set_defaults(func=cmd_lesson)

    s = sub.add_parser("recap", help="briefing for a writing project", parents=[shared])
    s.add_argument("--project")
    s.set_defaults(func=cmd_recap)

    s = sub.add_parser("context", help="alias for recap", parents=[shared])
    s.add_argument("--project")
    s.set_defaults(func=cmd_context)

    s = sub.add_parser("claim", help="store a claim with optional evidence", parents=[shared])
    s.add_argument("text")
    s.add_argument("--type", default="finding")
    s.add_argument("--paper")
    s.add_argument("--manuscript")
    s.add_argument("--evidence")
    s.add_argument("--section")
    s.add_argument("--status", default="extracted")
    s.add_argument("--confidence", type=float, default=0.5)
    s.set_defaults(func=cmd_claim)

    ms = sub.add_parser("manuscript", help="writing-project commands", parents=[shared])
    ms_sub = ms.add_subparsers(dest="ms_cmd", required=True)
    m = ms_sub.add_parser("init", parents=[shared])
    m.add_argument("--title", required=True)
    m.add_argument("--slug")
    m.add_argument("--venue")
    m.add_argument("--style")
    m.add_argument("--path")
    m.set_defaults(func=cmd_manuscript)
    m = ms_sub.add_parser("status", parents=[shared])
    m.add_argument("slug")
    m.set_defaults(func=cmd_manuscript)
    m = ms_sub.add_parser("comment", parents=[shared])
    m.add_argument("slug")
    m.add_argument("text")
    m.add_argument("--reviewer")
    m.set_defaults(func=cmd_manuscript)
    m = ms_sub.add_parser("term", parents=[shared])
    m.add_argument("slug")
    m.add_argument("canonical")
    m.add_argument("--avoid", default="")
    m.add_argument("--notes")
    m.set_defaults(func=cmd_manuscript)

    s = sub.add_parser("doctor", help="health check", parents=[shared])
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("mcp", help="run the MCP stdio server", parents=[shared])
    s.set_defaults(func=cmd_mcp)

    s = sub.add_parser("version", parents=[shared])
    s.set_defaults(func=lambda a: _emit({"version": VERSION, "db": str(db_path())}, a.json, f"papermemory {VERSION}"))
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except Exception as exc:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
