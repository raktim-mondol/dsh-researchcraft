/**
 * zvec-grep (zg) MCP connector on the ResearchCraft preset.
 *
 * First ResearchCraft start (after `dsh plugin add`) installs the zg CLI into
 * `$DSH_HOME/zvec-grep` if it is not already on PATH / ZVEC_GREP_CLI, then
 * mounts `mcp__zvec_grep__zvec_grep_search` in the same process — no second
 * restart. Indexing is opt-in: Settings "Index at session start" defaults to
 * no. The user can index later from chat (`zvec_index`) or by answering yes
 * when the agent asks. Progress and Cancel live in Settings and the session
 * header. Exact words/regex/filenames stay on native `grep` / `glob`.
 */
import { isAbsolute } from 'node:path'
import * as McpClient from '@deepseek-ai/dsh-mcp-client'
import { resolveEnv } from './credential-env.js'
import {
  bundledInstallDir,
  DEFAULT_EMBEDDING,
  ensureZgInstalled,
  isAutoIndexOn,
  LOG,
  shouldIndexRoot,
} from './zvec-grep-cli.js'
import {
  ensureCancelWatch,
  resetStaleIndexState,
  startIndex,
  waitForIndex,
} from './zvec-index-engine.js'

export const name = 'dsh-researchcraft-zvec-grep'
// Same as mcp-connectors.js: this row only registers into the host `tools`
// registry. Declaring inject: ['tools'] on the standing preset fiber can
// stall apply() so the CLI is never installed.
export const inject = []

const SEARCH_TOOL = 'mcp__zvec_grep__zvec_grep_search'
const TOOL_CALL_TIMEOUT_MS = 600_000

export {
  bundledInstallDir,
  DEFAULT_EMBEDDING,
  dshHome,
  ensureZgInstalled,
  resolveZgLaunch,
} from './zvec-grep-cli.js'

function sessionCwd(session) {
  const cwd = session?.header?.cwd
  return typeof cwd === 'string' && cwd.length > 0 ? cwd : undefined
}

function mountSearch(ctx, launch, embedding, apiKey) {
  const env = {
    ZVEC_GREP_MCP_TOOLSET: 'agent',
    ZVEC_GREP_EMBEDDING: embedding,
  }
  if (apiKey) env.ZVEC_GREP_API_KEY = apiKey

  ctx.plugin(McpClient, {
    serverName: 'zvec_grep',
    transport: 'stdio',
    command: launch.command,
    args: launch.args,
    env,
    failOnStartupError: false,
    toolCallTimeoutMs: TOOL_CALL_TIMEOUT_MS,
  })

  ctx.on('session/created', (session) => {
    if (session?.header?.origin === 'subagent') return
    const preset = session?.header?.agentPreset
    if (preset && preset !== 'researchcraft') return
    const cwd = sessionCwd(session)
    if (!shouldIndexRoot(cwd)) return
    void (async () => {
      const auto = await resolveEnv('ZVEC_GREP_AUTO_INDEX')
      if (!isAutoIndexOn(auto)) return
      const liveEmbedding = (await resolveEnv('ZVEC_GREP_EMBEDDING')) || embedding
      await startIndex({
        root: cwd,
        launch,
        embedding: liveEmbedding,
        wait: false,
        skipIfReady: true,
      })
    })()
  }, { global: true })

  // Never *start* an index from a search. If the user already started one
  // (session-start or zvec_index), wait so the first search is not empty.
  ctx.on('tools/pre-execute', async (exec, next) => {
    if (exec?.name !== SEARCH_TOOL) return next()
    const argRoot = exec.arguments && typeof exec.arguments === 'object'
      ? exec.arguments.root
      : undefined
    const root = typeof argRoot === 'string' && isAbsolute(argRoot)
      ? argRoot
      : exec.agent?.session?.header?.cwd
    if (shouldIndexRoot(root)) await waitForIndex(root, exec.signal)
    return next()
  })
}

export async function apply(ctx) {
  const launch = await ensureZgInstalled()
  if (!launch) {
    console.warn(
      `${LOG}: CLI not found; mcp__zvec_grep__* tools will be absent. `
      + `Set ZVEC_GREP_CLI or check ${bundledInstallDir()}.`,
    )
    return
  }

  ensureCancelWatch()
  resetStaleIndexState()

  const [embedding, apiKey] = await Promise.all([
    resolveEnv('ZVEC_GREP_EMBEDDING'),
    resolveEnv('ZVEC_GREP_API_KEY'),
  ])
  mountSearch(ctx, launch, embedding || DEFAULT_EMBEDDING, apiKey)
}
