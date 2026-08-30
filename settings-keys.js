/**
 * The `dsh-researchcraft-keys` settings namespace: API keys for the MCP
 * connectors, image generation, and remote-compute tools, plus a couple of
 * non-secret preferences (IMAGE_MODEL) that ride along in the same
 * namespace/UI section for convenience — editable from Settings ->
 * ResearchCraft API keys. Registered at plugin load; resolveEnv()
 * (credential-env.js) reads the live value on every call, so a value entered
 * in Settings works without a restart — process.env still wins when set.
 *
 * `ctx.remote.credentials` (the dedicated secret-credential wire seam) does
 * not resolve from a dynamically-loaded third-party client plugin in this
 * harness version — verified by direct testing, not merely undocumented.
 * `ctx.settingsScope` (used the same way by other third-party client
 * plugins, e.g. dsh-at-file) does resolve, so this plugin stores keys there
 * instead.
 *
 * Fields are deliberately NOT `role('secret')`: that role strips the field
 * from every client-facing snapshot unconditionally (verified — the write
 * still lands in settings.yaml, but no reader, including this plugin's own
 * settings page, can ever read it back to show "configured"). The web UI's
 * own write-only design (blank input, Save/Clear, never populating the
 * field from the stored value) is this plugin's actual protection against
 * displaying a stored key.
 */
import z from '@deepseek-ai/schemastery'
import { settingsNamespace } from '@deepseek-ai/dsh-settings'

export const KEYS_NAMESPACE = settingsNamespace('dsh-researchcraft-keys')

export const KEY_FIELDS = [
  'PARALLEL_API_KEY',
  'FIRECRAWL_API_KEY',
  'CONSENSUS_API_KEY',
  'SCITE_API_KEY',
  'GEMINI_API_KEY',
  'IMAGE_MODEL',
  'MODAL_TOKEN_ID',
  'MODAL_TOKEN_SECRET',
  'RUNPOD_API_KEY',
]

const shape = {}
for (const field of KEY_FIELDS) shape[field] = z.string().default('')
export const KeysSettingsSchema = z.object(shape)

let scope

/** Register the namespace; call once, at plugin apply(). */
export function registerKeysSettings(ctx) {
  scope = ctx.settings.register(KEYS_NAMESPACE, KeysSettingsSchema)
  return scope
}

/** Read one key's current stored value, or undefined if unset/unregistered. */
export function getStoredKey(name) {
  const value = scope?.get()?.[name]
  return typeof value === 'string' && value.length > 0 ? value : undefined
}
