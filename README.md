# dsh-researchcraft

ResearchCraft as a **DeepSeek Harness** profile: the DSH web UI and DSH agent, with ResearchCraft’s scientific skills, living lab notebook, and specialist subagents.

## Install

```sh
dsh plugin --profile researchcraft add github:raktim-mondol/dsh-researchcraft
```

This creates the `researchcraft` DSH profile (if it doesn't exist yet) and adds the plugin to it.

To update to the latest version:

```sh
dsh plugin --profile researchcraft update dsh-researchcraft
```

To install from a local checkout instead (for plugin development):

```sh
dsh plugin --profile researchcraft add /path/to/dsh-plugin
```

The profile must also list `@deepseek-ai/dsh-web-app` before this bundle.

## Run

```sh
dsh --profile researchcraft
```

Opens the Harness web UI (typically `http://127.0.0.1:3080`).

**Select the ResearchCraft agent preset for each chat.** Installing this plugin adds a *ResearchCraft* option to the agent-preset picker — it does not replace whatever your default preset already is (commonly "Standard mode" / "PTC mode"). A new chat starts on that default, not on ResearchCraft, until you pick it explicitly:

1. Start a new session.
2. Click the preset selector at the top of the message box (reads "PTC mode", "Standard mode", or similar by default).
3. Choose **ResearchCraft** from the list.

The persona, the longer research system prompt (notebook discipline, specialist roster, connector guidance, …), and academic search (`mcp__parallel__*`, `mcp__firecrawl__*`, `mcp__scite__*`, `consensus_search`) are only present on this preset — a session left on the default one won't have them, and asking it to use e.g. the Parallel connector will fail with `tools[name] is not a function`. The general-purpose tools below (notebook, image_generate, sci_inspect, latex_compile, pdf_to_markdown, modal_run/runpod_run, workflow) are available on every preset regardless, since they're registered at the plugin/bundle level rather than inside the ResearchCraft preset.

The preset picker remembers your last choice per browser, so you'll typically only need to do this once.

## What it adds

- **ResearchCraft agent preset** — persona, research system prompt (notebook discipline, specialist roster, connector guidance), standard coding tools, and the 4 academic MCP connectors below. Select it explicitly per chat — see [Run](#run).
- Scientific skills catalogue (`scientific-agent-skills`, or `RESEARCHCRAFT_SKILLS_DIR`) — available on every preset
- `notebook` tool — log, read, and export a living lab notebook (JSONL under `<cwd>/.dsh/notebook/`), shared across a subagent delegation tree, with a zip-bundle export alongside the plain Markdown one — every preset
- `scientific_result` tool — a structured, schema-validated "final finding" card (table or statistical-test), distinct from the notebook's running log — every preset
- Specialist briefs (code-reviewer, literature-researcher, …) for the DSH `subagent` tool, plus `subagent_pro` and `subagent_vision` — two more delegation tools pinned to a different model for unusually heavy reasoning and image-reading tasks respectively — see [Subagent model routing](#subagent-model-routing) — every preset
- `image_generate` tool for conceptual scientific figures (Gemini "nano banana" by default) — every preset
- `sci_inspect` tool for scientific file formats (chemistry, structure, mass spec, arrays, imaging, AnnData) — every preset
- `latex_compile` tool (`.tex` → PDF, bibtex/biber-aware) — every preset
- `pdf_to_markdown` tool (PDF → Markdown, via [pdf-inspector](https://github.com/firecrawl/pdf-inspector)) for literature-survey conversion of downloaded papers — every preset
- `modal_run` / `runpod_run` tools for remote GPU/CPU compute offload — every preset
- `workflow` tool over a ~330-template research-task catalogue — every preset
- Academic search: Parallel, Firecrawl, Scite (MCP connectors) and `consensus_search` (native REST tool) — **ResearchCraft preset only**
- A **Settings → ResearchCraft API keys** page for all of the above — no shell env vars required

## API keys

Every credential below (`PARALLEL_API_KEY`, `FIRECRAWL_API_KEY`, `CONSENSUS_API_KEY`, `SCITE_API_KEY`, `GEMINI_API_KEY`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `RUNPOD_API_KEY`) can be set two ways:

- **Settings → ResearchCraft API keys** in the DSH web UI — type a key, Save. Persisted in the profile's `settings.yaml`; a blank field always means "keep the current value", Clear removes it.
- **Shell environment variable** — takes priority over Settings when both are set.

The same Settings page also has an **Image model** dropdown for `IMAGE_MODEL` — not a credential, so it isn't password-masked and applies immediately on selection rather than needing Save (see [Image generation](#image-generation)). It also has two more model-id dropdowns, **Complex-task model** (`SUBAGENT_MODEL_COMPLEX`) and **Image-reading model** (`SUBAGENT_MODEL_VISION`) — not credentials either, but these two behave like the MCP connectors below, not like Image model: they need a restart to apply (see [Subagent model routing](#subagent-model-routing)).

Tools that call `resolveEnv()` per invocation (`image_generate`, `modal_run`, `runpod_run`, `consensus_search`) pick up a Settings change on the very next call, no restart needed.

The three MCP connectors and the two subagent-model fields are different: the `researchcraft` agent preset mounts once as a standing composition shared by every chat session for the life of the running `dsh` process, so a change only reaches them after you **stop and restart `dsh` itself** — a new chat session on the same running process is not enough. `consensus_search` isn't an MCP connector — see below — so it doesn't have this restart requirement.

**Also make sure the chat session is actually on the ResearchCraft preset.** Both the MCP connectors and `consensus_search` are wired into the `researchcraft` agent preset only; a session left on the default preset (Standard/PTC/etc.) has none of them, and calling one fails with `tools[name] is not a function`. Check the preset selector next to the session title (top of the message box for a new chat, top-left of an existing one) reads "ResearchCraft" before asking the agent to search.

## Academic search

Three literature/web MCP servers are wired into the `researchcraft` preset and surface as `mcp__parallel__*`, `mcp__firecrawl__*`, `mcp__scite__*` tools:

| Connector | Key | Without it |
|---|---|---|
| [Parallel](https://parallel.ai) — general + deep web search | `PARALLEL_API_KEY` (optional) | Works keyless, rate-limited |
| [Firecrawl](https://firecrawl.dev) — scrape/crawl/extract | `FIRECRAWL_API_KEY` (optional) | Works keyless, rate-limited |
| [Scite](https://scite.ai) — Smart Citations, retraction/correction checks, evidence datasets (patents, clinical trials, grants, drug safety, …) | `SCITE_API_KEY` (required) | Connector stays disabled |

[Consensus](https://consensus.app) is a native `consensus_search` tool (not an MCP connector) over its `GET /v1/search` REST API — plain `x-api-key` auth, no OAuth. Requires `CONSENSUS_API_KEY` (required — the tool returns a clear error, not a disabled connector, when unset). Supports the API's full filter set: study type, year/month range, sample size, journal quartile (SJR), citation count, study duration, domain, country, publisher, open-access/preprint/human/controlled/clinical-guideline flags, and pagination.

Set any of these via Settings → ResearchCraft API keys or the matching env var (see [API keys](#api-keys)). `SCITE_API_KEY` is an `mcp`-scoped key from [scite.ai/users/me/api](https://scite.ai/users/me/api) — Scite's own documented non-interactive path for MCP clients, sent as a bearer token to `https://api.scite.ai/mcp` (no OAuth or token exchange). Scite also offers an OAuth flow, but only for its first-party ChatGPT/Claude plugin and other interactive clients — not relevant here.

## Subagent model routing

Besides the plain `subagent`/`subagent_fork` delegation tools, the `researchcraft` preset adds two more that pin a delegated child to a specific model via `agentOptions.model`, so the agent can route a task to the model that fits it instead of running everything on whatever model the current chat session happens to be on:

| Tool | Use it for | Model (Settings or env) | Default |
|---|---|---|---|
| `subagent` | Ordinary delegated work — most specialist calls | — (inherits the parent session's model) | — |
| `subagent_pro` | Tasks where difficulty, not length, is the bottleneck: a hard proof/derivation, a causal-inference or experimental-design critique, tracing a subtle methodological flaw, multi-step reaction/pathway reasoning, a large multi-file refactor | `SUBAGENT_MODEL_COMPLEX` | `deepseek-v4-pro` |
| `subagent_vision` | Delegated tasks that need to *see* something with `read_image` — a figure, scan, diagram, screenshot, or a rendered LaTeX PDF page | `SUBAGENT_MODEL_VISION` | `deepseek-v4-flash-vision-exp` |

`subagent` is deliberately left without a pinned model: forcing every routine delegation onto a hardcoded model id would break delegation outright wherever that id isn't registered under the session's provider. Only the two escalation paths are pinned, and only where the agent is choosing to opt into a specific model rather than falling back to whatever it's already using.

The system prompt steers `subagent_pro` toward difficulty, not length: verifying a mathematical derivation step-by-step or propagating uncertainty through a multi-stage calculation, a causal-inference critique (spotting a hidden confounder, weighing conflicting evidence across several studies), tracing a subtle methodological flaw through many interacting parts (data leakage in a multi-stage ML pipeline, a silently-wrong nested cross-validation setup), multi-step reaction-mechanism or pathway reasoning, and large multi-file refactors that need many call sites kept consistent. It explicitly steers away from routine review, lookup, simple data validation, or literature search, since those get the same quality on plain `subagent` for a fraction of the cost and latency.

`subagent_vision` only routes the child to a model; the child still calls `read_image` (`@deepseek-ai/dsh-tool-fs`) itself, which refuses to read an image unless the calling route's resolved model actually declares `image` input in this deployment's model catalog — pick a `SUBAGENT_MODEL_VISION` value that's registered that way.

Beyond a plain "look at this image" request, the system prompt steers the agent to delegate to `subagent_vision` for scientific reading tasks specifically: interpreting a plot or trend, comparing panels in a multi-panel figure, reviewing a microscopy/gel/medical-imaging scan for qualitative features, checking a chemical structure/phylogenetic tree/pathway diagram for correctness, and comparing a generated figure against what was asked for. It also covers a case text tools can't: auditing a compiled LaTeX PDF's page layout — a table split across a page break, a table or figure that drifted into the references section, an overfull line, a caption stranded from its figure — since `read_image` only accepts PNG/JPEG/WebP/GIF, the agent renders the PDF pages first with `pdftoppm -png -r 150 file.pdf page` (poppler, usually already present alongside TeX Live) before delegating.

Set `SUBAGENT_MODEL_COMPLEX`/`SUBAGENT_MODEL_VISION` via Settings → ResearchCraft API keys (two more dropdowns beside Image model) or the matching env var — env wins when both are set, same resolution order as the API keys above. Unlike Image model, these two need a `dsh` restart to take effect (see [API keys](#api-keys)).

## Image generation

`image_generate` writes conceptual schematics, diagrams, and illustrations to the workspace — not quantitative plots (those should be real Python/matplotlib output over real data).

- **Default (Gemini):** set `GEMINI_API_KEY` (Settings or env). Model defaults to `gemini-2.5-flash-image` ("nano banana"); pick a different one from the **Image model** dropdown in Settings → ResearchCraft API keys (`gemini-3.1-flash-image` "nano banana 2", `gemini-3-pro-image` "nano banana pro", or a custom model id), or set `IMAGE_MODEL` (env). Unlike the API-key fields, the dropdown applies immediately on selection — no Save button, and (like `resolveEnv()` fields) no restart needed.
- **OpenAI-compatible Images API instead:** set `IMAGE_PROVIDER=openai`, `IMAGE_MODEL` (Settings or env), `IMAGE_BASE_URL` (env only) plus `IMAGE_API_KEY` (Settings or env).

## Scientific file inspection

`sci_inspect` summarizes SMILES/MOL/SDF, PDB/CIF, mzML and other mass-spec formats, npy/npz/parquet/hdf5, TIFF/NIfTI/DICOM, and h5ad files by shelling out to the bundled Python helpers under `python-helpers/`.

Set up the helper venv once (needs [uv](https://docs.astral.sh/uv/)):

```sh
cd python-helpers && uv sync
```

The tool finds `python-helpers/.venv` automatically. Override with `RESEARCHCRAFT_HELPERS_DIR` (a different helpers checkout) or `RESEARCHCRAFT_PYTHON` (a specific interpreter).

## LaTeX

`latex_compile` compiles a `.tex` file to PDF: `latexmk` when it's on `PATH` (handles bibtex/biber automatically), otherwise a `pdflatex`/`xelatex`/`lualatex` fallback with a bibtex/biber pass when the source needs one. Requires a TeX Live (or similar) install.

## PDF to Markdown

`pdf_to_markdown` converts a PDF to Markdown using [pdf-inspector](https://github.com/firecrawl/pdf-inspector) (`@firecrawl/pdf-inspector`, native Rust/napi) — built for literature-survey workflows where a lot of downloaded papers need converting. It classifies the PDF (text-based/scanned/image-based/mixed) and, for text-based PDFs, extracts headings, lists, tables, and reading order locally in milliseconds without OCR.

- `path` — the PDF to convert.
- `pages` — optional 1-indexed page numbers to limit conversion to.
- `write_to` — workspace-relative output path for the Markdown. Recommended for anything but a short excerpt; converting many papers with `write_to` set keeps each paper's full text out of the conversation and on disk instead (e.g. `literature/<author>-<year>.md`).
- `ocr` — selectively OCR pages flagged as low quality (mode `Auto`). Requires the PDFium and ONNX Runtime shared libraries installed locally (set `PDFIUM_LIB_PATH`/`ORT_DYLIB_PATH` if they're not on the library search path — see [pdf-inspector's OCR runtime guide](https://github.com/firecrawl/pdf-inspector/blob/main/docs/ocr-runtime.md)); without them, a scanned PDF still comes back with `pages_needing_ocr` populated, so the agent knows to fall back to `subagent_vision` on rendered page images instead.

Prebuilt native binaries ship as `optionalDependencies` for Linux (x64/ARM64, glibc and musl), macOS (ARM64), and Windows (x64) — a plain `npm install` picks up the right one, no Rust toolchain needed.

## Remote compute

`modal_run` and `runpod_run` offload a command to a remote CPU/GPU instance — upload inputs, run, download outputs, always terminate when done.

| Tool | Key (Settings or env) | Get credentials |
|---|---|---|
| `modal_run` | `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | https://modal.com/settings |
| `runpod_run` | `RUNPOD_API_KEY` | https://console.runpod.io/user/settings |

`runpod_run` also needs `ssh`, `scp`, and `ssh-keygen` on `PATH` (standard OpenSSH client tools) to provision and reach the ephemeral pod.

## Lab notebook

`notebook` keeps a running JSONL log per session at `<cwd>/.dsh/notebook/<sessionId>.jsonl` — `action: "log"` for a hypothesis/method/observation/decision/note, `action: "read"` to recall it, `action: "export"` to render it to Markdown (or a `.zip` bundling that Markdown with every artifact file the entries link to — set `export_format: "zip"`).

A subagent the top-level agent delegates to runs in its own DSH session, but its `notebook` calls resolve to the **same** file as its ancestor's — the tool walks the session's delegation lineage (`session.header.parentSession`) back to the root, so a specialist's findings land in the one shared notebook rather than a file nobody reads.

## Scientific results

`scientific_result` is a structured, schema-validated card for a *terminal* finding — a results table (`kind: "table"`) or a statistical-test summary (`kind: "statistical_test"`) — with up to 20 linked workspace-relative artifacts (`role`: figure/table/script/report/data/log). Use it once you have a concrete finding to report; use `notebook` for the running log on the way there. It has no separate storage — the call and its result are already part of the session transcript.

## Workflow templates

`workflow` browses (`action: "list"`, filterable by `category`/`query`) and retrieves (`action: "get"`, with `values` filling `{placeholder}` tokens) a catalogue of ~330 one-click research-task prompt templates across 22 disciplines, ported from ResearchCraft's own template library.

## Development

Every server-side file is plain ESM JS — no build step. The Settings page (`client/`) is the exception: it's a browser bundle (React, esbuild) served to the DSH web client, built with:

```sh
npm install   # once, for esbuild
npm run build # after any client/ change — rebuilds lib/client.js
```

`lib/client.js` is committed so installing the plugin never needs a build step or `pnpm approve-builds` for this package itself.

## License

MIT — see [LICENSE](LICENSE). Scientific skills are seeded from the open-source [`K-Dense-AI/scientific-agent-skills`](https://github.com/K-Dense-AI/scientific-agent-skills) catalogue (MIT); see [NOTICE](NOTICE).
