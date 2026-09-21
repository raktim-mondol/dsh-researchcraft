from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from papermemory.bibtex import parse_bibtex
from papermemory.citations import extract_cite_keys
from papermemory.db import Store
from papermemory.pdf import extract_pdf
from papermemory.understand import understand_text
from papermemory.util import normalize_doi, slugify, strip_tex_comments, word_count

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "figures", "qa_crops", "_work"}


def ingest_bibtex(store: Store, text: str, *, project_id: str | None = None, source: str | None = None) -> list[dict[str, Any]]:
    papers = []
    for entry in parse_bibtex(text):
        record = store.upsert_paper(
            {
                **entry,
                "project_id": project_id,
                "source_type": "bibtex",
                "verified": 1 if entry.get("doi") or entry.get("arxiv_id") else 0,
                "verification_note": "has identifier" if (entry.get("doi") or entry.get("arxiv_id")) else "bibtex-only",
            }
        )
        if project_id:
            ms = store.get_manuscript(project_id)
            if ms:
                store.add_relation("manuscript", ms["id"], "cites", "paper", record["id"], evidence=source)
        papers.append(record)
    return papers


def ingest_pdf(
    store: Store,
    path: Path,
    *,
    project_id: str | None = None,
    understand: bool = True,
    doi: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    extracted = extract_pdf(path)
    doi_n = normalize_doi(doi)
    existing = store.find_paper(doi=doi_n, pdf_path=str(path.expanduser().resolve())) if (doi_n or path) else None
    heading = (title or "").strip()
    if not heading and existing and existing.get("title"):
        heading = existing["title"]
    if not heading:
        heading = (extracted.get("title") or path.stem).strip()
    paper = store.upsert_paper(
        {
            "title": heading,
            "authors": extracted.get("authors") or [],
            "doi": doi_n,
            "url": f"https://doi.org/{doi_n}" if doi_n else None,
            "pdf_path": str(path.expanduser().resolve()),
            "source_type": "pdf",
            "project_id": project_id,
            "abstract": None,
            "verified": 1 if doi_n else 0,
            "verification_note": "doi" if doi_n else "local-pdf",
        }
    )
    summary = None
    if understand:
        summary = understand_text(extracted["text"])
        if summary.get("abstract") and not paper.get("abstract"):
            paper = store.upsert_paper({**paper, "abstract": summary["abstract"], "authors": paper.get("authors") or []})
        store.replace_chunks(paper["id"], summary["chunks"])
        for claim in summary["claims"]:
            store.add_claim({**claim, "paper_id": paper["id"]})
    else:
        from papermemory.understand import chunk_text

        chunks = []
        for page in extracted["pages"]:
            chunks.extend(chunk_text(page["text"], page=page["page"]))
        store.replace_chunks(paper["id"], chunks)
    return {"paper": paper, "understand": summary, "pages": extracted["page_count"]}


def ingest_markdown(
    store: Store,
    path: Path,
    *,
    project_id: str | None = None,
    doi: str | None = None,
    pdf_path: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    heading = title
    if not heading:
        heading = path.stem
        for line in text.splitlines():
            if line.startswith("# "):
                heading = line[2:].strip()
                break
    doi_n = normalize_doi(doi)
    resolved_pdf = str(Path(pdf_path).expanduser().resolve()) if pdf_path else None
    paper = store.upsert_paper(
        {
            "title": heading,
            "doi": doi_n,
            "url": f"https://doi.org/{doi_n}" if doi_n else None,
            "pdf_path": resolved_pdf,
            "source_type": "markdown",
            "project_id": project_id,
            "abstract": text[:1500],
            "verified": 1 if doi_n else 0,
            "verification_note": "doi" if doi_n else None,
        }
    )
    summary = understand_text(text)
    store.replace_chunks(paper["id"], summary["chunks"])
    return {"paper": paper, "understand": summary}


def ingest_arxiv(store: Store, arxiv_id: str, *, project_id: str | None = None) -> dict[str, Any]:
    from papermemory.scholar import fetch_arxiv

    meta = fetch_arxiv(arxiv_id)
    paper = store.upsert_paper({**meta, "project_id": project_id})
    if project_id:
        ms = store.get_manuscript(project_id)
        if ms:
            store.add_relation("manuscript", ms["id"], "cites", "paper", paper["id"])
    return paper


def ingest_doi(store: Store, doi: str, *, project_id: str | None = None) -> dict[str, Any]:
    from papermemory.scholar import fetch_crossref

    meta = fetch_crossref(doi)
    paper = store.upsert_paper({**meta, "project_id": project_id})
    if project_id:
        ms = store.get_manuscript(project_id)
        if ms:
            store.add_relation("manuscript", ms["id"], "cites", "paper", paper["id"])
    return paper


def _outline_contributions(text: str) -> list[str]:
    cue = re.compile(
        r"^(context|gap|objective|aim|method|results?|implication|contribution|limitation)\s*:\s*",
        re.I,
    )
    preferred: list[str] = []
    fallback: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^\s*(?:[-*]|\d+[\.)])\s+(.*)", line)
        if not m:
            continue
        item = re.sub(r"\*+", "", m.group(1)).strip()
        if not (40 <= len(item) <= 400) or item.startswith("`") or "In-text:" in item:
            continue
        if cue.match(item):
            preferred.append(item)
        elif item.endswith("?") or "develop" in item.lower() or "we " in item.lower():
            fallback.append(item)
    return (preferred or fallback)[:8]


def ingest_manuscript(store: Store, root: Path, *, slug: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    readme = ""
    outline_text = ""
    for name in ("Journal_Paper_Outline.md", "review_protocol.md", "README.md"):
        path = root / name
        if path.exists():
            blob = path.read_text(encoding="utf-8", errors="replace")
            readme += "\n" + blob
            if name != "README.md":
                outline_text += "\n" + blob
    title = root.name
    venue = None
    style = None
    if "SCANDY" in readme or (root / "Journal_Paper_Outline.md").exists():
        m = re.search(r"\*\*\"([^\"]+)\"\*\*", readme) or re.search(r"^# .*: (.+)$", readme, re.M)
        if m:
            title = m.group(1)
        vm = re.search(r"Primary[:\*]*\s*\**([^*\n]+)", readme)
        if vm:
            venue = vm.group(1).strip(" *")
        if "Harvard" in readme:
            style = "elsevier-harvard"
    slug = slug or slugify(title)
    ms = store.upsert_manuscript(
        {
            "title": title,
            "slug": slug,
            "target_venue": venue,
            "citation_style": style,
            "root_path": str(root),
            "status": "draft",
        }
    )
    bib_papers = []
    for bib in sorted(root.glob("*.bib")):
        bib_papers.extend(ingest_bibtex(store, bib.read_text(encoding="utf-8", errors="replace"), project_id=slug, source=str(bib)))
    sections: list[dict[str, Any]] = []
    section_dir = root / "sections"
    if section_dir.exists():
        for tex in sorted(section_dir.glob("*.tex")):
            text = tex.read_text(encoding="utf-8", errors="replace")
            keys = extract_cite_keys(text)
            paper_map = {
                row["bibtex_key"]: row["id"]
                for row in store.conn.execute("SELECT id, bibtex_key FROM papers WHERE bibtex_key IS NOT NULL").fetchall()
            }
            for key in set(keys):
                if key in paper_map:
                    store.add_relation("manuscript", ms["id"], "cites", "paper", paper_map[key], evidence=str(tex))
            sections.append(
                {
                    "name": tex.stem,
                    "path": str(tex),
                    "word_count": word_count(strip_tex_comments(text)),
                    "status": "draft" if word_count(text) > 40 else "empty",
                }
            )
    elif (root / "main.tex").exists():
        text = (root / "main.tex").read_text(encoding="utf-8", errors="replace")
        sections.append({"name": "main", "path": str(root / "main.tex"), "word_count": word_count(strip_tex_comments(text)), "status": "draft"})
    store.replace_sections(ms["id"], sections)
    contributions = _outline_contributions(outline_text or readme)
    if contributions:
        store.replace_contributions(ms["id"], contributions[:8])
    notes = []
    for name in ("Journal_Paper_Outline.md", "review_protocol.md", "REVIEW.md"):
        path = root / name
        if path.exists():
            notes.append(path.read_text(encoding="utf-8", errors="replace")[:4000])
    if notes:
        store.remember(
            f"Manuscript {slug} notes:\n" + "\n---\n".join(notes)[:3500],
            concepts=[slug, "manuscript", "outline"],
            project_id=slug,
            manuscript_id=ms["id"],
            tier="episodic",
        )
    return {
        "manuscript": store.get_manuscript(slug),
        "papers": len(bib_papers),
        "sections": sections,
        "contributions": contributions[:8],
    }


def ingest_path(
    store: Store,
    path: Path,
    *,
    project_id: str | None = None,
    kind: str = "auto",
    progress: Callable[[str], None] | None = None,
    doi: str | None = None,
    title: str | None = None,
    pdf_path: str | None = None,
) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if kind == "auto":
        if path.is_dir():
            if (path / "main.tex").exists() or (path / "references.bib").exists() or (path / "sections").exists():
                kind = "manuscript"
            else:
                kind = "dir"
        else:
            suffix = path.suffix.lower()
            kind = {".pdf": "pdf", ".bib": "bibtex", ".md": "markdown", ".tex": "tex"}.get(suffix, "file")
    if progress:
        progress(f"ingest {kind}: {path}")
    if kind == "manuscript":
        return ingest_manuscript(store, path, slug=project_id)
    if kind == "pdf":
        return ingest_pdf(store, path, project_id=project_id, doi=doi, title=title)
    if kind == "bibtex":
        papers = ingest_bibtex(store, path.read_text(encoding="utf-8", errors="replace"), project_id=project_id, source=str(path))
        return {"papers": papers, "count": len(papers)}
    if kind == "markdown":
        return ingest_markdown(store, path, project_id=project_id, doi=doi, pdf_path=pdf_path, title=title)
    if kind == "tex":
        return ingest_markdown(store, path, project_id=project_id, doi=doi, pdf_path=pdf_path, title=title)
    if kind == "dir":
        results = []
        for child in sorted(path.rglob("*")):
            if not child.is_file():
                continue
            if any(part in SKIP_DIRS for part in child.parts):
                continue
            if child.suffix.lower() not in {".pdf", ".bib", ".md"}:
                continue
            try:
                results.append(ingest_path(store, child, project_id=project_id, kind="auto"))
            except Exception as exc:
                results.append({"path": str(child), "error": str(exc)})
        return {"count": len(results), "items": results}
    raise ValueError(f"unsupported ingest kind: {kind}")
