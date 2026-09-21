from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from papermemory.config import db_path, ensure_dirs
from papermemory.util import dumps, fingerprint, loads, new_id, normalize_arxiv, normalize_doi, normalize_title, now_iso

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS papers (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  authors_json TEXT NOT NULL DEFAULT '[]',
  year INTEGER,
  venue TEXT,
  doi TEXT,
  arxiv_id TEXT,
  pmid TEXT,
  url TEXT,
  pdf_path TEXT,
  abstract TEXT,
  bibtex_key TEXT,
  bibtex TEXT,
  source_type TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0,
  verification_note TEXT,
  project_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  accessed_at TEXT,
  access_count INTEGER NOT NULL DEFAULT 0,
  confidence REAL NOT NULL DEFAULT 0.6,
  superseded_by TEXT,
  fingerprint TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL,
  section TEXT,
  page INTEGER,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY,
  paper_id TEXT,
  manuscript_id TEXT,
  claim_text TEXT NOT NULL,
  claim_type TEXT NOT NULL,
  evidence_quote TEXT,
  page INTEGER,
  section TEXT,
  confidence REAL NOT NULL DEFAULT 0.5,
  status TEXT NOT NULL DEFAULT 'extracted',
  superseded_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  normalized TEXT NOT NULL,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  description TEXT,
  UNIQUE(kind, normalized)
);

CREATE TABLE IF NOT EXISTS relations (
  id TEXT PRIMARY KEY,
  src_type TEXT NOT NULL,
  src_id TEXT NOT NULL,
  rel TEXT NOT NULL,
  dst_type TEXT NOT NULL,
  dst_id TEXT NOT NULL,
  evidence TEXT,
  confidence REAL NOT NULL DEFAULT 0.5,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manuscripts (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  target_venue TEXT,
  citation_style TEXT,
  root_path TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manuscript_sections (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL,
  name TEXT NOT NULL,
  path TEXT,
  word_target INTEGER,
  word_count INTEGER,
  status TEXT,
  notes TEXT,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(manuscript_id) REFERENCES manuscripts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS contributions (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL,
  text TEXT NOT NULL,
  order_index INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(manuscript_id) REFERENCES manuscripts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS terminology (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL,
  canonical TEXT NOT NULL,
  avoid_json TEXT NOT NULL DEFAULT '[]',
  notes TEXT,
  FOREIGN KEY(manuscript_id) REFERENCES manuscripts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviewer_comments (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL,
  reviewer TEXT,
  comment TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  response TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(manuscript_id) REFERENCES manuscripts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS observations (
  id TEXT PRIMARY KEY,
  tier TEXT NOT NULL,
  content TEXT NOT NULL,
  concepts_json TEXT NOT NULL DEFAULT '[]',
  project_id TEXT,
  manuscript_id TEXT,
  paper_id TEXT,
  confidence REAL NOT NULL DEFAULT 0.7,
  created_at TEXT NOT NULL,
  accessed_at TEXT,
  access_count INTEGER NOT NULL DEFAULT 0,
  superseded_by TEXT
);

CREATE TABLE IF NOT EXISTS lessons (
  id TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  concepts_json TEXT NOT NULL DEFAULT '[]',
  project_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
  id TEXT PRIMARY KEY,
  operation TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  detail TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_map (
  rowid INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  UNIQUE(kind, ref_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
  title,
  text,
  tokenize = 'unicode61 remove_diacritics 2'
);

CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_arxiv ON papers(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_papers_bib ON papers(bibtex_key);
CREATE INDEX IF NOT EXISTS idx_papers_project ON papers(project_id);
CREATE INDEX IF NOT EXISTS idx_chunks_paper ON chunks(paper_id);
CREATE INDEX IF NOT EXISTS idx_claims_paper ON claims(paper_id);
CREATE INDEX IF NOT EXISTS idx_claims_ms ON claims(manuscript_id);
CREATE INDEX IF NOT EXISTS idx_rel_src ON relations(src_type, src_id);
CREATE INDEX IF NOT EXISTS idx_rel_dst ON relations(dst_type, dst_id);
CREATE INDEX IF NOT EXISTS idx_obs_project ON observations(project_id);
CREATE INDEX IF NOT EXISTS idx_sections_ms ON manuscript_sections(manuscript_id);
"""


class Store:
    def __init__(self, path: Path | None = None):
        ensure_dirs()
        self.path = Path(path) if path else db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def audit(self, operation: str, target_type: str | None = None, target_id: str | None = None, detail: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO audit(id, operation, target_type, target_id, detail, created_at) VALUES (?,?,?,?,?,?)",
            (new_id("aud"), operation, target_type, target_id, detail, now_iso()),
        )

    def _index(self, kind: str, ref_id: str, title: str | None, text: str | None) -> None:
        self._unindex(kind, ref_id)
        body = (text or "").strip()
        heading = (title or "").strip()
        cur = self.conn.execute(
            "INSERT INTO search_fts(title, text) VALUES (?,?)",
            (heading, body),
        )
        self.conn.execute(
            "INSERT INTO search_map(rowid, kind, ref_id) VALUES (?,?,?)",
            (cur.lastrowid, kind, ref_id),
        )

    def _unindex(self, kind: str, ref_id: str) -> None:
        row = self.conn.execute(
            "SELECT rowid FROM search_map WHERE kind=? AND ref_id=?",
            (kind, ref_id),
        ).fetchone()
        if not row:
            return
        self.conn.execute("DELETE FROM search_fts WHERE rowid=?", (row["rowid"],))
        self.conn.execute("DELETE FROM search_map WHERE rowid=?", (row["rowid"],))

    def find_paper(
        self,
        *,
        doi: str | None = None,
        arxiv_id: str | None = None,
        bibtex_key: str | None = None,
        title: str | None = None,
        year: int | None = None,
        fingerprint_value: str | None = None,
        pdf_path: str | None = None,
    ) -> dict[str, Any] | None:
        doi = normalize_doi(doi)
        arxiv_id = normalize_arxiv(arxiv_id)
        if doi:
            row = self.conn.execute("SELECT * FROM papers WHERE doi=?", (doi,)).fetchone()
            if row:
                return dict(row)
        if pdf_path:
            row = self.conn.execute("SELECT * FROM papers WHERE pdf_path=?", (str(pdf_path),)).fetchone()
            if row:
                return dict(row)
        if arxiv_id:
            row = self.conn.execute("SELECT * FROM papers WHERE arxiv_id=?", (arxiv_id,)).fetchone()
            if row:
                return dict(row)
        if bibtex_key:
            row = self.conn.execute("SELECT * FROM papers WHERE bibtex_key=?", (bibtex_key,)).fetchone()
            if row:
                return dict(row)
        if fingerprint_value:
            row = self.conn.execute("SELECT * FROM papers WHERE fingerprint=?", (fingerprint_value,)).fetchone()
            if row:
                return dict(row)
        if title:
            fp = fingerprint(normalize_title(title), str(year or ""))
            row = self.conn.execute("SELECT * FROM papers WHERE fingerprint=?", (fp,)).fetchone()
            if row:
                return dict(row)
        return None

    def upsert_paper(self, data: dict[str, Any]) -> dict[str, Any]:
        title = (data.get("title") or "Untitled").strip()
        year = data.get("year")
        doi = normalize_doi(data.get("doi"))
        arxiv_id = normalize_arxiv(data.get("arxiv_id"))
        bibtex_key = data.get("bibtex_key")
        fp = data.get("fingerprint") or fingerprint(
            doi or "",
            arxiv_id or "",
            normalize_title(title),
            str(year or ""),
            bibtex_key or "",
        )
        existing = self.find_paper(
            doi=doi,
            arxiv_id=arxiv_id,
            bibtex_key=bibtex_key,
            title=title,
            year=year,
            fingerprint_value=fp,
            pdf_path=data.get("pdf_path"),
        )
        now = now_iso()
        authors = data.get("authors") or []
        payload = {
            "title": title,
            "authors_json": dumps(authors),
            "year": year,
            "venue": data.get("venue"),
            "doi": doi,
            "arxiv_id": arxiv_id,
            "pmid": data.get("pmid"),
            "url": data.get("url"),
            "pdf_path": data.get("pdf_path"),
            "abstract": data.get("abstract"),
            "bibtex_key": bibtex_key,
            "bibtex": data.get("bibtex"),
            "source_type": data.get("source_type") or "note",
            "verified": int(bool(data.get("verified", 0))),
            "verification_note": data.get("verification_note"),
            "project_id": data.get("project_id"),
            "updated_at": now,
            "confidence": data.get("confidence", 0.6),
            "fingerprint": fp,
        }
        if existing:
            paper_id = existing["id"]
            merged = dict(existing)
            for key, value in payload.items():
                if value in (None, "", "[]") and merged.get(key) not in (None, "", "[]"):
                    continue
                if key == "verified" and existing.get("verified") and not payload["verified"]:
                    continue
                if key == "source_type" and existing.get("source_type") == "pdf" and payload["source_type"] != "pdf":
                    continue
                merged[key] = value
            self.conn.execute(
                """UPDATE papers SET title=?, authors_json=?, year=?, venue=?, doi=?, arxiv_id=?,
                   pmid=?, url=?, pdf_path=?, abstract=?, bibtex_key=?, bibtex=?, source_type=?,
                   verified=?, verification_note=?, project_id=?, updated_at=?, confidence=?, fingerprint=?
                   WHERE id=?""",
                (
                    merged["title"], merged["authors_json"], merged["year"], merged["venue"],
                    merged["doi"], merged["arxiv_id"], merged["pmid"], merged["url"],
                    merged["pdf_path"], merged["abstract"], merged["bibtex_key"], merged["bibtex"],
                    merged["source_type"], merged["verified"], merged["verification_note"],
                    merged.get("project_id") or payload["project_id"], merged["updated_at"],
                    merged["confidence"], merged["fingerprint"], paper_id,
                ),
            )
            record = self.get_paper(paper_id)
        else:
            paper_id = new_id("pap")
            self.conn.execute(
                """INSERT INTO papers(id, title, authors_json, year, venue, doi, arxiv_id, pmid, url,
                   pdf_path, abstract, bibtex_key, bibtex, source_type, verified, verification_note,
                   project_id, created_at, updated_at, access_count, confidence, fingerprint)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)""",
                (
                    paper_id, payload["title"], payload["authors_json"], payload["year"], payload["venue"],
                    payload["doi"], payload["arxiv_id"], payload["pmid"], payload["url"], payload["pdf_path"],
                    payload["abstract"], payload["bibtex_key"], payload["bibtex"], payload["source_type"],
                    payload["verified"], payload["verification_note"], payload["project_id"], now, now,
                    payload["confidence"], payload["fingerprint"],
                ),
            )
            record = self.get_paper(paper_id)
            self.audit("paper_create", "paper", paper_id, title)
        authors_text = ", ".join(authors) if isinstance(authors, list) else str(authors)
        index_text = " ".join(
            filter(
                None,
                [
                    title,
                    authors_text,
                    str(year or ""),
                    payload.get("venue") or "",
                    bibtex_key or "",
                    doi or "",
                    arxiv_id or "",
                    payload.get("pdf_path") or "",
                    payload.get("abstract") or "",
                ],
            )
        )
        self._index("paper", paper_id, title, index_text)
        self.conn.commit()
        return record  # type: ignore[return-value]

    def get_paper(self, paper_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
        if not row:
            row = self.conn.execute("SELECT * FROM papers WHERE bibtex_key=?", (paper_id,)).fetchone()
        if not row:
            return None
        self.conn.execute(
            "UPDATE papers SET accessed_at=?, access_count=access_count+1 WHERE id=?",
            (now_iso(), row["id"]),
        )
        self.conn.commit()
        record = dict(row)
        record["authors"] = loads(record.get("authors_json"), [])
        return record

    def replace_chunks(self, paper_id: str, chunks: list[dict[str, Any]]) -> int:
        existing = self.conn.execute("SELECT id FROM chunks WHERE paper_id=?", (paper_id,)).fetchall()
        for row in existing:
            self._unindex("chunk", row["id"])
        self.conn.execute("DELETE FROM chunks WHERE paper_id=?", (paper_id,))
        now = now_iso()
        for i, chunk in enumerate(chunks):
            cid = new_id("chk")
            text = (chunk.get("text") or "").strip()
            if not text:
                continue
            self.conn.execute(
                "INSERT INTO chunks(id, paper_id, section, page, chunk_index, text, created_at) VALUES (?,?,?,?,?,?,?)",
                (cid, paper_id, chunk.get("section"), chunk.get("page"), i, text, now),
            )
            self._index("chunk", cid, chunk.get("section") or "", text)
        self.conn.commit()
        return len(chunks)

    def add_claim(self, data: dict[str, Any]) -> dict[str, Any]:
        cid = new_id("clm")
        now = now_iso()
        self.conn.execute(
            """INSERT INTO claims(id, paper_id, manuscript_id, claim_text, claim_type, evidence_quote,
               page, section, confidence, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cid,
                data.get("paper_id"),
                data.get("manuscript_id"),
                data["claim_text"],
                data.get("claim_type") or "finding",
                data.get("evidence_quote"),
                data.get("page"),
                data.get("section"),
                data.get("confidence", 0.5),
                data.get("status") or "extracted",
                now,
                now,
            ),
        )
        self._index("claim", cid, data.get("claim_type") or "claim", data["claim_text"])
        self.audit("claim_create", "claim", cid, data["claim_text"][:200])
        self.conn.commit()
        return self.get_claim(cid)

    def get_claim(self, claim_id: str) -> dict[str, Any]:
        return dict(self.conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone())

    def list_claims(self, paper_id: str | None = None, manuscript_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM claims WHERE 1=1"
        args: list[Any] = []
        if paper_id:
            sql += " AND paper_id=?"
            args.append(paper_id)
        if manuscript_id:
            sql += " AND manuscript_id=?"
            args.append(manuscript_id)
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def upsert_entity(self, kind: str, name: str, description: str | None = None) -> dict[str, Any]:
        normalized = re.sub(r"\s+", " ", name.strip().lower())
        row = self.conn.execute(
            "SELECT * FROM entities WHERE kind=? AND normalized=?",
            (kind, normalized),
        ).fetchone()
        if row:
            return dict(row)
        eid = new_id("ent")
        self.conn.execute(
            "INSERT INTO entities(id, kind, name, normalized, aliases_json, description) VALUES (?,?,?,?,?,?)",
            (eid, kind, name.strip(), normalized, dumps([]), description),
        )
        self._index("entity", eid, kind, f"{kind} {name} {description or ''}")
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM entities WHERE id=?", (eid,)).fetchone())

    def add_relation(
        self,
        src_type: str,
        src_id: str,
        rel: str,
        dst_type: str,
        dst_id: str,
        evidence: str | None = None,
        confidence: float = 0.5,
    ) -> None:
        existing = self.conn.execute(
            """SELECT id FROM relations WHERE src_type=? AND src_id=? AND rel=? AND dst_type=? AND dst_id=?""",
            (src_type, src_id, rel, dst_type, dst_id),
        ).fetchone()
        if existing:
            return
        self.conn.execute(
            """INSERT INTO relations(id, src_type, src_id, rel, dst_type, dst_id, evidence, confidence, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (new_id("rel"), src_type, src_id, rel, dst_type, dst_id, evidence, confidence, now_iso()),
        )
        self.conn.commit()

    def neighbors(self, node_type: str, node_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT * FROM relations
               WHERE (src_type=? AND src_id=?) OR (dst_type=? AND dst_id=?)
               LIMIT ?""",
            (node_type, node_id, node_type, node_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_manuscript(self, data: dict[str, Any]) -> dict[str, Any]:
        slug = data["slug"]
        now = now_iso()
        existing = self.conn.execute("SELECT * FROM manuscripts WHERE slug=?", (slug,)).fetchone()
        if existing:
            self.conn.execute(
                """UPDATE manuscripts SET title=?, target_venue=?, citation_style=?, root_path=?,
                   status=?, notes=?, updated_at=? WHERE slug=?""",
                (
                    data.get("title") or existing["title"],
                    data.get("target_venue") if data.get("target_venue") is not None else existing["target_venue"],
                    data.get("citation_style") if data.get("citation_style") is not None else existing["citation_style"],
                    data.get("root_path") if data.get("root_path") is not None else existing["root_path"],
                    data.get("status") or existing["status"],
                    data.get("notes") if data.get("notes") is not None else existing["notes"],
                    now,
                    slug,
                ),
            )
            ms_id = existing["id"]
        else:
            ms_id = new_id("ms")
            self.conn.execute(
                """INSERT INTO manuscripts(id, title, slug, target_venue, citation_style, root_path, status, notes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    ms_id,
                    data["title"],
                    slug,
                    data.get("target_venue"),
                    data.get("citation_style"),
                    data.get("root_path"),
                    data.get("status") or "draft",
                    data.get("notes"),
                    now,
                    now,
                ),
            )
            self.audit("manuscript_create", "manuscript", ms_id, slug)
        record = self.get_manuscript(slug)
        self._index("manuscript", ms_id, record["title"], " ".join(filter(None, [record["title"], record.get("target_venue"), record.get("citation_style"), slug])))
        self.conn.commit()
        return record

    def get_manuscript(self, slug_or_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM manuscripts WHERE slug=? OR id=?",
            (slug_or_id, slug_or_id),
        ).fetchone()
        return dict(row) if row else None

    def replace_sections(self, manuscript_id: str, sections: list[dict[str, Any]]) -> None:
        self.conn.execute("DELETE FROM manuscript_sections WHERE manuscript_id=?", (manuscript_id,))
        now = now_iso()
        for section in sections:
            self.conn.execute(
                """INSERT INTO manuscript_sections(id, manuscript_id, name, path, word_target, word_count, status, notes, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    new_id("sec"),
                    manuscript_id,
                    section["name"],
                    section.get("path"),
                    section.get("word_target"),
                    section.get("word_count"),
                    section.get("status"),
                    section.get("notes"),
                    now,
                ),
            )
        self.conn.commit()

    def replace_contributions(self, manuscript_id: str, items: list[str]) -> None:
        self.conn.execute("DELETE FROM contributions WHERE manuscript_id=?", (manuscript_id,))
        now = now_iso()
        for i, text in enumerate(items):
            if not text.strip():
                continue
            self.conn.execute(
                "INSERT INTO contributions(id, manuscript_id, text, order_index, created_at) VALUES (?,?,?,?,?)",
                (new_id("con"), manuscript_id, text.strip(), i, now),
            )
        self.conn.commit()

    def add_term(self, manuscript_id: str, canonical: str, avoid: list[str] | None = None, notes: str | None = None) -> None:
        existing = self.conn.execute(
            "SELECT id FROM terminology WHERE manuscript_id=? AND canonical=?",
            (manuscript_id, canonical),
        ).fetchone()
        if existing:
            return
        self.conn.execute(
            "INSERT INTO terminology(id, manuscript_id, canonical, avoid_json, notes) VALUES (?,?,?,?,?)",
            (new_id("trm"), manuscript_id, canonical, dumps(avoid or []), notes),
        )
        self.conn.commit()

    def add_reviewer_comment(self, manuscript_id: str, comment: str, reviewer: str | None = None) -> dict[str, Any]:
        cid = new_id("rev")
        self.conn.execute(
            """INSERT INTO reviewer_comments(id, manuscript_id, reviewer, comment, status, created_at)
               VALUES (?,?,?,?, 'open', ?)""",
            (cid, manuscript_id, reviewer, comment, now_iso()),
        )
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM reviewer_comments WHERE id=?", (cid,)).fetchone())

    def remember(self, content: str, concepts: Iterable[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        oid = new_id("obs")
        now = now_iso()
        concepts_list = [c.strip().lower() for c in (concepts or []) if c and c.strip()]
        self.conn.execute(
            """INSERT INTO observations(id, tier, content, concepts_json, project_id, manuscript_id, paper_id,
               confidence, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                oid,
                kwargs.get("tier") or "semantic",
                content.strip(),
                dumps(concepts_list),
                kwargs.get("project_id"),
                kwargs.get("manuscript_id"),
                kwargs.get("paper_id"),
                kwargs.get("confidence", 0.7),
                now,
            ),
        )
        self._index("observation", oid, " ".join(concepts_list), content)
        self.audit("remember", "observation", oid, content[:200])
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM observations WHERE id=?", (oid,)).fetchone())

    def add_lesson(self, content: str, concepts: Iterable[str] | None = None, project_id: str | None = None) -> dict[str, Any]:
        lid = new_id("les")
        concepts_list = [c.strip().lower() for c in (concepts or []) if c and c.strip()]
        self.conn.execute(
            "INSERT INTO lessons(id, content, concepts_json, project_id, created_at) VALUES (?,?,?,?,?)",
            (lid, content.strip(), dumps(concepts_list), project_id, now_iso()),
        )
        self._index("lesson", lid, " ".join(concepts_list), content)
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM lessons WHERE id=?", (lid,)).fetchone())

    def stats(self) -> dict[str, int]:
        tables = [
            "papers", "chunks", "claims", "entities", "relations",
            "manuscripts", "observations", "lessons",
        ]
        out: dict[str, int] = {}
        for table in tables:
            out[table] = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        out["verified_papers"] = self.conn.execute("SELECT COUNT(*) FROM papers WHERE verified=1").fetchone()[0]
        out["unverified_papers"] = self.conn.execute("SELECT COUNT(*) FROM papers WHERE verified=0").fetchone()[0]
        return out
