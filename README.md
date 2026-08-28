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
dsh-researchcraft
```

Same as `dsh --profile researchcraft`. Opens the Harness web UI (typically `http://127.0.0.1:3080`).

## What it adds

- ResearchCraft persona and research system prompt
- Scientific skills catalogue (`scientific-agent-skills`, or `RESEARCHCRAFT_SKILLS_DIR`)
- `notebook` tool (JSONL under `<cwd>/.dsh/notebook/`)
- Specialist briefs (code-reviewer, literature-researcher, …) for the DSH `subagent` tool
- Default agent preset `researchcraft` (standard tools + research identity)

## License

MIT — see [LICENSE](LICENSE). Scientific skills are seeded from the open-source [`K-Dense-AI/scientific-agent-skills`](https://github.com/K-Dense-AI/scientific-agent-skills) catalogue (MIT); see [NOTICE](NOTICE).
