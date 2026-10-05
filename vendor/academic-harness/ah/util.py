"""Small shared helpers. No project knowledge here."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def sha1(s: str | bytes, n: int = 40) -> str:
    b = s.encode() if isinstance(s, str) else s
    return hashlib.sha1(b).hexdigest()[:n]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1
