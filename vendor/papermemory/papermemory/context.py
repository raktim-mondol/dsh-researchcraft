from __future__ import annotations

from typing import Any

from papermemory.citations import cite_check
from papermemory.db import Store
from papermemory.util import loads


def recap(store: Store, project: str | None = None, limit: int = 8) -> dict[str, Any]:
    stats = store.stats()
    out: dict[str, Any] = {"stats": stats, "project": project}
    if project:
        ms = store.get_manuscript(project)
        if ms:
            out["manuscript"] = ms
            out["sections"] = [
                dict(r)
                for r in store.conn.execute(
                    "SELECT name, path, word_target, word_count, status FROM manuscript_sections WHERE manuscript_id=? ORDER BY name",
                    (ms["id"],),
                ).fetchall()
            ]
            out["contributions"] = [
                r["text"]
                for r in store.conn.execute(
                    "SELECT text FROM contributions WHERE manuscript_id=? ORDER BY order_index",
                    (ms["id"],),
                ).fetchall()
            ]
            out["terminology"] = [
                {"canonical": r["canonical"], "avoid": loads(r["avoid_json"], [])}
                for r in store.conn.execute(
                    "SELECT canonical, avoid_json FROM terminology WHERE manuscript_id=?",
                    (ms["id"],),
                ).fetchall()
            ]
            out["open_reviewer_comments"] = [
                dict(r)
                for r in store.conn.execute(
                    "SELECT id, reviewer, comment, status FROM reviewer_comments WHERE manuscript_id=? AND status='open'",
                    (ms["id"],),
                ).fetchall()
            ]
            try:
                out["cite_check"] = cite_check(store, ms["slug"])
            except Exception as exc:
                out["cite_check_error"] = str(exc)
    sql = "SELECT * FROM observations"
    args: list[Any] = []
    if project:
        sql += " WHERE project_id=? AND superseded_by IS NULL"
        args.append(project)
    else:
        sql += " WHERE superseded_by IS NULL"
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    out["observations"] = []
    for row in store.conn.execute(sql, args).fetchall():
        rec = dict(row)
        rec["concepts"] = loads(rec.get("concepts_json"), [])
        out["observations"].append(rec)
    out["lessons"] = []
    lsql = "SELECT * FROM lessons"
    largs: list[Any] = []
    if project:
        lsql += " WHERE project_id=? OR project_id IS NULL"
        largs.append(project)
    lsql += " ORDER BY created_at DESC LIMIT ?"
    largs.append(limit)
    for row in store.conn.execute(lsql, largs).fetchall():
        rec = dict(row)
        rec["concepts"] = loads(rec.get("concepts_json"), [])
        out["lessons"].append(rec)
    paper_sql = "SELECT id, title, year, bibtex_key, verified, venue FROM papers"
    pargs: list[Any] = []
    if project:
        paper_sql += " WHERE project_id=?"
        pargs.append(project)
    paper_sql += " ORDER BY updated_at DESC LIMIT ?"
    pargs.append(limit)
    out["recent_papers"] = [dict(r) for r in store.conn.execute(paper_sql, pargs).fetchall()]
    return out
