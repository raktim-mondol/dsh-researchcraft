/**
 * dsh-researchcraft client plugin: Settings page for ResearchCraft API keys
 * plus zvec-grep index progress (header chip + tool card). Uses
 * `ctx.settingsScope` (not `ctx.remote.credentials`) — the dedicated
 * secret-credential wire seam does not resolve from this third-party client
 * plugin in this harness version.
 */
import { ApiKeysSection } from './ApiKeysSection.jsx'
import { ZvecIndexHeaderAction, ZvecIndexToolView } from './ZvecIndexProgress.jsx'

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

  ctx.slots.inject('conversation.session.header.actions', () => ctx.slots.register({
    name: 'conversation.session.header.actions',
    id: 'zvec-index-progress',
    order: 25,
    inject: () => ({ scope }),
  }, ZvecIndexHeaderAction))

  ctx.slots.inject('tool.call.toolview', () => ctx.slots.register({
    name: 'tool.call.toolview',
    key: 'zvec_index',
    inject: () => ({ scope }),
  }, ZvecIndexToolView))
}
