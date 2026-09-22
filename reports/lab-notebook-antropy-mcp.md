# Lab Notebook
**Session:** session-a41f3787-66a2-4c11-bc65-5be647f7552b
**Span:** 2026-09-22T06:22:28.062Z → 2026-09-22T07:19:49.345Z
**Entries:** 14

---

## Method: Ran official upstream evidence for antropy.perm_entropy at pinned rev dfbe688
_+0s · #paper2mcp #antropy #perm_entropy #official-test_

Native driver `notebooks/perm_entropy_official_test/driver.py` executed with `antropy-env/bin/python` (Python 3.12.3) from the project root.

- `import antropy` resolves to `repo/antropy/src/antropy/__init__.py`, version 0.2.2, git HEAD `dfbe688744021eb79c4745ceb02a1efc7cd3fbd8` (verified, repo `git status --short` empty).
- Fixtures rebuilt by importing the repository's own `repo/antropy/tests/utils.py` (adds `tests/` to `sys.path`; that module seeds `np.random.seed(1234567)` at import). 19 `.npy` fixtures persisted with sha256.
- Reference helper `_perm_entropy_orig` imported from the upstream test module `tests/test_entropy.py` (line 26), never re-implemented.
- Official pytest: `pytest tests/test_entropy.py -k "perm_entropy" -q` -> exit 0, 4 passed, 12 deselected.
- Replay in a second process from the saved `.npy` inputs only: 603 floats compared, 0 nonzero differences, 0 exact mismatches.

Artifacts: notebooks/perm_entropy_official_test/{provenance.json,results.json,replay.json,data/,logs/pytest.txt,driver.py,replay.py}

## Observation: Independent verification of antropy.spectral_entropy claimed reference values — all claims reproduce; reduction-order claim CONFIRMED with a mechanisic refinement
_+273s · confidence: high · #antropy #spectral_entropy #verification #floating-point #reduction-order_

Independent recomputation via my own throwaway scripts (/tmp/verify_se.py … /tmp/verify_se5.py), using the repo's own fixture module and `antropy.spectral_entropy` directly. Repo pinned at dfbe688744021eb79c4745ceb02a1efc7cd3fbd8; numpy 2.5.3, scipy 1.18.1, antropy 0.2.2; python 3.12.3.

**Every claimed reference value reproduced.** Highlights with full precision:
- `spectral_entropy(RANDOM_TS,100,'fft')` = `9.946904572430391` / `0x1.3e4d0ad160af4p+3`
- `(RANDOM_TS,100,'welch')` = `6.973029438395976` / `0x1.be461d43fd2e8p+2`
- `(RANDOM_TS,100,'welch',nperseg=400)` = `7.598239157804065` / `0x1.e6498ce47d1f7p+2`
- `round(spectral_entropy(RANDOM_TS,100,normalize=True),1)` = `0.9`, `== 0.9` → True (raw `0.9426819170702315`)
- `PURE_SINE`: raw `6.2342562839119945e-27` (`0x1.ededbd51794ecp-88`), `round(,2)` → `0.0`, `== 0.0` → True. NOT exactly zero.
- 2D test path: `apply_along_axis` and the vectorised call are **bitwise identical**; `assert_equal` PASSES.
- `spectral_entropy(RANDOM_TS,100,method='invalid')` → `ValueError: method must be 'fft' or 'welch', got 'invalid'.`
- Docstring/README (non-CI) values all match: `0.00`, `6.9800`, `0.9956`, `[0.9464,0.9428,0.9431,0.9417]`, `0.9941`. `stochastic` NOT importable (FGN doctests UNVERIFIABLE).
- Official test: `1 passed, 15 deselected`, exit 0; `git status --short` empty.

**Claim under attack** (`data.T`, `axis=0` not bitwise identical to `data`, `axis=-1`; max abs diff ~1.1e-16; cause is reduction order in the final `.sum`; Welch PSD bitwise identical): **AGREE on every element.** Exact max abs diff `1.1102230246251565e-16` (= eps/2, i.e. exactly 1 ulp at magnitude ~1). Only 2 of 4 channels differ (RANDOM_TS +1 ulp, ARANGE −0.375 ulp); NORMAL_TS and PURE_SINE are bitwise identical.

**Mechanistic refinement found.** The PSD is bitwise identical for both layouts *and so is the pre-normalisation `psd.sum(axis=axis)`*, because scipy returns both PSDs with the reduction axis strided by 16 bytes (`(816,16)` vs `(16,816)`). The divergence appears only after `psd / psd.sum(...)`: the ufunc materialises a fresh C-contiguous array, so the final `-_xlogx(psd_norm).sum(axis=axis)` reduces axis -1 with stride **8** in one layout and axis 0 with stride **32** in the other → different pairwise-summation grouping. Forcing the two term-arrays into the identical layout collapses the difference to `0.0` in both directions — conclusive isolation. Over 300 random `(4,3000)` welch draws: reduction 1 diverges 0/300, reduction 2 diverges 294/300. So "purely the final `.sum`" is correct for the fixture and consistent across seeds, but the *other* reduction in the same function is equally layout-exposed in principle and is shielded only by scipy's stride choice.

Fragility worth flagging: `np.testing.assert_equal` is exact (not tolerant). The suite's 2D assertion passes only because `apply_along_axis` and the vectorised call share the `(4,51)` axis=-1 layout; an equivalent exact-equality assertion against the `data.T, axis=0` layout would FAIL. Docstring Examples are not CI-enforced (no `--doctest-modules`; `testpaths=["tests"]`; no doctest step in `.github`).

[/tmp/verify_se.py](/tmp/verify_se.py)
[/tmp/verify_se4.py](/tmp/verify_se4.py)
[/tmp/verify_se5.py](/tmp/verify_se5.py)
[/tmp/pytest_raw.txt](/tmp/pytest_raw.txt)

## Observation: spectral_entropy official-test evidence: all CI gates reproduced; axis=0 differs by exactly 1 ulp
_+513s · confidence: high · #spectral_entropy #antropy #official-test #reference-evidence #float-determinism_

Execution `spectral_entropy_official_test` (native driver, pinned antropy dfbe688 at v0.2.2, repo left clean).

**Official test (real run):** `pytest tests/test_entropy.py -k spectral_entropy -q` → `1 passed, 15 deselected`, exit 0.

**CI-enforced reference values (full precision):**
- `spectral_entropy(RANDOM_TS, 100, 'fft')` = `9.946904572430391` (`0x1.3e4d0ad160af4p+3`)
- `welch` = `6.973029438395976` (`0x1.be461d43fd2e8p+2`)
- `welch, nperseg=400` = `7.598239157804065` (`0x1.e6498ce47d1f7p+2`)
- `round(se(RANDOM_TS,100,normalize=True), 1)` = `0.9` from raw `0.9426819170702315` ✓
- `round(se(PURE_SINE,100), 2)` = `0.0` from raw `6.2342562839119945e-27` — **not exactly zero**, a 2-dp formatting artifact
- Error contract: `method='invalid'` → `ValueError: method must be 'fft' or 'welch', got 'invalid'.`

**2D path:** `apply_along_axis(se, axis=1, arr=data, **params)` is **bitwise identical** to `se(data, **params)` (both `(4,)`, max abs diff `0.0`, `assert_equal` passes).

**Changed-input axis probe:** `se(data.T, axis=0)` returns shape `(4,)` but is **NOT** bitwise equal to the `axis=-1` result — max abs difference exactly `1.1102230246251565e-16` (eps/2 = 1 ulp), affecting only 2 of 4 channels.
Stage-by-stage isolation: Welch PSD, frequency axis, normalisation sums, normalised PSD and per-element `_xlogx` terms are all **bitwise identical**; only the final `_xlogx(psd_norm).sum(axis=axis)` differs. Controlled test: same values in two memory layouts → sums differ (`8.88e-16`); forced into an identical layout → `0.0`. Over 300 fresh random draws the normalisation sum diverged 0/300 while the final sum diverged 294/300. Cause is NumPy's memory-layout-dependent pairwise-summation grouping — **not** an algorithmic difference, and scoped to this input (the earlier `psd.sum(axis=axis)` is equally layout-exposed in principle).

**Documented-only (not CI gates — corroborated: no `--doctest-modules`, no doctest step in `.github`):** `0.00`→`1.058e-28`; `6.9800`→`6.9800456623713885`; `0.9956`→`0.995552619831607`; array→exact `array_equal` True; README `0.9941`→`0.9940882825422431`. The three FractionalGaussianNoise examples are **unverifiable here**: `stochastic` is not installed (module deliberately not installed), `ModuleNotFoundError` captured.

**Replay:** second process read only the saved `.npy` inputs (never importing `utils`); 38 comparisons, max float abs difference `0.0`, 0 exact mismatches, input file+buffer hashes identical. `results.json` and `provenance.json` are byte-stable across a fresh full re-run; only timestamps/durations vary.

**Limitation worth passing downstream:** the suite's 2D exact-equality assertion is layout-fragile — `numpy.testing.assert_equal` is exact, so the same check against the `data.T, axis=0` layout would fail. A numpy/scipy change to reduction grouping or scipy PSD strides could break this test with no semantic change.

Independently verified by a separate subagent (all checkable values confirmed, no mismatch); one mechanism detail it offered (reduction "stride 8 vs 32") did not describe the actual operands and was replaced by the verified layout-grouping statement. Report: `reports/executed_notebook_spectral_entropy_official_test.json`.

[notebooks/spectral_entropy_official_test/driver.py](notebooks/spectral_entropy_official_test/driver.py)
[notebooks/spectral_entropy_official_test/results.json](notebooks/spectral_entropy_official_test/results.json)
[notebooks/spectral_entropy_official_test/replay.json](notebooks/spectral_entropy_official_test/replay.json)
[notebooks/spectral_entropy_official_test/provenance.json](notebooks/spectral_entropy_official_test/provenance.json)
[notebooks/spectral_entropy_official_test/logs/pytest.txt](notebooks/spectral_entropy_official_test/logs/pytest.txt)
[reports/executed_notebook_spectral_entropy_official_test.json](reports/executed_notebook_spectral_entropy_official_test.json)

## Method: entropy module: independently re-derived all expectations from direct upstream calls
_+2047s · #verification #entropy #paper2mcp_

Built my own fixture set (tests/data/entropy/, 16 fixtures rebuilt from repo/antropy/tests/utils.py plus verifier-authored arrays) and my own driver (tests/results/entropy/derive_expected.py) that calls the pinned `antropy.perm_entropy` / `spectral_entropy` / `sample_entropy` **directly** — never the generated wrapper — to produce 87 expectation records in upstream_expected.json.

All 7 CI-inherited reference values reproduce: bandt order=2 -> 0.9182958340544896 (3dp 0.918), order=3 -> 1.5219280948873621 (3dp 1.522), perm(RANDOM_TS,order=3,normalize) -> 0.9995858289645746, spectral(RANDOM_TS,100,normalize) -> 0.9426819170702315, spectral(PURE_SINE,100) -> 6.2342562839119945e-27, sampen(RANDOM_TS,order=2) -> 2.192416747827227, sampen(RANDOM_TS,order=3,euclidean) -> 2.724354910127154. All bit-identical.

Tolerance: exact (ATOL = 0.0) — deterministic NumPy/SciPy/sklearn reductions in a pinned env, wrapper applies no scientific transform.

[tests/results/entropy/derive_expected.py](tests/results/entropy/derive_expected.py)
[tests/results/entropy/upstream_expected.json](tests/results/entropy/upstream_expected.json)
[tests/data/entropy/make_fixtures.py](tests/data/entropy/make_fixtures.py)

## Observation: 20/20 wrapper-vs-upstream exact agreements through real FastMCP transport; 98/98 tests pass
_+2047s · #verification #entropy #mcp-transport_

Exercised all three decorated tools via `async with Client(entropy_mcp) as client` (fastmcp 4.0.3). All 20 positive probe calls matched the direct-upstream expectation exactly, including changed-input grids (order x delay x normalize; method x nperseg x normalize; order x tolerance x metric), 2-D/3-D paths, the KDTree threshold, and the non-finite edge semantics (-0.0 sign bit preserved, "nan"/"inf" as exact JSON strings).

pytest: 98 passed, 0 failed, exit status 0 (perm 41, sample 27, spectral 30). Log at tests/logs/entropy/pytest.txt.

Acceptance dry-run (tests/results/entropy/validate_acceptance.py) exits 0 over 36 cases: 22 positive (all three tools covered, 22 unique artifacts, every artifact inside artifact_root), 14 error_contains.

[tests/logs/entropy/pytest.txt](tests/logs/entropy/pytest.txt)
[tests/results/entropy/wrapper_probe.json](tests/results/entropy/wrapper_probe.json)
[reports/mcp-acceptance-entropy.json](reports/mcp-acceptance-entropy.json)

## Observation: Schema-vs-upstream deviation: tolerance="0.1" coerced, not rejected; handoff claim #7 wrong
_+2054s · #verification #entropy #deviation_

DEVATION (measured on identical literals, both sides): `tolerance` is typed `float | None`, so pydantic COERCES the string "0.1" to 0.1 and the tool returns 1.652946133848861 — exactly upstream's value for the *number* 0.1 — whereas upstream called with the string raises TypeError("tolerance must be a float or int, got str."). `tolerance="bad"` is refused at the schema boundary (float_parsing) where upstream raises TypeError. `method="Welch"` is refused by the Literal (literal_error) where upstream raises ValueError. The same lax-mode coercion also accepts order="3", delay="2", sf="100", axis="-1", nperseg="50".

Verdict: documented deviation, NOT a fidelity failure — every coerced case computes the correct upstream value for the coerced number, and the coercion is inherent to a typed JSON-Schema MCP transport (the format rules mandate Literal and typed params). Widening the types would remove the schema's refusal of values like tolerance="bad" without removing the coercion. `metric` was correctly left an open str, so upstream's exact ValueError text surfaces verbatim.

Also found: reports/implementation-entropy.json adaptation #7 is factually wrong — upstream's np.mean over per-epoch 4-element arrays flattens to a SCALAR (2.5824708766536855), not an array. The wrapper's behaviour is nonetheless correct; no code change needed.

[tests/results/entropy/wrapper_probe.json](tests/results/entropy/wrapper_probe.json)
[reports/verification-entropy.json](reports/verification-entropy.json)

## Decision: Verdict: all three entropy tools verified, no production repair, hashes match handoff
_+2054s · #verification #entropy #verdict_

Verdict: all three tools VERIFIED, zero production repairs (0 of 6 allowed attempts used per tool). src/tools/entropy.py sha256 568fb44a4d56c29c43e89e917daec23c0a4407e1294eb2b0ec8ee693f5610844 and src/tools/__init__.py sha256 04928751607d756001980df4164d8bc6985c5818ede776982f7e6599e8af3ffd are byte-identical to the implementer's handoff claims — verified before and after all testing.

Source reuse: each tool body traces to the pinned upstream symbol with no reimplemented algorithm (grep for np.std/log2/argsort/periodogram/welch/KDTree/query_radius/_xlogx finds only annotation text and the literal string label "0.2 * np.std(x, ddof=0)" at entropy.py:197). sample_entropy's only added restriction is the 1-D guard. repo/antropy clean at dfbe688744021eb79c4745ceb02a1efc7cd3fbd8.

Upstream quirk preserved faithfully: sample_entropy(order=1) succeeds on the numba path but raises ValueError("Order has to be at least 2.", from antropy/utils.py:38) on the KDTree path. Neither the wrapper nor my tests paper over it.

My own test file bugs (4 initial failures) were corrected without relaxing any assertion; the order=1 case now asserts both sides fail with the same upstream text.

[src/tools/entropy.py](src/tools/entropy.py)
[src/tools/__init__.py](src/tools/__init__.py)
[reports/verification-entropy.json](reports/verification-entropy.json)

## Observation: Independent delivery validation of antropy-mcp.zip: PASS (success=true)
_+2674s · confidence: high · #delivery-validation #paper2mcp #mcp #antropy #relocation_

Fresh extraction of `dist/antropy-mcp.zip` (sha256 `f0340924…c7a99`, matches binding) into a NEW space-containing path `/tmp/antropy-delivery-check/antropy mcp package`, then exercised end-to-end.

**Archive**: `unzip -t` clean. Archive's own entry list = `reports/zip-inventory.json` exactly: 13 files, no extra, no missing; all 13 sha256 matched after extraction (confirmed twice — in the space path and in a pristine second extraction). No dev evidence (no tests/notebooks/reports/dist/.git/caches/venvs), no secrets. 0 hits for `dsh-researchcraft`, `/home/raktim`, `/home/`, `raktim`, `/tmp/`. `requirements.txt` pins 6 dists by version and installs antropy from the relative `./vendor/antropy` — no absolute path.

**Install (from extracted package only)**: `uv venv` → 0; `uv pip install -r requirements.txt` → 0 (77 pkgs); `uv pip install ./vendor/antropy` → 0 (antropy 0.2.2); `uv pip check` → "All installed packages are compatible". `antropy.__file__` resolves to the extracted `.venv/lib/python3.12/site-packages/antropy/__init__.py`, NOT `$PROJECT_ROOT/repo/antropy` (the project venv has an editable `.pth` into repo/, absent from the extracted run's sys.path).

**Relocated acceptance**: helper exit 0, `success=true`, 36/36 cases, `missing=[]`, `unexpected=[]`, `require_all_tools=true`; every one of the 3 tools has positive cases (8/6/8) plus error cases (7/3/4). Recorded python = extracted venv.

**Independent real MCP calls**: 16/16 own checks pass. Changed inputs (order=4/delay=2/normalize=True; welch/nperseg=50; sample order=2/tol=0.1 on the LONG series) matched direct vendored-antropy calls to **abs diff 0.000e+00**. 2-D: 20 values on epochs_20x500, 4 on epochs_4x3000. Non-finite: `"nan"`/`"inf"` as strings; all 18 written `result.json` parse as strict JSON (hook proven non-vacuous by positive control). Unsupported-extension and missing-required-arg both surface as real MCP tool errors. Repeated identical calls → two distinct fresh output dirs and two distinct `result.json` paths.

**Notable**: 4 files are archived mode 0600 and no file has an exec bit — but the server is launched as `python <server>.py`, needing only read, so no permission restoration is required. Caveat recorded: both venvs symlink to `/usr/bin/python3.12`, so environment identity was established via `sys.prefix`/site-packages, not `realpath(sys.executable)`.

Report: `reports/delivery-validation.json`.

[reports/delivery-validation.json](reports/delivery-validation.json)
[reports/mcp-delivery-relocated.json](reports/mcp-delivery-relocated.json)
[reports/mcp-acceptance-cases-relocated.json](reports/mcp-acceptance-cases-relocated.json)
[tests/logs/delivery/independent_calls.json](tests/logs/delivery/independent_calls.json)
[tests/logs/delivery/provenance_check.json](tests/logs/delivery/provenance_check.json)
[tests/logs/delivery/install.log](tests/logs/delivery/install.log)
[tests/logs/delivery/relocated_acceptance.log](tests/logs/delivery/relocated_acceptance.log)

## Decision: Routing: red-team review on subagent_pro for the delivery verdict (NOT FALSIFIED, 1 new defect)
_+3055s · #routing #red-team #delivery-validation_
_↳ supports "Independent delivery validation of antropy-mcp.zip: PASS (success=true)" (call_00_ax2hj99jTEHUTykmFqTg6503)_

**Task**: adversarially re-verify the `antropy-mcp` delivery verdict — 9 named attacks (vacuous strict-JSON hook, wrong interpreter, silent workspace import, relaxed acceptance cases, inventory truth, relocation reality, repeat-call freshness, the 36/36 claim, and reading the sources for real defects), plus a fresh end-to-end relocation from the ZIP.

**Why pro**: this is a "prove or disprove" mandate where the failure mode is a *subtly* convincing false pass. Catching it requires holding the whole chain consistent — the interpreter's provenance, the case-file diff, the helper's assertion semantics, and the on-disk artifact state at once — rather than checking each item in isolation. That is difficulty, not length.

**Outcome**: NOT FALSIFIED. 0 of 9 attacks falsified the claim. It independently corroborated every load-bearing point, and *strengthened* two checks: it widened the strict-JSON sweep from my 18 `result.json` files to all 62 (still 0 bare `NaN`/`Infinity`), and it ran its own fresh relocation under CPython 3.13 (passed, so the 3.12 pin is not a hard blocker).

**It found one thing I missed**: `src/antropy_mcp.py:9` uses an implicit script-directory import (`from tools.entropy import entropy_mcp`). Works in the documented launch mode and is cwd-independent, but `import antropy_mcp` / `python -m antropy_mcp` raises `ModuleNotFoundError: No module named 'tools'`. Latent fragility, not a self-containment break. Added to the report as defect `implicit-script-dir-import`.

**It also raised a fair caveat I had not stated**: vendored antropy is byte-identical to the project's `repo/antropy/src`, so matching numbers alone cannot show which copy ran — only the provenance evidence (`antropy.__file__`, `direct_url.json`, empty workspace `sys.path`) carries that claim. Added to `limitations`.

Net: escalation was warranted. It produced one real new defect and one real new caveat, and improved two checks, without disturbing the verdict.

## Observation: Antropy MCP delivery re-verified after 0644 mode rebuild: success
_+3396s · confidence: high · #paper2mcp #delivery-verification #antropy #mcp #verification_

Independent delivery verification of `dist/antropy-mcp.zip` (SHA-256 `f45a8278…6e971`, superseding the 0600-mode archive `f0340924…c7a99`), extracted fresh to `/tmp/antropy-delivery-final/antropy mcp package` (path contains a space) and exercised only from the extracted package.

- Archive: hash matches binding, not the superseded archive; `unzip -t` clean; all 13 file hashes match `reports/zip-inventory.json`; contents identical to the superseded run's recorded per-file hashes (superseded ZIP bytes are gone from disk, so identity rests on that record + the 0644 staging tree at `tmp/staging`, both of which agree).
- Modes: all 13 entries report `0o644` via `ZipInfo.external_attr` and `zipinfo -l`; post-extraction all 13 readable. The ZIP stores **no directory entries**, so the "directories 0755" half of the rebuild note is not embodied in the archive — this host's umask 002 produced 0775 (harmless, recorded as informational).
- Fresh install from the extracted package only: `uv venv` / `uv pip install -r requirements.txt` / `uv pip install ./vendor/antropy` / `uv pip check` all exit 0; `antropy.__file__` resolves inside the extracted venv, `direct_url.json` → `./vendor/antropy`, no project path on `sys.path`.
- Relocated acceptance (strict helper, extracted python + server, cwd = package): exit 0, **36/36 passed** (22 positive, 14 expected-error), `missing`/`unexpected` empty.
- Independent `fastmcp.Client` driver: 14/14 checks, every numeric expectation derived by calling the vendored antropy directly (all absolute diffs 0.0, tolerance 0.0) — changed inputs, 2-D lengths 20 and 4, `"nan"`/`"inf"` contract with a non-vacuous strict-JSON `parse_constant` hook, an expected tool error, and two identical calls yielding distinct fresh output dirs.
- Findings: `archived-mode-0600` **RESOLVED**; `implicit-script-dir-import` (`src/antropy_mcp.py:9`) **still present**, retested — works as a script (cwd-independent), fails under `python -m src.antropy_mcp` from the package root and under module import from another cwd with `ModuleNotFoundError: No module named 'tools'`. Latent, non-blocking, not fixed.
- Verdict `success: true` at `reports/delivery-validation.json` (31 keys, all required present).

[reports/delivery-validation.json](reports/delivery-validation.json)
[reports/mcp-delivery-relocated.json](reports/mcp-delivery-relocated.json)
[reports/mcp-acceptance-cases-relocated.json](reports/mcp-acceptance-cases-relocated.json)
[tests/logs/delivery-final/independent_mcp_driver.py](tests/logs/delivery-final/independent_mcp_driver.py)
[tests/logs/delivery-final/check1-inventory-modes.json](tests/logs/delivery-final/check1-inventory-modes.json)
[tests/logs/delivery-final/independent-mcp-calls.json](tests/logs/delivery-final/independent-mcp-calls.json)
[tests/logs/delivery-final/pristine-hygiene.txt](tests/logs/delivery-final/pristine-hygiene.txt)

## Method: Paper2MCP conversion of antropy pinned at dfbe688 (3 entropy tools)
_+3441s · #paper2mcp #antropy #mcp_

Converted the pinned antropy checkout (v0.2.2, commit `dfbe688744021eb79c4745ceb02a1efc7cd3fbd8`) into a tested FastMCP server exposing exactly the three filtered operations, CPU only.

Route: `python`. Project: `.e2e/ui-e2e/antropy-agent`. Scope filter: `perm_entropy`, `sample_entropy`, `spectral_entropy` only.

Stages, each gated with `verify_workflow.py`:
1. environment + scanner (2 concurrent subagents) -> `setup` gate
2. 3 executors, one per filtered function's official test -> `execution` gate
3. 1 implementer for the single owning module `entropy` -> `extraction` gate
4. 1 fresh verifier (distinct agent id) -> `verification` gate
5. coordinator: `src/antropy_mcp.py` mounts `entropy_mcp` with `namespace=None`
6. requirements + fresh-env acceptance
7. USAGE.md + ZIP + fresh independent delivery verifier -> `complete` gate

Host agent ids were recovered from the DSH session store (`~/.dsh/sessions/--home-raktim-dsh-researchcraft--/<id>/session.v3.jsonl.zstd`) because foreground delegations did not return an id; recorded in `reports/agent-runs.json` with a provenance note.

[reports/agent-runs.json](reports/agent-runs.json)
[.pipeline/language.json](.pipeline/language.json)
[reports/tutorial-scanner.json](reports/tutorial-scanner.json)

## Observation: Reference values and upstream edge semantics established from direct execution
_+3441s · #antropy #reference-values #edge-cases_

Executors ran the official tests plus native drivers, calling pinned `antropy` directly. `pytest tests/test_entropy.py -k "perm_entropy or spectral_entropy or sample_entropy"` -> 6 passed. Pinned reference values (full precision):

- `perm_entropy([4,7,9,10,6,11,3], order=2)` = 0.9182958340544896; order=3 = 1.5219280948873621 (Bandt & Pompe)
- `perm_entropy(RANDOM_TS, order=3, normalize=True)` = 0.9995858289645746
- `spectral_entropy(RANDOM_TS, 100, normalize=True)` = 0.9426819170702315; `spectral_entropy(PURE_SINE, 100)` = 6.2342562839119945e-27 (rounds to 0.0)
- `sample_entropy(RANDOM_TS, order=2)` = 2.192416747827227; order=3 euclidean = 2.724354910127154

Upstream semantics that a wrapper must not "fix": `perm_entropy` returns `-0.0` for a constant signal; `sample_entropy` legitimately returns `inf` (m matches, no m+1) and `nan` (no m match), including silently on short inputs; `spectral_entropy` axis layouts can differ by ~1 ulp from NumPy pairwise-summation grouping.

Two documented examples are unreproducible here: the FractionalGaussianNoise doctests need `stochastic`, which is not a dependency. Also the README's `perm_entropy(X, normalize=True, axis=-1)` is invalid at this revision (TypeError) - no axis parameter exists.

Numba compiles `_numba_sampen` eagerly at `import antropy.entropy` (~5-6 s per fresh process), so MCP server startup carries that cost; tool calls themselves are fast.

[reports/executed_notebook_perm_entropy_official_test.json](reports/executed_notebook_perm_entropy_official_test.json)
[reports/executed_notebook_spectral_entropy_official_test.json](reports/executed_notebook_spectral_entropy_official_test.json)
[reports/executed_notebook_sample_entropy_official_test.json](reports/executed_notebook_sample_entropy_official_test.json)
[reports/executed_notebooks.json](reports/executed_notebooks.json)

## Observation: Independent verification: 98 tests pass, zero production repairs, 0.0 tolerance agreement
_+3441s · #verification #acceptance #transport-typing_

The fresh verifier (distinct agent id from the implementer) re-derived every expectation from direct upstream calls and drove all three tools through the real FastMCP client: 98 tests passed, 0 failed (perm 41 / sample 27 / spectral 30); 20/20 wrapper-vs-upstream probes matched exactly (tolerance 0.0). It made no production code changes, so the module is byte-identical to the implementer revision.

Its one substantive finding: the MCP input schema refuses an out-of-range `method` and a non-numeric `tolerance` before upstream sees them, and coerces `tolerance="0.1"` to the number 0.1 (which upstream would reject with TypeError). Every coerced case computes the correct upstream value; documented as a transport-typing deviation, not a fidelity failure. `metric` was correctly left an open string so upstream's ValueError surfaces verbatim.

Runtime acceptance: 36/36 cases in the project env and 36/36 in a freshly created env; 8/8 clean-env scientific checks matched the saved upstream values exactly, including the `inf`/`nan` contract.

[reports/verification-entropy.json](reports/verification-entropy.json)
[reports/mcp-acceptance-entropy.json](reports/mcp-acceptance-entropy.json)
[reports/mcp-project-environment.json](reports/mcp-project-environment.json)
[reports/mcp-clean-environment.json](reports/mcp-clean-environment.json)

## Decision: Rebuilt the ZIP to normalize 0600 file modes, then re-verified with a fresh delivery verifier
_+3441s · #routing #delivery #zip-integrity_

The first delivery verification passed but disclosed that four archived files stored mode `0600`. Since a recipient extracting the archive under a different UID could fail to read them, I rebuilt the archive from byte-identical contents with all files at `0644` (per-file content hashes provably unchanged; only `dist/antropy-mcp.zip` changed, `f0340924...` -> `f45a8278...`).

Because any package change invalidates its delivery result, I archived the superseded evidence to `reports/archive/` and ran a second, fresh independent delivery verifier against the new archive. It extracted to a path containing a space, installed from `requirements.txt` + `./vendor/antropy` only, re-ran the strict acceptance (36/36, 22 positive + 14 expected-error, no missing/unexpected) and 14/14 independent calls with expectations derived from the extracted vendored antropy (absolute difference 0.0). Modes confirmed 0644 on all 13 entries; only difference from the superseded archive is stored permissions.

It also retested the remaining disclosed defect: `src/antropy_mcp.py` uses an implicit script-directory import, so the documented launch (`python src/antropy_mcp.py`) works from any cwd but `python -m src.antropy_mcp` does not. Left unfixed (non-blocking, documented) rather than mutating a verified production file for a launch mode that is not the documented one.

[dist/antropy-mcp.zip](dist/antropy-mcp.zip)
[reports/delivery-validation.json](reports/delivery-validation.json)
[reports/zip-inventory.json](reports/zip-inventory.json)
