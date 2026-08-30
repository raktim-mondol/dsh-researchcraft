/**
 * Academic search MCP connectors (Parallel, Firecrawl, Scite), mounted
 * programmatically instead of as static cordis.yml rows so each server's
 * auth can come from the `dsh-researchcraft-keys` settings store
 * (Settings -> ResearchCraft API keys) as well as the matching env var.
 * Resolved once when the `researchcraft` preset first mounts. That mount is
 * a STANDING composition shared by every session naming the preset for the
 * life of the running `dsh` process (see @deepseek-ai/dsh-agent-presets) —
 * a new chat session does NOT get a fresh mount, so a key entered or
 * changed in Settings only reaches these connectors after `dsh` itself is
 * stopped and restarted, not merely after starting a new session (verified
 * live: a freshly-saved key was still invisible to a brand-new session on
 * the correct preset). `dsh-mcp-client`'s own config is fixed per instance,
 * and env vars have the same restart requirement.
 *
 * Parallel and Firecrawl work keyless (rate-limited); Scite authenticates via
 * OAuth sign-in in its own browser app normally — DSH has no interactive
 * OAuth flow, so it only mounts when a personal bearer token is available.
 *
 * Consensus is NOT here: it moved off its MCP server (which needed the same
 * OAuth workaround) to a plain REST API with `x-api-key` auth, so it's now
 * `consensus-search.js` — a native per-call tool, not a standing MCP mount,
 * which also means a Settings-changed CONSENSUS_API_KEY takes effect on the
 * next call rather than needing a restart. See presets/researchcraft/agent.cordis.yml.
 */
import * as McpClient from '@deepseek-ai/dsh-mcp-client'
import { resolveEnv } from './credential-env.js'

export const name = 'dsh-researchcraft-mcp-connectors'
export const inject = []

export async function apply(ctx) {
  const [parallelKey, firecrawlKey, sciteKey] = await Promise.all([
    resolveEnv('PARALLEL_API_KEY'),
    resolveEnv('FIRECRAWL_API_KEY'),
    resolveEnv('SCITE_API_KEY'),
  ])

  ctx.plugin(McpClient, {
    serverName: 'parallel',
    transport: 'streamable-http',
    url: 'https://search.parallel.ai/mcp',
    ...(parallelKey ? { headers: { Authorization: `Bearer ${parallelKey}` } } : {}),
  })

  ctx.plugin(McpClient, {
    serverName: 'firecrawl',
    transport: 'streamable-http',
    url: firecrawlKey
      ? `https://mcp.firecrawl.dev/${encodeURIComponent(firecrawlKey)}/v2/mcp`
      : 'https://mcp.firecrawl.dev/v2/mcp',
  })

  if (sciteKey) {
    ctx.plugin(McpClient, {
      serverName: 'scite',
      transport: 'streamable-http',
      url: 'https://api.scite.ai/mcp',
      headers: { Authorization: `Bearer ${sciteKey}` },
    })
  }
}
