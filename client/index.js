/**
 * dsh-researchcraft client plugin: adds a Settings page for the API keys
 * ResearchCraft's server-side tools and MCP connectors read (the launching
 * shell's environment always takes priority over a key set here). Registers
 * one `settings.section` entry; nothing else in the web UI is touched.
 *
 * Uses `ctx.settingsScope` (an injected Service, like `ctx.slots`), not
 * `ctx.remote.credentials`: dotted `ctx.remote.<namespace>` access resolves
 * to a separate, permanently-empty instance from a dynamically-loaded
 * third-party client plugin in this harness version (verified by direct
 * testing) — the dedicated secret-credential wire seam is unusable from here.
 */
// Type-only in the TS original; kept as a plain comment here since this
// package has no client type-check step — ctx.settingsScope and ctx.slots
// come from @deepseek-ai/dsh-client-ui-settings and
// @deepseek-ai/dsh-client-ui-slots, already mounted by dsh-web-app.
import { ApiKeysSection } from './ApiKeysSection.jsx'

const NAMESPACE = 'dsh-researchcraft-keys'

export const inject = ['slots', 'settingsScope']

export function apply(ctx) {
  const scope = ctx.settingsScope.bind({ namespace: NAMESPACE })

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'researchcraft-api-keys',
    order: 60,
    label: () => 'ResearchCraft API keys',
    inject: () => ({ scope }),
  }, ApiKeysSection))
}
