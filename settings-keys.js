/**
 * The `dsh-researchcraft` host entry Config: API keys for the MCP
 * connectors, image generation, and remote-compute tools, plus a handful of
 * non-secret preferences (IMAGE_MODEL, SUBAGENT_MODEL_COMPLEX,
 * SUBAGENT_MODEL_VISION, ZVEC_GREP_EMBEDDING, ZVEC_GREP_AUTO_INDEX) that ride
 * along in the same schema/UI section for convenience — editable from
 * Settings -> ResearchCraft API keys.
 * Registered at plugin load; resolveEnv() (credential-env.js) reads the live
 * value on every call, so a value entered in Settings works without a
 * restart for fields read per-call (IMAGE_MODEL, ZVEC_GREP_AUTO_INDEX) —
 * process.env still wins when set. The two SUBAGENT_MODEL_* fields and
 * ZVEC_GREP_EMBEDDING / ZVEC_GREP_API_KEY feed standing preset mounts (see
 * subagent-models.js and zvec-grep.js) and need a `dsh` restart to apply,
 * same as the MCP connector keys below. ZVEC_GREP_INDEX_STATE /
 * ZVEC_GREP_INDEX_CANCEL are ephemeral progress/cancel wires, not user
 * credentials — hidden from the Settings form, written by the indexer.
 *
 * DSH 0.2.0 dropped `ctx.settings.register(namespace, schema)`. Keys live on
 * this plugin's Cordis Config (volatile strings) and persist through the
 * profile patch on Loader entry id `researchcraft`. The browser page uses
 * `ctx.configForms.get(KEYS_ENTRY_ID)`.
 *
 * Fields are deliberately NOT `role('secret')`: that role strips the field
 * from every client-facing snapshot unconditionally (the write still lands,
 * but no reader, including this plugin's own settings page, can ever read
 * it back to show "configured"). The web UI's own write-only design (blank
 * input, Save/Clear, never populating the field from the stored value) is
 * this plugin's actual protection against displaying a stored key.
 */
import { existsSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import z from '@deepseek-ai/schemastery'

export const KEYS_NAMESPACE = 'dsh-researchcraft-keys'
/** Loader row id of the host plugin; 0.2.0 settings forms key by entry id. */
export const KEYS_ENTRY_ID = 'researchcraft'

export const KEY_FIELDS = [
  'PARALLEL_API_KEY',
  'FIRECRAWL_API_KEY',
  'CONSENSUS_API_KEY',
  'SCITE_API_KEY',
  'UNPAYWALL_EMAIL',
  'GEMINI_API_KEY',
  'IMAGE_MODEL',
  'SUBAGENT_MODEL_COMPLEX',
  'SUBAGENT_MODEL_VISION',
  'MODAL_TOKEN_ID',
  'MODAL_TOKEN_SECRET',
  'RUNPOD_API_KEY',
  'ZVEC_GREP_EMBEDDING',
  'ZVEC_GREP_API_KEY',
  'ZVEC_GREP_AUTO_INDEX',
  'ZVEC_GREP_INDEX_STATE',
  'ZVEC_GREP_INDEX_CANCEL',
]

function fieldSchema() {
  const field = z.string().default('')
  return typeof field.volatile === 'function' ? field.volatile() : field
}

const shape = {}
for (const field of KEY_FIELDS) shape[field] = fieldSchema()
export const KeysSettingsSchema = z.object(shape)

let keysCtx
let keysConfig
let scope

function unwrapField(raw) {
  if (raw && typeof raw === 'object' && typeof raw.get === 'function') return raw.get()
  return raw
}

function readSection() {
  const out = {}
  if (!keysConfig) return out
  for (const field of KEY_FIELDS) {
    const value = unwrapField(keysConfig[field])
    out[field] = typeof value === 'string' ? value : ''
  }
  return out
}

function makeScope(ctx) {
  return {
    get() {
      return readSection()
    },
    async update(patch) {
      if (!ctx?.settings?.update) return
      await ctx.settings.update(KEYS_ENTRY_ID, patch)
    },
    watch(callback) {
      if (!ctx?.on) return () => {}
      let prev = readSection()
      const dispose = ctx.on('settings/document-updated', (id) => {
        if (id !== KEYS_ENTRY_ID) return
        const next = readSection()
        const prevSnap = prev
        prev = next
        try {
          const result = callback(next, prevSnap)
          if (result && typeof result.then === 'function') result.catch(() => {})
        } catch {
          // same containment as 0.1.x SettingsScope.watch
        }
      })
      return typeof dispose === 'function' ? dispose : () => {}
    },
  }
}

const SKIP_IMPORT_FIELDS = new Set(['ZVEC_GREP_INDEX_STATE', 'ZVEC_GREP_INDEX_CANCEL'])

/** Flat `dsh-researchcraft-keys:` mapping from a 0.1.x settings.yaml import. */
function parseImportedKeys(text) {
  const out = {}
  let inSection = false
  for (const line of String(text || '').split(/\r?\n/)) {
    if (/^[A-Za-z0-9_.-]+:\s*$/.test(line)) {
      inSection = line.startsWith(`${KEYS_NAMESPACE}:`)
      continue
    }
    if (!inSection) continue
    if (/^\S/.test(line)) {
      inSection = false
      continue
    }
    const match = line.match(/^\s+([A-Z0-9_]+):\s*(.*)$/)
    if (!match || !KEY_FIELDS.includes(match[1]) || SKIP_IMPORT_FIELDS.has(match[1])) continue
    let value = match[2].trim()
    if (
      (value.startsWith("'") && value.endsWith("'"))
      || (value.startsWith('"') && value.endsWith('"'))
    ) {
      value = value.slice(1, -1)
    }
    if (value) out[match[1]] = value
  }
  return out
}

/**
 * DSH 0.2.0 imported `settings.yaml` once, keyed by Loader entry id. The 0.1.x
 * namespace was `dsh-researchcraft-keys`, so those values stayed in
 * `settings.yaml.imported`. Copy them onto this entry when Config is empty.
 */
function migrateImportedKeys(ctx) {
  const current = readSection()
  const already = KEY_FIELDS.some((field) => !SKIP_IMPORT_FIELDS.has(field) && current[field])
  if (already || !ctx.settings?.update) return
  const home = process.env.DSH_HOME || join(homedir(), '.dsh')
  const imported = join(home, 'settings.yaml.imported')
  if (!existsSync(imported)) return
  let patch
  try {
    patch = parseImportedKeys(readFileSync(imported, 'utf8'))
  } catch {
    return
  }
  if (Object.keys(patch).length === 0) return
  ctx.settings.update(KEYS_ENTRY_ID, patch).catch((error) => {
    console.warn(`[dsh-researchcraft] could not migrate imported API keys: ${error?.message || error}`)
  })
}

/** Bind the live Config; call once, at plugin apply(). */
export function registerKeysSettings(ctx, config) {
  keysCtx = ctx
  keysConfig = config ?? {}
  scope = makeScope(ctx)
  if (typeof ctx.settings?.configure === 'function') {
    ctx.effect(() => ctx.settings.configure({ auto: false }))
  }
  migrateImportedKeys(ctx)
  return scope
}

/** Owner handle for this entry, or undefined before registration. */
export function getKeysScope() {
  return scope
}

/**
 * Read one key's current stored value, or undefined if unset/unregistered.
 * Trimmed the same way resolveEnv() trims process.env — otherwise a stray
 * leading/trailing space or newline from copy-pasting a token into the
 * Settings field (e.g. a trailing newline copied from a terminal or a
 * dashboard's "copy" button) is stored and returned verbatim: the UI shows
 * "configured" but the credential silently fails to authenticate.
 */
export function getStoredKey(name) {
  const value = scope?.get()?.[name]?.trim()
  return typeof value === 'string' && value.length > 0 ? value : undefined
}
