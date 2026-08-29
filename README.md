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

The persona, the longer research system prompt (notebook discipline, specialist roster, MCP connector guidance, …), and the four academic search connectors (`mcp__parallel__*` etc.) are only present on this preset — a session left on the default one won't have them, and asking it to use e.g. the Parallel connector will fail with `tools[name] is not a function`. The general-purpose tools below (notebook, image_generate, sci_inspect, latex_compile, modal_run/runpod_run, workflow) are available on every preset regardless, since they're registered at the plugin/bundle level rather than inside the ResearchCraft preset.

The preset picker remembers your last choice per browser, so you'll typically only need to do this once.

## What it adds

- **ResearchCraft agent preset** — persona, research system prompt (notebook discipline, specialist roster, connector guidance), standard coding tools, and the 4 academic MCP connectors below. Select it explicitly per chat — see [Run](#run).
- Scientific skills catalogue (`scientific-agent-skills`, or `RESEARCHCRAFT_SKILLS_DIR`) — available on every preset
- `notebook` tool — log, read, and export a living lab notebook (JSONL under `<cwd>/.dsh/notebook/`) — every preset
- Specialist briefs (code-reviewer, literature-researcher, …) for the DSH `subagent` tool — every preset
- `image_generate` tool for conceptual scientific figures (Gemini "nano banana" by default) — every preset
- `sci_inspect` tool for scientific file formats (chemistry, structure, mass spec, arrays, imaging, AnnData) — every preset
- `latex_compile` tool (`.tex` → PDF, bibtex/biber-aware) — every preset
- `modal_run` / `runpod_run` tools for remote GPU/CPU compute offload — every preset
- `workflow` tool over a ~330-template research-task catalogue — every preset
- Academic search MCP connectors: Parallel, Firecrawl, Consensus, Scite — **ResearchCraft preset only**
- A **Settings → ResearchCraft API keys** page for all of the above — no shell env vars required

## API keys

Every credential below (`PARALLEL_API_KEY`, `FIRECRAWL_API_KEY`, `CONSENSUS_API_KEY`, `SCITE_API_KEY`, `GEMINI_API_KEY`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `RUNPOD_API_KEY`) can be set two ways:

- **Settings → ResearchCraft API keys** in the DSH web UI — type a key, Save. Persisted in the profile's `settings.yaml`; a blank field always means "keep the current value", Clear removes it.
- **Shell environment variable** — takes priority over Settings when both are set.

Tools that call `resolveEnv()` per invocation (`image_generate`, `modal_run`, `runpod_run`) pick up a Settings change on the very next call, no restart needed.

The four MCP connectors (below) are different: the `researchcraft` agent preset mounts once as a standing composition shared by every chat session for the life of the running `dsh` process, so a key change only reaches them after you **stop and restart `dsh` itself** — a new chat session on the same running process is not enough.

**Also make sure the chat session is actually on the ResearchCraft preset.** The connectors are wired into the `researchcraft` agent preset only; a session left on the default preset (Standard/PTC/etc.) has no `mcp__parallel__*`/`mcp__firecrawl__*`/`mcp__consensus__*`/`mcp__scite__*` tools at all, and calling one fails with `tools[name] is not a function`. Check the preset selector next to the session title (top of the message box for a new chat, top-left of an existing one) reads "ResearchCraft" before asking the agent to search.

## Academic search connectors

Four literature/web MCP servers are wired into the `researchcraft` preset and surface as `mcp__parallel__*`, `mcp__firecrawl__*`, `mcp__consensus__*`, `mcp__scite__*` tools:

| Connector | Key | Without it |
|---|---|---|
| [Parallel](https://parallel.ai) — general + deep web search | `PARALLEL_API_KEY` (optional) | Works keyless, rate-limited |
| [Firecrawl](https://firecrawl.dev) — scrape/crawl/extract | `FIRECRAWL_API_KEY` (optional) | Works keyless, rate-limited |
| [Consensus](https://consensus.app) — evidence-backed answers over peer-reviewed papers | `CONSENSUS_API_KEY` (required) | Connector stays disabled |
| [Scite](https://scite.ai) — Smart Citations, supporting/contrasting context | `SCITE_API_KEY` (required) | Connector stays disabled |

Set any of these via Settings → ResearchCraft API keys or the matching env var (see [API keys](#api-keys)). Consensus and Scite's hosted MCP servers normally authenticate through an OAuth sign-in flow in a browser app; DSH has no interactive OAuth flow, so these two connectors only activate once a personal bearer token is available from either source.

## Image generation

`image_generate` writes conceptual schematics, diagrams, and illustrations to the workspace — not quantitative plots (those should be real Python/matplotlib output over real data).

- **Default (Gemini "nano banana"):** set `GEMINI_API_KEY` (Settings or env). Defaults to model `gemini-2.5-flash-image`; override with `IMAGE_MODEL` (env only).
- **OpenAI-compatible Images API instead:** set `IMAGE_PROVIDER=openai`, `IMAGE_MODEL`, `IMAGE_BASE_URL` (env only) plus `IMAGE_API_KEY` (Settings or env).

## Scientific file inspection

`sci_inspect` summarizes SMILES/MOL/SDF, PDB/CIF, mzML and other mass-spec formats, npy/npz/parquet/hdf5, TIFF/NIfTI/DICOM, and h5ad files by shelling out to the bundled Python helpers under `python-helpers/`.

Set up the helper venv once (needs [uv](https://docs.astral.sh/uv/)):

```sh
cd python-helpers && uv sync
```

The tool finds `python-helpers/.venv` automatically. Override with `RESEARCHCRAFT_HELPERS_DIR` (a different helpers checkout) or `RESEARCHCRAFT_PYTHON` (a specific interpreter).

## LaTeX

`latex_compile` compiles a `.tex` file to PDF: `latexmk` when it's on `PATH` (handles bibtex/biber automatically), otherwise a `pdflatex`/`xelatex`/`lualatex` fallback with a bibtex/biber pass when the source needs one. Requires a TeX Live (or similar) install.

## Remote compute

`modal_run` and `runpod_run` offload a command to a remote CPU/GPU instance — upload inputs, run, download outputs, always terminate when done.

| Tool | Key (Settings or env) | Get credentials |
|---|---|---|
| `modal_run` | `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | https://modal.com/settings |
| `runpod_run` | `RUNPOD_API_KEY` | https://console.runpod.io/user/settings |

`runpod_run` also needs `ssh`, `scp`, and `ssh-keygen` on `PATH` (standard OpenSSH client tools) to provision and reach the ephemeral pod.

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
