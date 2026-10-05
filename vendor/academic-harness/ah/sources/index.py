"""Passage index: full-text search over the cited sources (design 7.3, 7.5).

Sources are split into passages (blank-line blocks, merged to a useful size) that keep their line
range. Search is SQLite FTS5/BM25 and restricted to the source(s) a claim cites, so the verifier sees a
few relevant passages instead of a whole paper. Numbers are normalised ('0.052' -> '0_052') because the
default tokenizer would split them.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..project import Project
from ..util import sha256_file

STOP = set("the a an and or of in on to for with by from as at is are was were be been it its this that these those which who whom than then so such not no but if into over under between among across within per via also may can could would should has have had their there while where when what how all any each both more most other some only very".split())
MIN_CHARS, MAX_CHARS = 350, 1500
SCHEMA_VERSION = 2
# When a query asks about a reporting guideline, also retrieve passages that name the usual ones.
# "claim" is omitted: it is a common English verb and would drown the ranking.
GUIDELINE_ALIASES = ("stard", "tripod", "consort", "prisma", "strobe", "spirit", "cheers", "arrive")
GUIDELINE_NEAR = ("followed", "adherence", "accordance", "presented", "guideline", "guidelines", "statement")
SNIPPET_WIDTH = 520


@dataclass
class Passage:
    source: str
    start: int
    end: int
    text: str
    score: float = 0.0
    file: str = ""           # which conversion of the source this came from (when there are several)

    @property
    def locator(self) -> str:
        return f"{self.source}{'[' + self.file + ']' if self.file else ''}:{self.start}-{self.end}"


def norm_numbers(s: str) -> str:
    s = re.sub(r"(?<=\d)[.,](?=\d)", "_", s)
    return s


def tokens(s: str) -> list[str]:
    s = norm_numbers(s.lower())
    out = re.findall(r"[a-z][a-z0-9_\-]{2,}|\d[\d_]*", s)
    return [t.strip("-_") for t in out if t.strip("-_") and t not in STOP]


def query_terms(query: str) -> tuple[list[str], list[str]]:
    """Distinct query tokens plus reporting-guideline aliases when the query asks for a guideline."""
    terms = list(dict.fromkeys(tokens(query)))[:40]
    extra: list[str] = []
    if any(t in ("guideline", "guidelines") for t in terms):
        extra = [a for a in GUIDELINE_ALIASES if a not in terms]
    return terms, extra


def snippet(text: str, query: str, width: int = SNIPPET_WIDTH) -> str:
    """The span of `text` that covers the most query tokens, not the prefix.

    Pack used to cut at 420 characters from the start. Guideline statements (STARD, TRIPOD)
    often sit at the end of a methods block, so the writer never saw them.
    """
    if len(text) <= width:
        return text
    terms, extra = query_terms(query)
    want = terms + extra
    if not want:
        return text[:width]
    low = text.lower()
    hits: list[tuple[int, int, str]] = []
    for t in want:
        pat = re.escape(t).replace("_", r"[._]")
        for m in re.finditer(pat, low):
            hits.append((m.start(), m.end(), t))
    if not hits:
        return text[:width]
    hits.sort()
    aliases = set(extra)
    best = (0, 0, 0, 0, 0)  # alias hits, unique terms, -span, lo, hi
    for i, (s, e, _t) in enumerate(hits):
        seen: set[str] = set()
        hi = e
        for j in range(i, len(hits)):
            if hits[j][1] - s > width:
                break
            seen.add(hits[j][2])
            hi = hits[j][1]
            cand = (len(seen & aliases), len(seen), -(hi - s), s, hi)
            if cand[:3] > best[:3]:
                best = cand
    lo, hi = best[3], best[4]
    pad = max(0, (width - (hi - lo)) // 2)
    start = max(0, lo - pad)
    if start > 0:
        sp = text.rfind(" ", max(0, start - 30), start + 1)
        if sp >= max(0, start - 30):
            start = sp + 1
    end = min(len(text), start + width)
    if end < len(text):
        sp = text.find(" ", max(start, end - 20), end + 1)
        if start < sp <= end + 20:
            end = sp
    frag = text[start:end].strip()
    if start > 0:
        frag = "..." + frag
    if end < len(text):
        frag = frag + "..."
    return frag


def passages_of(text: str, source: str) -> list[Passage]:
    lines = text.split("\n")
    blocks, cur, start = [], [], None
    for i, line in enumerate(lines, 1):
        if line.strip():
            if start is None:
                start = i
            cur.append(line.strip())
        elif cur:
            blocks.append((start, i - 1, " ".join(cur)))
            cur, start = [], None
    if cur:
        blocks.append((start, len(lines), " ".join(cur)))
    out: list[Passage] = []
    buf: Passage | None = None
    for s, e, t in blocks:
        while len(t) > MAX_CHARS:                      # very long blocks: split at a sentence boundary
            cut = t.rfind(". ", 0, MAX_CHARS)
            cut = cut + 1 if cut > MIN_CHARS else MAX_CHARS
            out.append(Passage(source, s, e, t[:cut].strip()))
            t = t[cut:].strip()
        if buf is None:
            buf = Passage(source, s, e, t)
        elif len(buf.text) < MIN_CHARS:
            buf = Passage(source, buf.start, e, buf.text + " " + t)
        else:
            out.append(buf)
            buf = Passage(source, s, e, t)
    if buf:
        out.append(buf)
    return [p for p in out if len(p.text) >= 20]


class Index:
    def __init__(self, project: Project):
        project.state_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(project.state_dir / "sources.sqlite")
        if self.db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:    # derived data: rebuild, never migrate
            self.db.executescript("DROP TABLE IF EXISTS ps; DROP TABLE IF EXISTS docs;")
            self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS docs (source TEXT PRIMARY KEY, path TEXT, sha TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS ps USING fts5(body, source UNINDEXED, start UNINDEXED, end_ UNINDEXED, raw UNINDEXED, file UNINDEXED, tokenize='unicode61');
        """)

    def ensure(self, source: str, path: Path | list[Path]) -> bool:
        paths = [path] if isinstance(path, Path) else list(path)
        sha = "|".join(sha256_file(p) for p in paths)
        row = self.db.execute("SELECT sha FROM docs WHERE source=?", (source,)).fetchone()
        if row and row[0] == sha:
            return False
        self.db.execute("DELETE FROM ps WHERE source=?", (source,))
        for path_ in paths:
            for p in passages_of(path_.read_text(errors="replace"), source):
                self.db.execute("INSERT INTO ps(body, source, start, end_, raw, file) VALUES (?,?,?,?,?,?)",
                                (norm_numbers(p.text), source, p.start, p.end, p.text, path_.stem if len(paths) > 1 else ""))
        self.db.execute("INSERT OR REPLACE INTO docs VALUES (?,?,?)", (source, ";".join(map(str, paths)), sha))
        self.db.commit()
        return True

    def search(self, sources: list[str], query: str, k: int = 3) -> list[Passage]:
        terms, extra = query_terms(query)
        all_terms = (terms + extra)[:40]
        if not all_terms or not sources:
            return []
        q = " OR ".join(f'"{t}"' for t in all_terms)
        ph = ",".join("?" * len(sources))
        pool = max(k * 8, 24)
        rows = self.db.execute(
            f"SELECT source, start, end_, raw, bm25(ps) AS s, file FROM ps WHERE ps MATCH ? AND source IN ({ph}) ORDER BY s LIMIT ?",
            [q, *sources, pool]).fetchall()
        cands = [Passage(r[0], r[1], r[2], r[3], -r[4], r[5] or "") for r in rows]
        want, aliases = set(all_terms), set(extra)
        def cover(p: Passage) -> tuple:
            pt = set(tokens(p.text))
            hit = want & pt
            return (len(hit & aliases), _alias_near(p.text, aliases), len(hit), p.score)
        cands.sort(key=cover, reverse=True)
        return cands[:k]

    def all_text_numbers(self, source: str) -> set[str]:
        out: set[str] = set()
        for (raw,) in self.db.execute("SELECT raw FROM ps WHERE source=?", (source,)):
            out.update(re.findall(r"\d+(?:\.\d+)?", raw.replace(",", "")))
        return out

    def close(self):
        self.db.close()


def _alias_near(text: str, aliases: set[str]) -> int:
    """How many claim-verbs ('followed', 'presented', 'statement') co-occur with a guideline name in this passage."""
    if not aliases:
        return 0
    low = text.lower()
    if not any(a in low for a in aliases):
        return 0
    return sum(1 for w in GUIDELINE_NEAR if w in low)
