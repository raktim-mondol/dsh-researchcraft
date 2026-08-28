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

## What it adds

- ResearchCraft persona and research system prompt
- Scientific skills catalogue (`scientific-agent-skills`, or `RESEARCHCRAFT_SKILLS_DIR`)
- `notebook` tool — log, read, and export a living lab notebook (JSONL under `<cwd>/.dsh/notebook/`)
- Specialist briefs (code-reviewer, literature-researcher, …) for the DSH `subagent` tool
- `image_generate` tool for conceptual scientific figures (Gemini "nano banana" by default)
- `sci_inspect` tool for scientific file formats (chemistry, structure, mass spec, arrays, imaging, AnnData)
- `latex_compile` tool (`.tex` → PDF, bibtex/biber-aware)
- `modal_run` / `runpod_run` tools for remote GPU/CPU compute offload
- `workflow` tool over a ~330-template research-task catalogue
- Academic search MCP connectors: Parallel, Firecrawl, Consensus, Scite
- Default agent preset `researchcraft` (standard tools + research identity)

## Academic search connectors

Four literature/web MCP servers are wired into the `researchcraft` preset and surface as `mcp__parallel__*`, `mcp__firecrawl__*`, `mcp__consensus__*`, `mcp__scite__*` tools:

| Connector | Env var | Without it |
|---|---|---|
| [Parallel](https://parallel.ai) — general + deep web search | `PARALLEL_API_KEY` (optional) | Works keyless, rate-limited |
| [Firecrawl](https://firecrawl.dev) — scrape/crawl/extract | `FIRECRAWL_API_KEY` (optional) | Works keyless, rate-limited |
| [Consensus](https://consensus.app) — evidence-backed answers over peer-reviewed papers | `CONSENSUS_API_KEY` (required) | Connector stays disabled |
| [Scite](https://scite.ai) — Smart Citations, supporting/contrasting context | `SCITE_API_KEY` (required) | Connector stays disabled |

Consensus and Scite's hosted MCP servers normally authenticate through an OAuth sign-in flow in a browser app; DSH has no interactive OAuth flow, so these connectors only activate when you supply a personal bearer token as the env var above.

## Image generation

`image_generate` writes conceptual schematics, diagrams, and illustrations to the workspace — not quantitative plots (those should be real Python/matplotlib output over real data).

- **Default (Gemini "nano banana"):** set `GEMINI_API_KEY`. Defaults to model `gemini-2.5-flash-image`; override with `IMAGE_MODEL`.
- **OpenAI-compatible Images API instead:** set `IMAGE_PROVIDER=openai`, `IMAGE_MODEL`, `IMAGE_BASE_URL`, `IMAGE_API_KEY`.

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

| Tool | Env vars | Get credentials |
|---|---|---|
| `modal_run` | `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | https://modal.com/settings |
| `runpod_run` | `RUNPOD_API_KEY` | https://console.runpod.io/user/settings |

`runpod_run` also needs `ssh`, `scp`, and `ssh-keygen` on `PATH` (standard OpenSSH client tools) to provision and reach the ephemeral pod.

## Workflow templates

`workflow` browses (`action: "list"`, filterable by `category`/`query`) and retrieves (`action: "get"`, with `values` filling `{placeholder}` tokens) a catalogue of ~330 one-click research-task prompt templates across 22 disciplines, ported from ResearchCraft's own template library.

## License

MIT — see [LICENSE](LICENSE). Scientific skills are seeded from the open-source [`K-Dense-AI/scientific-agent-skills`](https://github.com/K-Dense-AI/scientific-agent-skills) catalogue (MIT); see [NOTICE](NOTICE).
