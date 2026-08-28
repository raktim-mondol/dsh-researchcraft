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
- `notebook` tool (JSONL under `<cwd>/.dsh/notebook/`)
- Specialist briefs (code-reviewer, literature-researcher, …) for the DSH `subagent` tool
- `image_generate` tool for conceptual scientific figures (Gemini "nano banana" by default)
- Academic search MCP connectors: Parallel, Firecrawl, Consensus
- Default agent preset `researchcraft` (standard tools + research identity)

## Academic search connectors

Three literature/web MCP servers are wired into the `researchcraft` preset and surface as `mcp__parallel__*`, `mcp__firecrawl__*`, `mcp__consensus__*` tools:

| Connector | Env var | Without it |
|---|---|---|
| [Parallel](https://parallel.ai) — general + deep web search | `PARALLEL_API_KEY` (optional) | Works keyless, rate-limited |
| [Firecrawl](https://firecrawl.dev) — scrape/crawl/extract | `FIRECRAWL_API_KEY` (optional) | Works keyless, rate-limited |
| [Consensus](https://consensus.app) — evidence-backed answers over peer-reviewed papers | `CONSENSUS_API_KEY` (required) | Connector stays disabled |

Consensus's hosted MCP server normally authenticates through an OAuth sign-in flow in a browser app; DSH has no interactive OAuth flow, so its connector only activates when you supply a personal bearer token as `CONSENSUS_API_KEY`.

## Image generation

`image_generate` writes conceptual schematics, diagrams, and illustrations to the workspace — not quantitative plots (those should be real Python/matplotlib output over real data).

- **Default (Gemini "nano banana"):** set `GEMINI_API_KEY`. Defaults to model `gemini-2.5-flash-image`; override with `IMAGE_MODEL`.
- **OpenAI-compatible Images API instead:** set `IMAGE_PROVIDER=openai`, `IMAGE_MODEL`, `IMAGE_BASE_URL`, `IMAGE_API_KEY`.

## License

MIT — see [LICENSE](LICENSE). Scientific skills are seeded from the open-source [`K-Dense-AI/scientific-agent-skills`](https://github.com/K-Dense-AI/scientific-agent-skills) catalogue (MIT); see [NOTICE](NOTICE).
