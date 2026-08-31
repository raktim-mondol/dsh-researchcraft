---
name: agent-browser
description: "Browse and interact with live websites — navigate, fill forms, extract data, download datasets/files — when web_search/web_fetch can't reach rendered or interactive content. Delegate any screenshot it takes to subagent_vision."
---

# agent-browser

Load this when a research task needs a real, rendered browser rather than a text fetch — `web_search`/`web_fetch` and `mcp__firecrawl__*` cover plain pages and search, but not JS-rendered content, logins, forms, multi-step navigation, or clicking through to a download. Typical triggers: "find and download this dataset," "log into X and pull Y," "explore this site and tell me what's there," "fill out/submit this form," "does this page actually render correctly."

## Install

Missing `agent-browser` isn't a reason to ask the user — install it yourself, no root needed:

```bash
npm i -g agent-browser && agent-browser install   # persistent install, once
# or, for a single ad hoc task:
npx agent-browser@latest <command>...
```

`agent-browser install --with-deps` additionally pulls required browser libraries on Linux hosts if a run fails with a missing-dependency error.

## Before anything else

Read the CLI's own live docs — commands move faster than any static reference:

```bash
agent-browser skills get core --full
```

Then set a named session for the task (the default session is shared machine-wide and can hijack another agent's page):

```bash
export AGENT_BROWSER_SESSION="$(agent-browser session id --scope worktree --prefix research)"
```

## The core loop

```bash
agent-browser open <url>
agent-browser snapshot -i       # interactive elements only, ~200-400 tokens
agent-browser click @e3         # act on a ref from the snapshot
agent-browser snapshot -i       # re-snapshot — refs go stale after any page change
```

Use `agent-browser read <url>` instead of `open`+`snapshot` for plain reading (docs, articles) — it prefers markdown and needs no browser session at all for many sites.

## Downloading data

```bash
agent-browser download <sel> <path>     # download by clicking the element that triggers it
agent-browser read <direct-file-url>    # or fetch a direct URL straight into the workspace
```

Save into the workspace (e.g. `user_data/` or wherever the task's other inputs live), not `/tmp`, so the downloaded dataset is visible to the rest of the session.

## Screenshots need a vision model — delegate, don't eyeball

`agent-browser screenshot <path>` is the right call whenever the accessibility-tree snapshot isn't enough to judge a page — visual layout, a chart/canvas/image-heavy page, a CAPTCHA, confirming something *looks* right. But the main session's model is not guaranteed to have vision input. After capturing a screenshot, delegate reading it to `subagent_vision` (this plugin's vision-pinned specialist) rather than trying to interpret the PNG yourself:

```bash
agent-browser screenshot page.png
```

then delegate: "Read `page.png` with `read_image` and report `<what you need to know>`" to `subagent_vision`. Never guess at on-screen content, layout, or chart values from the snapshot text alone if a screenshot is available — request one.

## Cleanup

Always run `agent-browser close` (or `close --all`) when the task is done — the daemon otherwise keeps a browser alive for up to an hour of inactivity by default.
