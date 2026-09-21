from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from papermemory.db import Store
from papermemory.util import loads

RRF_K = 60
HALF_LIFE_DAYS = {
    "paper": 730.0,
    "chunk": 365.0,
    "claim": 365.0,
    "observation": 90.0,
    "lesson": 400.0,
    "entity": 800.0,
    "manuscript": 800.0,
}


def _fts_query(raw: str) -> str | None:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", raw or "")
    if not tokens:
        return None
    quoted = [f'"{t}"' for t in tokens[:12]]
    if len(quoted) == 1:
        return quoted[0]
    return " OR ".join(quoted)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _decay(kind: str, created_at: str | None, access_count: int = 0) -> float:
    created = _parse_ts(created_at)
    if not created:
        return 1.0
    now = datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - created).total_seconds() / 86400.0)
    half = HALF_LIFE_DAYS.get(kind, 180.0)
    recency = math.exp(-math.log(2) * days / half)
    boost = 1.0 + min(0.3, 0.04 * access_count)
    return recency * boost


def _hydrate(store: Store, kind: str, ref_id: str) -> dict[str, Any] | None:
    if kind == "paper":
        row = store.conn.execute("SELECT * FROM papers WHERE id=?", (ref_id,)).fetchone()
        if not row:
            return None
        rec = dict(row)
        rec["authors"] = loads(rec.get("authors_json"), [])
        rec["kind"] = "paper"
        rec["label"] = rec["title"]
        return rec
    if kind == "chunk":
        row = store.conn.execute(
            """SELECT c.*, p.title AS paper_title, p.bibtex_key, p.year, p.verified
               FROM chunks c JOIN papers p ON p.id=c.paper_id WHERE c.id=?""",
            (ref_id,),
        ).fetchone()
        if not row:
            return None
        rec = dict(row)
        rec["kind"] = "chunk"
        rec["label"] = rec.get("paper_title")
        return rec
    if kind == "claim":
        row = store.conn.execute("SELECT * FROM claims WHERE id=?", (ref_id,)).fetchone()
        if not row:
            return None
        rec = dict(row)
        rec["kind"] = "claim"
        rec["label"] = rec["claim_text"]
        return rec
    if kind == "observation":
        row = store.conn.execute("SELECT * FROM observations WHERE id=?", (ref_id,)).fetchone()
        if not row:
            return None
        rec = dict(row)
        rec["concepts"] = loads(rec.get("concepts_json"), [])
        rec["kind"] = "observation"
        rec["label"] = rec["content"]
        return rec
    if kind == "lesson":
        row = store.conn.execute("SELECT * FROM lessons WHERE id=?", (ref_id,)).fetchone()
        if not row:
            return None
        rec = dict(row)
        rec["concepts"] = loads(rec.get("concepts_json"), [])
        rec["kind"] = "lesson"
        rec["label"] = rec["content"]
        return rec
    if kind == "entity":
        row = store.conn.execute("SELECT * FROM entities WHERE id=?", (ref_id,)).fetchone()
        if not row:
            return None
        rec = dict(row)
        rec["kind"] = "entity"
        rec["label"] = rec["name"]
        return rec
    if kind == "manuscript":
        row = store.conn.execute("SELECT * FROM manuscripts WHERE id=?", (ref_id,)).fetchone()
        if not row:
            return None
        rec = dict(row)
        rec["kind"] = "manuscript"
        rec["label"] = rec["title"]
        return rec
    return None


def _fts_hits(store: Store, query: str, kind: str | None, limit: int) -> list[tuple[str, str, int]]:
    match = _fts_query(query)
    if not match:
        return []
    sql = """
        SELECT search_map.kind, search_map.ref_id
        FROM search_fts
        JOIN search_map ON search_map.rowid = search_fts.rowid
        WHERE search_fts MATCH ?
    """
    args: list[Any] = [match]
    if kind and kind != "all":
        sql += " AND search_map.kind=?"
        args.append(kind)
    sql += " LIMIT ?"
    args.append(limit * 4)
    rows = store.conn.execute(sql, args).fetchall()
    return [(r["kind"], r["ref_id"], i + 1) for i, r in enumerate(rows)]


def _graph_hits(store: Store, query: str, limit: int) -> list[tuple[str, str, int]]:
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", query)]
    if not tokens:
        return []
    like = "%" + "%".join(tokens[:3]) + "%"
    entities = store.conn.execute(
        "SELECT * FROM entities WHERE name LIKE ? OR normalized LIKE ? LIMIT 8",
        (like, like),
    ).fetchall()
    hits: list[tuple[str, str]] = []
    for ent in entities:
        rels = store.neighbors("entity", ent["id"], limit=12)
        for rel in rels:
            if rel["src_type"] != "entity":
                hits.append((rel["src_type"], rel["src_id"]))
            if rel["dst_type"] != "entity":
                hits.append((rel["dst_type"], rel["dst_id"]))
    papers = store.conn.execute(
        "SELECT id FROM papers WHERE bibtex_key LIKE ? OR title LIKE ? LIMIT 8",
        (like, like),
    ).fetchall()
    for paper in papers:
        hits.append(("paper", paper["id"]))
        for rel in store.neighbors("paper", paper["id"], limit=8):
            hits.append((rel["dst_type"], rel["dst_id"]))
            hits.append((rel["src_type"], rel["src_id"]))
    seen: set[tuple[str, str]] = set()
    ranked: list[tuple[str, str, int]] = []
    for kind, ref_id in hits:
        key = (kind, ref_id)
        if key in seen:
            continue
        seen.add(key)
        ranked.append((kind, ref_id, len(ranked) + 1))
        if len(ranked) >= limit:
            break
    return ranked


def _token_overlap(query: str, rec: dict[str, Any]) -> float:
    q_tokens = {t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", query)}
    if not q_tokens:
        return 0.0
    blob = " ".join(
        [
            rec.get("title") or "",
            rec.get("label") or "",
            rec.get("bibtex_key") or "",
            rec.get("venue") or "",
            rec.get("claim_text") or "",
            rec.get("content") or "",
            " ".join(rec.get("authors") or []) if isinstance(rec.get("authors"), list) else "",
            rec.get("snippet") or "",
        ]
    ).lower()
    words = set(re.findall(r"[a-z0-9]+", blob))
    hits = len(q_tokens & words)
    phrase = " ".join(t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", query))
    phrase_bonus = 0.35 if phrase and phrase in blob else 0.0
    return hits / len(q_tokens) + phrase_bonus


def search(store: Store, query: str, kind: str = "all", limit: int = 10, project_id: str | None = None) -> list[dict[str, Any]]:
    fts = _fts_hits(store, query, None if kind == "all" else kind, limit)
    graph = _graph_hits(store, query, limit)
    scores: dict[tuple[str, str], float] = {}
    for source in (fts, graph):
        for item_kind, ref_id, rank in source:
            if kind not in ("all", None) and item_kind != kind:
                continue
            key = (item_kind, ref_id)
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)

    hydrated: list[dict[str, Any]] = []
    for (item_kind, ref_id), rrf in scores.items():
        rec = _hydrate(store, item_kind, ref_id)
        if not rec:
            continue
        if project_id and rec.get("project_id") not in (None, project_id) and rec.get("manuscript_id") != project_id:
            if rec.get("slug") != project_id:
                continue
        snippet = rec.get("text") or rec.get("abstract") or rec.get("claim_text") or rec.get("content") or rec.get("label") or ""
        rec["snippet"] = " ".join(snippet.split())[:400]
        overlap = _token_overlap(query, rec)
        rec["score"] = (rrf * _decay(item_kind, rec.get("created_at"), rec.get("access_count") or 0)) * (0.15 + overlap)
        rec["overlap"] = overlap
        hydrated.append(rec)
    hydrated.sort(key=lambda r: r["score"], reverse=True)
    return hydrated[:limit]
