/**
 * Task-complexity model routing for delegated specialists, mounted
 * programmatically (like mcp-connectors.js) instead of as static cordis.yml
 * rows so each model id can come from the `dsh-researchcraft-keys` settings
 * store (Settings -> ResearchCraft API keys) as well as the matching env
 * var. Adds two subagent tools alongside the default `subagent`
 * (presets/researchcraft/agent.cordis.yml), each pinned to a fixed model via
 * `agentOptions.model`:
 *
 * - `subagent_pro` — an escalation path for delegated work that needs
 *   noticeably more reasoning than routine review/research (deep multi-step
 *   analysis, hard proofs, large refactors), pinned to SUBAGENT_MODEL_COMPLEX
 *   (default "deepseek-v4-pro").
 * - `subagent_vision` — for delegating image-reading/visual-inspection work
 *   (figures, scans, screenshots) to a child whose route actually declares
 *   image input, pinned to SUBAGENT_MODEL_VISION (default
 *   "deepseek-v4-flash-vision-exp"). The child still does the reading itself
 *   with the shared `read_image` tool (@deepseek-ai/dsh-tool-fs) once routed
 *   to a vision-capable model — this tool only supplies the routing.
 *
 * The plain default `subagent` tool (agent.cordis.yml) is deliberately left
 * alone with no `agentOptions` override: it inherits whichever model the
 * session is already on, same as before this file existed. Forcing every
 * ordinary delegation onto a hardcoded model id would break delegation
 * outright in any deployment where that id isn't registered under the
 * session's provider — the "default" in "default to flash" is satisfied by
 * *not* overriding, not by pinning a string here.
 *
 * `@deepseek-ai/dsh-tool-subagent`'s `agentOptions` is read once when this
 * plugin instance mounts, not per call (unlike `resolveEnv()` fields such as
 * IMAGE_MODEL) — and the `researchcraft` preset mounts once as a standing
 * composition for the life of the running `dsh` process (see
 * mcp-connectors.js). So, like the MCP connector keys, a value changed in
 * Settings or the environment only reaches these two tools after `dsh`
 * itself is stopped and restarted.
 *
 * Model ids are resolved synchronously here (inline env/settings lookup,
 * not the async `resolveEnv()` used elsewhere in this plugin): `ctx.plugin`
 * validates a mounted child's config against its declared services eagerly,
 * so `agentOptions.model` has to be a plain string by the time `ctx.plugin`
 * is called, not a value an outstanding `await` still owns.
 *
 * `inject` must list every service a `ctx.plugin()`-mounted child reads,
 * not just what this module reads directly: Cordis gates `ctx.<service>`
 * property access per fiber, and mounting `@deepseek-ai/dsh-tool-subagent`
 * (whose 0.1.1-rc.2 `inject` is `tools`/`subagents`/`systemPrompt`) from
 * inside a fiber that never declared those itself throws `cannot get
 * property "subagents" without inject` the moment the child's `apply()`
 * reads `ctx.subagents.getProvider(...)` — a load-time failure, not a
 * runtime one, so it took the preset down instead of just these two tools.
 *
 * This plugin pins `@deepseek-ai/dsh-tool-subagent` to the same 0.1.1-rc.2
 * line as `npm install -g @deepseek-ai/dsh` (`latest`). That tool-subagent
 * forwards `agentOptions` to spawn without requiring an `agentOptions`
 * capability flag. The 0.1.2-alpha.2 tool-subagent *does* require that flag
 * and throws `provider "spawn" does not support child agentOptions` against
 * the 0.1.1-rc.2 spawn provider, which made `subagent_pro`/`subagent_vision`
 * vanish as "unknown tool". Stay on the matching `latest` packages.
 */
import * as ToolSubagent from '@deepseek-ai/dsh-tool-subagent'
import { getStoredKey } from './settings-keys.js'

export const name = 'dsh-researchcraft-subagent-models'
export const inject = ['tools', 'subagents', 'systemPrompt']

const DEFAULT_COMPLEX_MODEL = 'deepseek-v4-pro'
const DEFAULT_VISION_MODEL = 'deepseek-v4-flash-vision-exp'

function resolveEnvSync(name) {
  return process.env[name]?.trim() || getStoredKey(name)
}

export function apply(ctx) {
  const complexModel = resolveEnvSync('SUBAGENT_MODEL_COMPLEX')
  const visionModel = resolveEnvSync('SUBAGENT_MODEL_VISION')

  ctx.plugin(ToolSubagent, {
    provider: 'spawn',
    toolName: 'subagent_pro',
    backgroundMode: 'continuable',
    agentOptions: { model: complexModel || DEFAULT_COMPLEX_MODEL },
  })

  ctx.plugin(ToolSubagent, {
    provider: 'spawn',
    toolName: 'subagent_vision',
    backgroundMode: 'continuable',
    agentOptions: { model: visionModel || DEFAULT_VISION_MODEL },
  })
}
