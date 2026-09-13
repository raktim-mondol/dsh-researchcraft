# Hypothesis card

One card per kept candidate. Ranked list in this order. Scores are 1–5; novelty requires a search, not a hunch.

## Schema

```markdown
### H<n>. <short title>

**Claim:** <one falsifiable sentence: variables, population, direction>

**Mechanism:** <how the claim would be true>

**Evidence for:** <cited findings>
**Evidence against:** <cited findings, or "none found in this search">

**Novelty:** <what is already published vs. what is new in this combination>
**Searched:** <tools + queries, or [VERIFY] if a source could not be confirmed>

**Discriminating test:** <experiment or analysis>
**Refuted if:** <the result that kills the claim>
**Feasibility / safety:** <constraints, cost, known toxicities or dual-use flags>

| Alignment | Plausibility | Novelty | Testability | Safety |
|---|---|---|---|---|
| <1–5> | <1–5> | <1–5> | <1–5> | <1–5> |
```

## Example (format only)

### H1. ROCK inhibition restores RPE phagocytosis in dry AMD

**Claim:** Inhibiting ROCK in retinal pigment epithelium increases phagocytosis of photoreceptor outer segments, which would slow debris accumulation in dry age-related macular degeneration.

**Mechanism:** ROCK restrains actin remodeling needed for engulfment; acute inhibition restores phagocytic cup formation and may transcriptionally upregulate lipid-efflux genes such as ABCA1.

**Evidence for:** RPE phagocytic decline in AMD; ROCK inhibitors restore phagocytosis in cultured RPE in prior work.
**Evidence against:** ROCK inhibitors are studied mainly in wet AMD / neovascular disease; in vivo dry-AMD evidence is lacking.

**Novelty:** ROCK inhibition in RPE is known; applying it as a dry-AMD phagocytosis therapy (vs. anti-angiogenic use) is the combinatorial claim.
**Searched:** consensus_search + parallel_search `advanced` for "RPE phagocytosis ROCK" and "dry AMD ROCK inhibitor"; [VERIFY] any trial not retrieved.

**Discriminating test:** Flow-cytometry phagocytosis assay (pHrodo outer segments) in primary or iPSC-RPE ± ROCK inhibitor vs. vehicle.
**Refuted if:** no increase in phagocytic index at non-cytotoxic doses, or the increase is an assay artifact (bead-only, no outer-segment substrate).
**Feasibility / safety:** In-vitro first; approved ocular ROCK inhibitors have known topical safety profiles — still not a clinical recommendation.

| Alignment | Plausibility | Novelty | Testability | Safety |
|---|---|---|---|---|
| 5 | 4 | 3 | 5 | 4 |
