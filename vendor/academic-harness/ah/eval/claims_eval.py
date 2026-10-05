"""Evaluate evidence checking on labelled claims (design 12.2, 6.10 admission test).

Unlike the Phase 0 probe, passages are NOT handed over: the engine retrieves them from the full source,
so retrieval recall is part of the result. Code baselines are reported next to the model verdicts.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..project import Project
from ..sources.index import Index
from ..context import parse_bib
from ..sources.registry import doi_index, load_registry, resolve_all, source_map
from ..verifier.backends import Backend
from ..verifier.verify import Cache, norm_text, number_found, verify

KEY = re.compile(r"[a-z][a-z\-]+\d{4}[a-z]+")


def clean_claim(s: str) -> str:
    s = re.sub(r"\((?:0\d_[a-z]+|\d+_results|abstract|S\d)[^)]*\)", "", s)      # manuscript location markers
    s = re.sub(r"\((?:Fig|Table)\.?[^)]*\)", "", s)
    return re.sub(r"\s+", " ", s).strip()


def claim_numbers(s: str) -> list[str]:
    out = []
    for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)(\s*%)?", s):
        t = m.group(1)
        if re.fullmatch(r"(19|20)\d\d", t) and not m.group(2):
            continue
        if len(t.replace(".", "")) >= 2 or "." in t:
            out.append(t + ("%" if m.group(2) else ""))
    return list(dict.fromkeys(out))


def _toks(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", norm_text(s))


def covers(fragment: str, passage: str, share: float = 0.8) -> bool:
    """The passage holds the audited fragment: most of the fragment's tokens occur in it. Tolerant on purpose,
    because the golden quotes were typed by hand and differ from the source in punctuation, spacing and sometimes a digit."""
    ft = _toks(fragment)
    if len(ft) < 5:
        return False
    pt = set(_toks(passage))
    return sum(t in pt for t in ft) / len(ft) >= share


def auroc(pos: list[float], neg: list[float]) -> float:
    if not pos or not neg:
        return float("nan")
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def run_claims_eval(project: Project, golden: Path, backend: Backend | None, k: int = 3, limit: int = 0, repeat: int = 1,
                    workers: int = 4, use_cache: bool = True, jev: bool = False) -> dict:
    rows = [json.loads(l) for l in golden.read_text().splitlines() if l.strip()]
    if limit:
        rows = rows[:limit]
    reg, smap, idx, dois = load_registry(project), source_map(project), Index(project), doi_index(project)
    bib = {}
    for bp in project.bib_files():
        bib.update(parse_bib(bp.read_text(errors="replace"), bp.name)[0])
    items = []
    for r in rows:
        keys = list(dict.fromkeys(KEY.findall(r["key"])))
        srcs = []
        for key in keys:
            paths = resolve_all(project, key, reg, smap, bib, dois)
            if paths:
                idx.ensure(key, paths)
                srcs.append(key)
        text = clean_claim(r["claim"])
        nums = claim_numbers(text)
        items.append({"row": r, "keys": keys, "srcs": srcs, "text": text, "nums": nums})
    usable = [i for i in items if i["srcs"]]
    for i in usable:
        i["passages"] = idx.search(i["srcs"], i["text"], k)
        frags = [x for q in i["row"]["passage"].split("\n") for x in re.split(r"…|\.\.\.", q) if len(norm_text(x)) >= 40]
        i["retrieved"] = any(covers(f, p.text) for f in frags for p in i["passages"]) if frags else None
        have = set().union(*[idx.all_text_numbers(s) for s in i["srcs"]])
        i["b_all"] = (sum(number_found(n, have) for n in i["nums"]) / len(i["nums"])) if i["nums"] else 0.5
        topnums = set().union(*[set(re.findall(r"\d+(?:\.\d+)?", p.text.replace(",", ""))) for p in i["passages"]]) if i["passages"] else set()
        i["b_top"] = (sum(number_found(n, topnums) for n in i["nums"]) / len(i["nums"])) if i["nums"] else 0.5

    res: dict = {"rows": len(rows), "usable": len(usable), "unresolved": len(items) - len(usable)}
    rec = [i["retrieved"] for i in usable if i["retrieved"] is not None]
    res["retrieval_recall_at_k"] = (sum(rec) / len(rec)) if rec else None
    res["retrieval_k"] = k
    pos = [i for i in usable if i["row"]["human_verdict"] == "SUPPORTED"]
    neg = [i for i in usable if i["row"]["human_verdict"] != "SUPPORTED"]
    res["n_supported"], res["n_not_supported_or_partial"] = len(pos), len(neg)
    res["auroc_numbers_in_whole_source"] = auroc([i["b_all"] for i in pos], [i["b_all"] for i in neg])
    res["auroc_numbers_in_top_passages"] = auroc([i["b_top"] for i in pos], [i["b_top"] for i in neg])

    if backend is not None:
        cache = Cache(project) if use_cache else None
        def go(i):
            return verify(i["text"], i["nums"], i["passages"], backend, cache, True)
        passes = []
        for rep in range(repeat):
            if rep > 0:
                cache = None          # a repeat measures the model, not the cache
            with ThreadPoolExecutor(max_workers=workers) as ex:
                passes.append(list(ex.map(go, usable)))
        first = passes[0]
        conf: dict = {}
        agree = bin_ok = 0
        def three(v):
            return {"SUPPORTED": "SUPPORTED", "PARTIAL": "PARTIAL", "CONTESTED": "PARTIAL", "NOT_SUPPORTED": "NOT_SUPPORTED",
                    "NOT_IN_SOURCE": "NOT_SUPPORTED"}.get(v, "ERROR")
        for i, r in zip(usable, first):
            h, m = i["row"]["human_verdict"], three(r.verdict)
            conf[(h, m)] = conf.get((h, m), 0) + 1
            agree += h == m
            bin_ok += (h == "SUPPORTED") == (m == "SUPPORTED") and m != "ERROR"
        res["verifier"] = {"model": backend.model, "three_class_agreement": agree / len(usable) if usable else None,
                           "supported_vs_not_accuracy": bin_ok / len(usable) if usable else None,
                           "confusion": {f"{h}->{m}": n for (h, m), n in sorted(conf.items())},
                           "errors": sum(r.verdict == "ERROR" for r in first),
                           "calls": sum(r.calls for r in first), "tokens_in": sum(r.tokens_in for r in first),
                           "tokens_out": sum(r.tokens_out for r in first), "cached": sum(r.cached for r in first)}
        flagged = [three(r.verdict) not in ("SUPPORTED", "ERROR") for r in first]
        bad = [i["row"]["human_verdict"] != "SUPPORTED" for i in usable]
        tp = sum(f and b for f, b in zip(flagged, bad))
        nflag, nbad = sum(flagged), sum(bad)
        res["verifier"]["as_a_flag"] = {
            "flagged": f"{nflag}/{len(usable)}", "base_rate_of_real_problems": round(nbad / len(usable), 3) if usable else None,
            "precision": round(tp / nflag, 3) if nflag else None, "recall": round(tp / nbad, 3) if nbad else None,
            "lift_over_base_rate": round((tp / nflag) / (nbad / len(usable)), 2) if nflag and nbad else None}
        ps = [(three(r.verdict) == "SUPPORTED") for r in first]
        res["verifier"]["auroc_supported_flag"] = auroc([float(p) for p, i in zip(ps, usable) if i["row"]["human_verdict"] == "SUPPORTED"],
                                                      [float(p) for p, i in zip(ps, usable) if i["row"]["human_verdict"] != "SUPPORTED"])
        if repeat > 1:
            flips = sum(1 for j in range(len(usable)) if len({three(p[j].verdict) for p in passes}) > 1)
            res["verifier"]["flips_across_repeats"] = f"{flips}/{len(usable)}"
        res["detail"] = [{"id": i["row"]["id"], "key": i["keys"], "human": i["row"]["human_verdict"], "model": r.verdict,
                          "retrieved": i["retrieved"], "mismatch": r.mismatch, "note": r.note[:140], "error": r.error} for i, r in zip(usable, first)]
    if jev:
        res["jev"] = _jev_eval(usable, workers)
    idx.close()
    return res


def _jev_eval(usable: list, workers: int) -> dict:
    """Score every (claim, retrieved passage) pair with Jev; see ah/verifier/jev.py for the pre-registered bar."""
    from ..verifier.jev import JevError, api_key, score_pair
    key = api_key()
    pairs = [(i, p) for i in usable for p in i["passages"]]
    errors = []

    def go(ip):
        i, p = ip
        try:
            return score_pair(i["text"], p.text, key)
        except JevError as e:
            errors.append(str(e))
            return None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        out = list(ex.map(go, pairs))
    per: dict[int, list[dict]] = {}
    for (i, _p), o in zip(pairs, out):
        if o:
            per.setdefault(id(i), []).append(o)
    S, S2, bad = [], [], []
    for i in usable:
        sc = per.get(id(i), [])
        S.append(max((x["p_supports"] for x in sc), default=0.0))
        S2.append(max((min(x["p_supports"], x["same_metric"], x["same_scope"]) for x in sc), default=0.0))
        bad.append(i["row"]["human_verdict"] != "SUPPORTED")
    pos = [s for s, b in zip(S, bad) if not b]
    neg = [s for s, b in zip(S, bad) if b]
    res = {"pairs": len(pairs), "pairs_scored": sum(o is not None for o in out), "errors": len(errors),
           "tokens_in": sum(o["tokens_in"] for o in out if o), "tokens_out": sum(o["tokens_out"] for o in out if o),
           "auroc_primary_S": auroc(pos, neg),
           "auroc_secondary_S2": auroc([s for s, b in zip(S2, bad) if not b], [s for s, b in zip(S2, bad) if b]), "flags": {}}
    nbad = sum(bad)
    for t in (0.5, 0.8, 0.9):
        flagged = [s < t for s in S]
        tp = sum(f and b for f, b in zip(flagged, bad))
        nf = sum(flagged)
        res["flags"][str(t)] = {"flagged": f"{nf}/{len(usable)}", "precision": round(tp / nf, 3) if nf else None,
                                "recall": round(tp / nbad, 3) if nbad else None,
                                "lift": round((tp / nf) / (nbad / len(usable)), 2) if nf and nbad else None}
    f08 = res["flags"]["0.8"]
    res["admission_bar"] = {"rule": "AUROC(S) >= 0.70 and lift >= 1.5 at threshold 0.8",
                            "auroc_ok": res["auroc_primary_S"] >= 0.70, "lift_ok": bool(f08["lift"] and f08["lift"] >= 1.5)}
    res["admitted"] = res["admission_bar"]["auroc_ok"] and res["admission_bar"]["lift_ok"]
    res["per_claim"] = [{"id": i["row"]["id"], "human": i["row"]["human_verdict"], "S": round(s, 3)} for i, s in zip(usable, S)]
    return res
