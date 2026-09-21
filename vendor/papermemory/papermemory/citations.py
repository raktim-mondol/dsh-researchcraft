from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from papermemory.db import Store
from papermemory.util import strip_tex_comments

CITE_RE = re.compile(r"\\cite[tpa]?[A-Za-z]*\*?(?:\[[^\]]*\]){0,2}\{([^}]+)\}")


def extract_cite_keys(tex: str) -> list[str]:
    keys: list[str] = []
    for match in CITE_RE.finditer(strip_tex_comments(tex)):
        for key in match.group(1).split(","):
            key = key.strip()
            if key:
                keys.append(key)
    return keys


def scan_tex_tree(root: Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.tex")):
        if any(part.startswith(".") for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        keys = extract_cite_keys(text)
        if keys:
            found[str(path)] = keys
    return found


def cite_check(store: Store, manuscript_slug: str) -> dict[str, Any]:
    ms = store.get_manuscript(manuscript_slug)
    if not ms:
        raise LookupError(f"manuscript not found: {manuscript_slug}")
    root = Path(ms["root_path"]) if ms.get("root_path") else None
    used: dict[str, list[str]] = {}
    if root and root.exists():
        used = scan_tex_tree(root)
    all_keys: list[str] = []
    for keys in used.values():
        all_keys.extend(keys)
    unique_keys = sorted(set(all_keys))
    papers = {
        row["bibtex_key"]: dict(row)
        for row in store.conn.execute(
            "SELECT * FROM papers WHERE project_id=? OR bibtex_key IS NOT NULL",
            (ms["slug"],),
        ).fetchall()
        if row["bibtex_key"]
    }
    missing_from_memory = [k for k in unique_keys if k not in papers]
    unverified = [
        {"key": k, "title": papers[k]["title"], "verified": 0}
        for k in unique_keys
        if k in papers and not papers[k]["verified"]
    ]
    unused = sorted(k for k in papers if k not in unique_keys and papers[k].get("project_id") == ms["slug"])
    return {
        "manuscript": ms["slug"],
        "cited_keys": unique_keys,
        "cite_count": len(all_keys),
        "files": {path: sorted(set(keys)) for path, keys in used.items()},
        "missing_from_memory": missing_from_memory,
        "unverified_cited": unverified,
        "in_memory_uncited": unused,
    }


def lookup_cite(store: Store, query: str, limit: int = 8) -> list[dict[str, Any]]:
    from papermemory.search import search

    hits = search(store, query, kind="paper", limit=limit)
    out = []
    for hit in hits:
        authors = hit.get("authors") or []
        year = hit.get("year")
        key = hit.get("bibtex_key")
        cite = None
        if authors and year:
            last = authors[0].split()[-1]
            cite = f"{last} et al., {year}" if len(authors) > 2 else f"{last}, {year}"
        out.append(
            {
                "id": hit["id"],
                "bibtex_key": key,
                "title": hit.get("title"),
                "authors": authors,
                "year": year,
                "venue": hit.get("venue"),
                "doi": hit.get("doi"),
                "arxiv_id": hit.get("arxiv_id"),
                "verified": bool(hit.get("verified")),
                "suggested_cite": cite,
                "score": hit.get("score"),
            }
        )
    return out
