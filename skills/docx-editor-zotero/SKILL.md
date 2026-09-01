---
name: docx-editor-zotero
description: Edit Word (.docx) documents — delete/reorder paragraphs, bulk text replacement — while preserving 100% of Zotero field codes, citations, and bibliography references. Use whenever a .docx to be edited contains Zotero citations, since normal paragraph deletion/reordering silently orphans or corrupts citation fields.
license: MIT
metadata:
  version: "1.0"
  skill-author: K-Dense Inc.
---

# docx-editor-zotero

## Overview

Editing a Word document that contains Zotero citations with ordinary XML
surgery (or by hand) easily orphans citation field codes or breaks the
bibliography. This skill wraps `python-docx`-level `.docx` edits — deleting
paragraphs, reordering paragraphs, bulk text replacement — with citation
tracking so every Zotero field code, in-text citation, and bibliography entry
survives the edit, and produces a JSON audit log of exactly what changed.

Zero external dependencies — pure Python 3.10+ standard library
(`xml.etree.ElementTree`, `zipfile`, `json`). Run it with `uv run python`
per this plugin's Python convention; no `uv add` needed.

## When to use this skill

Reach for this instead of hand-editing `.docx` XML or reaching for
`python-docx` directly whenever the document being edited has Zotero
citations and the task is: removing sections/paragraphs, reordering them, or
bulk text replacement (e.g. terminology changes across a manuscript) — not
for documents without Zotero fields, where the `docx` skill's normal tooling
is sufficient.

## Basic workflow

1. Load the input `.docx` with `WordEditor` (`scripts/word_editor.py`).
2. It extracts every Zotero citation and its position before any edit.
3. Apply structural modifications in this order: delete → reorder → replace.
4. It recalculates endnote/citation IDs and flags orphaned citations.
5. Validate document integrity, then save the edited `.docx` plus a
   `*_log.json` audit trail (timestamps, paragraphs deleted, citations
   orphaned/preserved, text replacements, validation results).

```python
from word_editor import WordEditor

editor = WordEditor("input.docx")
editor.delete_paragraphs([1, 3, 5])
editor.move_paragraph(2, 0)
editor.replace_text("HSG", "Tkk")
editor.save("output.docx")
```

Run it from inside `scripts/` (or add that directory to `sys.path`) since
`word_editor.py` imports `zotero_docx_preserver.py` as a sibling module —
both ship together in `scripts/`.

## Notes

- After editing, the user may need to refresh Zotero fields in Word via the
  Zotero menu (Word doesn't always auto-refresh field display after an
  out-of-band XML edit).
- Handles documents containing tables and complex nested elements.
- The original file is never modified in place — always writes a new output
  path, so edits are trivially reversible.
- See `references/EXAMPLES.md` for worked examples of each operation
  (delete, reorder, replace, and combinations) with expected output.
