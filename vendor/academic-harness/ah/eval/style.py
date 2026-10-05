"""Evaluate T5 pattern lints against a human-labelled set (design 6.6, 12.3).

A lint is promoted from info-only to the catalogue default (minor) when precision and
recall on this set clear the bars below. A lint that fails is dropped (not run).
STY-02 (model-scored overclaim / calibration / ai_prose) is recorded as dropped: the
example's own Jev run flagged 82/94 paragraphs at the 0.5 gate and `ai_prose` did not
discriminate (median 0.67). Reopen only through the 6.10 admission test on this file.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..checks.t5_style import LINTS, lint_text

PROMOTE_PRECISION = 0.80
PROMOTE_RECALL = 0.50
MIN_POS = 2


def _metrics(tp: int, fp: int, fn: int, tn: int) -> dict:
    prec = tp / (tp + fp) if (tp + fp) else float("nan")
    rec = tp / (tp + fn) if (tp + fn) else float("nan")
    spec = tn / (tn + fp) if (tn + fp) else float("nan")
    flag = (tp + fp) / (tp + fp + fn + tn) if (tp + fp + fn + tn) else float("nan")
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": prec, "recall": rec,
            "specificity": spec, "flag_rate": flag, "n": tp + fp + fn + tn}


def run_style_eval(golden: Path) -> dict:
    rows = [json.loads(l) for l in golden.read_text().splitlines() if l.strip()]
    names = list(LINTS)
    counts = {n: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for n in names}
    overall = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}   # any-lint vs edit=needed
    per_row = []
    for r in rows:
        hits = {n for n, _ in lint_text(r["text"], names)}
        labels = r.get("labels") or {}
        edit = r.get("edit") == "needed"
        any_hit = bool(hits)
        if any_hit and edit:
            overall["tp"] += 1
        elif any_hit and not edit:
            overall["fp"] += 1
        elif (not any_hit) and edit:
            overall["fn"] += 1
        else:
            overall["tn"] += 1
        row_out = {"id": r["id"], "edit": r.get("edit"), "hits": sorted(hits), "misses": []}
        for n in names:
            y = int(labels.get(n, 0))
            yhat = int(n in hits)
            if y and yhat:
                counts[n]["tp"] += 1
            elif yhat and not y:
                counts[n]["fp"] += 1
                row_out["misses"].append(f"fp:{n}")
            elif y and not yhat:
                counts[n]["fn"] += 1
                row_out["misses"].append(f"fn:{n}")
            else:
                counts[n]["tn"] += 1
        per_row.append(row_out)
    dimensions = {}
    promote, drop = [], []
    for n, c in counts.items():
        m = _metrics(c["tp"], c["fp"], c["fn"], c["tn"])
        n_pos = c["tp"] + c["fn"]
        prec, rec = m["precision"], m["recall"]
        ok = (n_pos >= MIN_POS and prec == prec and rec == rec
              and prec >= PROMOTE_PRECISION and rec >= PROMOTE_RECALL)
        m["decision"] = "promote" if ok else "drop"
        m["n_pos"] = n_pos
        dimensions[n] = m
        (promote if ok else drop).append(n)
    return {
        "golden": str(golden),
        "n": len(rows),
        "bars": {"precision": PROMOTE_PRECISION, "recall": PROMOTE_RECALL, "min_pos": MIN_POS},
        "dimensions": dimensions,
        "overall_edit_needed": _metrics(**overall),
        "promote": promote,
        "drop": drop,
        "sty02_model": {
            "decision": "drop",
            "reason": "Jev ai_prose median 0.67 with 76/94 above 0.5 on the example; overclaim/directive at the 0.5 gate flagged 82/94. Code lints replace it (design 6.6, 6.10).",
        },
        "rows": per_row,
    }
