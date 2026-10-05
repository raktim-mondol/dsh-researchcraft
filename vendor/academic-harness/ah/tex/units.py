"""Units and stable anchors (design 4.3).

A unit is one paragraph, or one float or display environment. Each carries a comment anchor
`%% @unit <id> h=<hash>` on the line directly above it. The id is assigned once and never
reused; the hash follows the text, so a verdict cached against the hash is invalidated when
(and only when) the unit changes.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..project import Project
from ..util import collapse_ws, sha1
from .text import (RE_ANCHOR, find_envs, is_structure_only, mask_ranges, split_paragraphs,
                   strip_comments, word_count)


@dataclass
class Unit:
    uid: str | None
    file: str            # relative to the TeX root
    start: int           # first source line (1-based)
    end: int
    kind: str            # para | float | display
    raw: str             # source text of the unit, comments included
    norm: str            # comments stripped, whitespace collapsed
    hash: str            # short hash of `norm`
    anchor_line: int | None = None
    anchor_hash: str | None = None
    words: int = 0


@dataclass
class ParsedFile:
    file: str
    lines: list[str]
    units: list[Unit]
    orphan_anchors: list[tuple[int, str]] = field(default_factory=list)  # (line, id)
    all_anchors: dict[int, tuple[str, str | None]] = field(default_factory=dict)


def unit_hash(norm: str) -> str:
    return sha1(norm, 8)


def parse_file(project: Project, path: Path) -> ParsedFile:
    rel = project.rel(path)
    raw_text = path.read_text(errors="replace")
    lines = raw_text.split("\n")
    anchors: dict[int, tuple[str, str | None]] = {}
    for i, line in enumerate(lines, 1):
        m = RE_ANCHOR.match(line)
        if m:
            anchors[i] = (m.group(1), m.group(2))
    stripped = strip_comments(raw_text)
    envs = find_envs(stripped)
    masked = mask_ranges(stripped, envs)

    units: list[Unit] = []
    for s, e, p in split_paragraphs(masked):
        if is_structure_only(p) or word_count(p) < 5:
            continue
        raw = "\n".join(lines[s - 1:e])
        norm = collapse_ws(strip_comments(raw))
        units.append(Unit(None, rel, s, e, "para", raw, norm, unit_hash(norm), words=word_count(p)))
    for name, a, b in envs:
        s = stripped.count("\n", 0, a) + 1
        e = stripped.count("\n", 0, b) + 1
        raw = "\n".join(lines[s - 1:e])
        norm = collapse_ws(strip_comments(raw))
        kind = "display" if name in ("equation", "equation*", "align", "align*", "gather", "gather*") else "float"
        units.append(Unit(None, rel, s, e, kind, raw, norm, unit_hash(norm), words=word_count(norm)))
    units.sort(key=lambda u: (u.start, u.end))

    used = set()
    for u in units:
        al = u.start - 1
        if al in anchors:
            u.uid, u.anchor_hash = anchors[al]
            u.anchor_line = al
            used.add(al)
    orphans = [(ln, anchors[ln][0]) for ln in sorted(anchors) if ln not in used]
    return ParsedFile(rel, lines, units, orphans, anchors)


# ---------------- registry of ids ----------------

class UnitRegistry:
    """`.ah/units.json`: id prefix per file and the highest number ever issued per prefix."""

    def __init__(self, project: Project):
        self.path = project.state_dir / "units.json"
        self.data = {"prefix": {}, "max": {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    def prefix_for(self, file: str, existing_ids: list[str]) -> str:
        if file in self.data["prefix"]:
            return self.data["prefix"][file]
        pref = None
        for uid in existing_ids:
            m = re.match(r"^(.*)\.[pfd]\d+$", uid)
            if m:
                pref = m.group(1)
                break
        if pref is None:
            generic = {"sections", "chapters", "appendices", "src", "tables", "figures", "."}
            parts = [re.sub(r"^\d+[_-]?", "", x) or x for x in (list(Path(file).parent.parts) + [Path(file).stem])]
            parts = [x for x in parts if x not in generic and x != "index" or x == parts[-1]]
            pref = re.sub(r"[^A-Za-z0-9_]+", "_", "_".join(parts)).strip("_").lower() or "unit"
            taken = set(self.data["prefix"].values())
            base, n = pref, 2
            while pref in taken:
                pref, n = f"{base}{n}", n + 1
        self.data["prefix"][file] = pref
        return pref

    def next_id(self, prefix: str, kind: str) -> str:
        letter = {"para": "p", "float": "f", "display": "d"}[kind]
        key = f"{prefix}.{letter}"
        n = self.data["max"].get(key, 0) + 1
        self.data["max"][key] = n
        return f"{prefix}.{letter}{n:03d}"

    def note_existing(self, uid: str):
        m = re.match(r"^(.*\.[pfd])(\d+)$", uid)
        if m:
            n = int(m.group(2))
            if n > self.data["max"].get(m.group(1), 0):
                self.data["max"][m.group(1)] = n

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True))


def anchor_line_text(uid: str, h: str) -> str:
    return f"%% @unit {uid}  h={h}"


def sync_project(project: Project, write: bool = True) -> dict:
    """Insert missing anchors and refresh hashes. Returns a summary; writes files if `write`."""
    reg = UnitRegistry(project)
    summary = {"files": 0, "added": 0, "hash_updated": 0, "unchanged": 0, "orphan_anchors": []}
    for path in project.prose_files():
        pf = parse_file(project, path)
        existing = [u.uid for u in pf.units if u.uid]
        for uid in list(existing) + [a[0] for a in pf.all_anchors.values()]:
            reg.note_existing(uid)
        prefix = reg.prefix_for(pf.file, existing)
        edits: list[tuple[int, str, str]] = []  # (line index to act on, action, text)
        changed = False
        for u in pf.units:
            if u.uid is None:
                uid = reg.next_id(prefix, u.kind)
                edits.append((u.start, "insert", anchor_line_text(uid, u.hash)))
                summary["added"] += 1
                changed = True
            elif u.anchor_hash != u.hash:
                edits.append((u.anchor_line, "replace", anchor_line_text(u.uid, u.hash)))
                summary["hash_updated"] += 1
                changed = True
            else:
                summary["unchanged"] += 1
        for ln, uid in pf.orphan_anchors:
            summary["orphan_anchors"].append(f"{pf.file}:{ln} {uid}")
        if changed:
            summary["files"] += 1
            if write:
                lines = list(pf.lines)
                for ln, action, text in sorted(edits, key=lambda e: -e[0]):
                    if action == "insert":
                        lines.insert(ln - 1, text)
                    else:
                        lines[ln - 1] = text
                path.write_text("\n".join(lines))
    if write:
        reg.save()
    return summary


def load_units(project: Project) -> tuple[list[Unit], list[ParsedFile]]:
    parsed = [parse_file(project, p) for p in project.prose_files()]
    return [u for pf in parsed for u in pf.units], parsed
