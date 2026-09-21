---
name: papermemory
description: >
  Academic paper memory for understanding papers and writing papers. Use for
  literature, citations, claims, manuscripts, related work, bibtex, DOI/arXiv
  ingest, cite-check, and recap of a writing project. Triggers: paper memory,
  remember this paper, cite this, citation check, literature review, manuscript
  status, /papermemory. Not for coding-session memory or the lab notebook.
license: MIT
metadata:
  version: "0.1.0"
  source: https://github.com/raktim-mondol/papermemory
---

# PaperMemory

Local academic memory on the ResearchCraft preset. Database: `~/.local/share/papermemory/papermemory.db` (override `PAPERMEMORY_DB`). The plugin auto-installs the CLI and mounts MCP tools; do not `pip install` a second copy.

Prefer MCP tools `mcp__papermemory__*` when they are in the catalog. CLI fallback: `papermemory <cmd> --json`.

## First action

On any paper-writing or paper-reading task, call `mcp__papermemory__papermemory_recap` (pass `project` when you know the manuscript slug). If the slug is unknown, omit `project`. Workspace directory name is a reasonable default slug (`journal_paper_writing` → `journal-paper-writing`).

If MCP is absent:

```bash
papermemory recap --json --project <slug>
```

## MCP tools

| Goal | Tool |
| --- | --- |
| Writing-project briefing | `mcp__papermemory__papermemory_recap` (`project`) |
| Search papers/claims/chunks/notes | `mcp__papermemory__papermemory_search` (`query`, optional `kind`, `project`, `limit`) |
| Ingest PDF / bib / markdown / manuscript path | `mcp__papermemory__papermemory_ingest` (`path`, optional `project`, `kind`) |
| Ingest arXiv / DOI | `mcp__papermemory__papermemory_ingest` (`arxiv` or `doi`, optional `project`) |
| Show a paper | `mcp__papermemory__papermemory_get` (`key` = id or bibtex key) |
| Find a citation | `mcp__papermemory__papermemory_cite` (`query`) |
| Check manuscript cites | `mcp__papermemory__papermemory_cite_check` (`manuscript` slug) |
| Save a decision | `mcp__papermemory__papermemory_remember` (`content`, optional `concepts`, `project`) |
| Save a durable rule | `mcp__papermemory__papermemory_lesson` (`content`, optional `concepts`, `project`) |
| Store a claim | `mcp__papermemory__papermemory_claim` (`text`, optional `paper`, `evidence`, `status`) |

`paper_download` already ingests the saved PDF (and DOI metadata when given). Still ingest a DOI/arXiv you have not downloaded, a local `.bib` / manuscript tree, or a PDF obtained some other way.

## CLI fallback

| Goal | Command |
| --- | --- |
| Ingest a manuscript tree | `papermemory ingest PATH --kind manuscript --project SLUG --json` |
| Ingest PDF / bib / markdown | `papermemory ingest PATH --project SLUG --json` |
| Ingest arXiv / DOI | `papermemory ingest --arxiv ID --project SLUG --json` / `--doi DOI` |
| Search | `papermemory search QUERY --json` |
| Show a paper | `papermemory paper BIBKEY --json` |
| Find a citation | `papermemory cite QUERY --json` |
| Check manuscript cites | `papermemory cite-check SLUG --json` |
| Save a decision | `papermemory remember TEXT --concepts a,b --project SLUG --json` |
| Save a durable rule | `papermemory lesson TEXT --concepts a,b --json` |
| Store a claim | `papermemory claim TEXT --paper ID --evidence QUOTE --status extracted --json` |

## Citation integrity

- Cite only papers returned by `papermemory_cite` or `papermemory_get` (or the matching CLI).
- If the hit is `verified: false` / `UNVERIFIED`, say so and do not treat the metadata as confirmed.
- If cite returns no hits, say that memory has no source. Do not invent a title, year, DOI, or bibtex key.
- Before finishing a section, run `cite_check`. Missing keys must be ingested or removed, not guessed.

## Understanding a paper

1. `paper_download` (DOI or URL) or `ingest` the PDF / arXiv / DOI.
2. `pdf_to_markdown` to read the PDF; `papermemory_get` for stored claims and chunks.
3. Save claims with an evidence quote and `status=extracted` until the quote is checked against stored paper text.
4. `remember` the reading notes tagged with the bibtex key.

## Writing a paper

1. `recap` for venue, citation style, section word counts, open reviewer comments, terminology.
2. Search claims/papers before writing related work. New literature still comes from `consensus_search` + `parallel_search`; ingest what you will cite.
3. `remember` outline decisions and rejected phrasings.
4. `cite_check` before calling a section done.

## Do not

- Do not use the lab `notebook`, coding-agent memory, or generic session notes as the source of citations.
- Do not mark a claim `verified` unless the evidence quote is in the stored paper text.
- Do not `pip install papermemory` / `uv add papermemory` yourself — the plugin installs into `~/.dsh/papermemory` (or uses PATH / `PAPERMEMORY_CLI`).
