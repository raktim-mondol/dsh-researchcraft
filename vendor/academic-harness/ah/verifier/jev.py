"""Jev (TypeSafe System One) as a passage scorer, for the admission test (design 6.10).

Jev returns typed answers and probabilities, not text, so it cannot produce a quote. The pattern is the one in
TypeSafe's citation-check cookbook: code retrieves candidate passages, Jev judges one (claim, passage) pair at a
time, and the "quote" is the passage itself, selected and therefore verbatim by construction.

Pre-registered before any result was read (2026-10-01), on the 32-claim golden set of Phase 2:
  primary score   S = max over the top-5 passages of P(supports)
  admission bar   AUROC(S) >= 0.70  AND  flag lift >= 1.5 at threshold 0.8 (flag = S < 0.8)
Thresholds 0.5, 0.8 and 0.9 are reported; 0.8 is the cookbook's suggested start and is the only one the bar uses.
Secondary scores (not used for admission): S2 = max_i min(P(supports), same_metric, same_scope).
The key is read from TYPESAFE_API_KEY only; it is never printed, logged, cached or written to a manifest.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
QUESTIONS = {
    "relation": {
        "type": "choice",
        "instructions": "How does `passage` relate to the statement `claim`?",
        "criteria": {
            "supports": "The passage states the claim, including its specific values, metric and scope, or directly implies it.",
            "contradicts": "The passage states something that conflicts with the claim, for example different values or the opposite direction.",
            "says_nothing": "The passage does not address what the claim asserts, either way.",
        },
    },
    "same_metric": {"type": "noul", "instructions": "Does `passage` report the same kind of measurement that `claim` states (for example AUROC versus accuracy, F1, or a percentage gap)?"},
    "same_scope": {"type": "noul", "instructions": "Does `passage` concern the same dataset, task, population and method as `claim`?"},
}


class JevError(Exception):
    pass


def api_key() -> str:
    k = os.environ.get("TYPESAFE_API_KEY")
    if not k:
        raise JevError("TYPESAFE_API_KEY is not set in the environment")
    return k


def score_pair(claim: str, passage: str, key: str, retries: int = 5) -> dict:
    body = json.dumps({"state": {"claim": claim, "passage": passage}, "model": MODEL, "questions": QUESTIONS}).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read())
            a = resp["answers"]
            probs = a["relation"]["probabilities"]
            return {"p_supports": probs.get("supports", 0.0), "p_contradicts": probs.get("contradicts", 0.0),
                    "p_says_nothing": probs.get("says_nothing", 0.0), "same_metric": a["same_metric"]["noul"],
                    "same_scope": a["same_scope"]["noul"], "tokens_in": resp.get("usage", {}).get("input_tokens", 0),
                    "tokens_out": resp.get("usage", {}).get("output_tokens", 0)}
        except urllib.error.HTTPError as e:
            if e.code in (429, 529) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise JevError(f"HTTP {e.code} from TypeSafe")       # status only: the body is never printed
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise JevError(f"network error: {e.reason}")
    raise JevError("unreachable")
