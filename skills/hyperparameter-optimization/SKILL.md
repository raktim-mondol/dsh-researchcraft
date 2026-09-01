---
name: hyperparameter-optimization
description: Run an automated, disciplined hyperparameter-search loop to improve a deep learning or LLM model against a chosen metric — define the search space and selection metric before looking at results, delegate trials, track them against a baseline, and verify the winning configuration before claiming an improvement. Use when the task is "improve/tune this model's hyperparameters," not for a single one-off training run.
license: MIT
metadata:
  version: "1.0"
  skill-author: K-Dense Inc.
---

# Hyperparameter Optimization

## Overview

Adapted from [`K-Dense-AI/karpathy`](https://github.com/K-Dense-AI/karpathy), an
agentic ML-engineer built on Google ADK with a fixed "expert team" (Plan
Creator, Experiment Manager, Infra & Modal Operator, Evaluation Agent, …)
that it delegates to via a bespoke `delegate_task` tool. This skill keeps the
*idea* — a structured, resource-aware, verify-before-claiming loop for
improving a model against a metric — and re-expresses it with this plugin's
own tools instead of a second agent framework: `subagent` in place of
`delegate_task`, `notebook` in place of ad hoc `.md` files in a sandbox, and
the science-superpowers skills for the rigor a hyperparameter search
specifically needs (it is very easy to overfit to the validation set by
searching long enough).

## The loop

1. **Frame the objective before running anything.** What metric, on what
   held-out data, counts as "improved," and by how much would matter? Use
   the `framing-research-questions` skill if this isn't already pinned down
   — a vague "make it better" invites p-hacking the hyperparameters.
2. **Check compute before designing the sweep.** Call the
   `get-available-resources` skill/tooling to know what GPU/CPU/memory is
   actually available; a sweep sized for hardware you don't have just wastes
   the first several trials discovering that.
3. **Know the data and the current baseline.** If the dataset or existing
   training setup is unfamiliar, delegate a `subagent` to inspect it (the
   `exploratory-data-analysis` and `markitdown` skills cover most formats)
   and report the current baseline metric before any tuning starts — you
   can't claim an improvement without a documented starting point.
4. **Pre-register the search space and selection rule before looking at
   trial results.** Use `preregistering-analysis`: write down the
   hyperparameters in scope, their ranges, the search strategy (grid,
   random, Bayesian/Optuna-style, population-based), the metric that decides
   a winner, and how many trials you'll run — *before* the first result
   comes back. Log this as a `notebook` `decision` entry so a later reviewer
   can see the rule wasn't adjusted after seeing which configs did well.
5. **Delegate trials, don't run them all inline.** Dispatch each trial (or
   each independent batch of trials) via `subagent`, in parallel when they
   don't depend on each other's output; route training code itself through
   the relevant ML skill (`pytorch-lightning`, `transformers`,
   `torch-geometric`, `scikit-learn`, …) and `optimize-for-gpu` for
   throughput, and offload actual GPU work with `modal_run`/`runpod_run`
   when the local sandbox can't or shouldn't run it. Log each trial's
   config and result as a `notebook` entry (`method` for the config,
   `observation` for the metric), threaded with `relatesTo` back to the
   pre-registration decision, so the full trial history stays reconstructable
   without re-reading logs.
6. **A surprising result — a config that wins by an implausible margin, a
   metric that moves the wrong way with more capacity, a run that diverges —
   gets investigated before being trusted**, per
   `investigating-anomalous-results`; don't just re-run it and hope.
7. **Verify the winner before claiming it.** Once a candidate configuration
   looks best, rerun it fresh (new seed if that's part of the search space)
   and read the actual output — `verifying-results-before-claiming` — rather
   than reporting the number from the original sweep run. For a result that
   will inform a real decision, dispatch a `requesting-red-team-review`
   subagent whose job is to argue the improvement is noise, a leaked
   validation set, or an unfair baseline comparison, before you believe it.
8. **Report with `scientific_result`**: the full trial table (or a
   representative subset) as `kind: "table"`, or a `kind: "statistical_test"`
   summary if the improvement claim rests on a significance test — not just
   a prose "it got better."

## What was deliberately left out

Karpathy's own Python package (`agent.py`/`tools.py`, Google ADK +
`claude_agent_sdk.query()`, a fixed roster of named "experts") was not
ported: `delegate_task` is a thin wrapper around exactly what this plugin's
`subagent` tool already does, and running a second agent framework alongside
DSH would duplicate delegation rather than add anything. The one thing worth
keeping was the *shape* of the loop, captured above.
