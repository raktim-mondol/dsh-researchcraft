import { useEffect, useState } from 'react'

/** The settings fields this section manages, grouped for display. */
const KEYS = [
  { field: 'PARALLEL_API_KEY', label: 'Parallel', group: 'Literature search', hint: 'Optional — raises the keyless rate limit.' },
  { field: 'FIRECRAWL_API_KEY', label: 'Firecrawl', group: 'Literature search', hint: 'Optional — raises the keyless rate limit.' },
  { field: 'CONSENSUS_API_KEY', label: 'Consensus', group: 'Literature search', hint: 'Required to enable this connector.' },
  { field: 'SCITE_API_KEY', label: 'Scite', group: 'Literature search', hint: 'Required to enable this connector.' },
  { field: 'GEMINI_API_KEY', label: 'Gemini (nano banana)', group: 'Image generation', hint: 'Enables the image_generate tool.' },
  { field: 'MODAL_TOKEN_ID', label: 'Modal — token ID', group: 'Remote compute', hint: 'From modal.com/settings.' },
  { field: 'MODAL_TOKEN_SECRET', label: 'Modal — token secret', group: 'Remote compute', hint: 'From modal.com/settings.' },
  { field: 'RUNPOD_API_KEY', label: 'Runpod', group: 'Remote compute', hint: 'From console.runpod.io/user/settings.' },
]

const GROUPS = [...new Set(KEYS.map((k) => k.group))]

/** Props supplied by our own client/index.js registration: { scope }. */
export function ApiKeysSection(props) {
  const { scope } = props
  const [snapshot, setSnapshot] = useState(() => scope.getSnapshot())
  const [drafts, setDrafts] = useState({})
  const [busy, setBusy] = useState({})
  const [errors, setErrors] = useState({})

  useEffect(() => scope.subscribe(() => setSnapshot(scope.getSnapshot())), [scope])

  if (snapshot.status === 'loading') {
    return (
      <div style={{ padding: '4px 0' }}>
        <p style={{ margin: 0, opacity: 0.75, fontSize: '0.9em' }}>Connecting…</p>
      </div>
    )
  }
  if (snapshot.status === 'unavailable') {
    return (
      <div style={{ padding: '4px 0' }}>
        <p style={{ margin: 0, opacity: 0.75, fontSize: '0.9em' }}>
          Settings storage is unavailable in this browser session (non-loopback connections don't get durable
          settings). Set the matching environment variables before starting DSH instead.
        </p>
      </div>
    )
  }

  const writable = snapshot.writable !== false
  const isConfigured = (field) => Boolean(snapshot.value?.[field])

  const save = async (field) => {
    const value = (drafts[field] ?? '').trim()
    if (!value) return
    setBusy((b) => ({ ...b, [field]: true }))
    setErrors((e) => ({ ...e, [field]: undefined }))
    try {
      await scope.set(field, value)
      setDrafts((d) => ({ ...d, [field]: '' }))
    } catch (error) {
      setErrors((e) => ({ ...e, [field]: error instanceof Error ? error.message : String(error) }))
    } finally {
      setBusy((b) => ({ ...b, [field]: false }))
    }
  }

  const clear = async (field) => {
    setBusy((b) => ({ ...b, [field]: true }))
    setErrors((e) => ({ ...e, [field]: undefined }))
    try {
      await scope.unset(field)
    } catch (error) {
      setErrors((e) => ({ ...e, [field]: error instanceof Error ? error.message : String(error) }))
    } finally {
      setBusy((b) => ({ ...b, [field]: false }))
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', padding: '4px 0' }}>
      <p style={{ margin: 0, opacity: 0.75, fontSize: '0.9em' }}>
        API keys for ResearchCraft's academic-search connectors, image generation, and remote-compute tools.
        A key set here is used only when the matching environment variable isn't already set when DSH starts.
      </p>
      {!writable && (
        <p style={{ color: 'var(--color-danger, #c0392b)', margin: 0, fontSize: '0.85em' }}>
          Settings storage is read-only in this session.
        </p>
      )}
      {GROUPS.map((group) => (
        <div key={group} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <h3 style={{ margin: 0, fontSize: '0.95em' }}>{group}</h3>
          {KEYS.filter((k) => k.group === group).map((k) => {
            const configured = isConfigured(k.field)
            return (
              <div key={k.field} style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <label style={{ fontSize: '0.85em' }}>
                  {k.label}
                  {' — '}
                  {configured ? 'configured' : 'not set'}
                </label>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder={configured ? 'leave blank to keep' : 'not set'}
                    value={drafts[k.field] ?? ''}
                    disabled={Boolean(busy[k.field]) || !writable}
                    onChange={(e) => setDrafts((d) => ({ ...d, [k.field]: e.target.value }))}
                    style={{ flex: 1 }}
                  />
                  <button
                    type="button"
                    disabled={Boolean(busy[k.field]) || !writable || !(drafts[k.field]?.trim())}
                    onClick={() => save(k.field)}
                  >
                    Save
                  </button>
                  <button
                    type="button"
                    disabled={Boolean(busy[k.field]) || !writable || !configured}
                    onClick={() => clear(k.field)}
                  >
                    Clear
                  </button>
                </div>
                {errors[k.field] && <p style={{ color: 'var(--color-danger, #c0392b)', margin: 0, fontSize: '0.85em' }}>{errors[k.field]}</p>}
                {k.hint && <p style={{ margin: 0, opacity: 0.6, fontSize: '0.8em' }}>{k.hint}</p>}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
