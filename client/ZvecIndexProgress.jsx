import { useEffect, useState } from 'react'

export const INDEX_STATE_FIELD = 'ZVEC_GREP_INDEX_STATE'
export const INDEX_CANCEL_FIELD = 'ZVEC_GREP_INDEX_CANCEL'

const errorText = { color: 'var(--color-danger, #c0392b)', margin: 0, fontSize: '0.85em' }
const hintText = { margin: 0, opacity: 0.6, fontSize: '0.8em' }

export function parseIndexState(raw) {
  if (typeof raw !== 'string' || raw.trim().length === 0) return { status: 'idle' }
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && typeof parsed.status === 'string') return parsed
  } catch {
    /* ignore */
  }
  return { status: 'idle' }
}

export function useIndexJob(scope) {
  const [snapshot, setSnapshot] = useState(() => scope.getSnapshot())
  useEffect(() => scope.subscribe(() => setSnapshot(scope.getSnapshot())), [scope])
  const job = parseIndexState(snapshot.value?.[INDEX_STATE_FIELD])
  return { snapshot, job, writable: snapshot.writable !== false }
}

function formatDuration(ms) {
  const total = Math.max(0, Math.floor(ms / 1000))
  const seconds = total % 60
  const minutes = Math.floor(total / 60) % 60
  const hours = Math.floor(total / 3600)
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`
  return `${seconds}s`
}

export function formatEta(job, now = Date.now()) {
  if (!job?.startedAt) return null
  const elapsed = Math.max(0, now - job.startedAt)
  const { current, total, percent } = job
  let ratio
  if (typeof current === 'number' && typeof total === 'number' && total > 0 && current > 0 && current < total) {
    ratio = current / total
  } else if (typeof percent === 'number' && percent > 0 && percent < 100) {
    ratio = percent / 100
  }
  if (!ratio) return elapsed > 0 ? `elapsed ${formatDuration(elapsed)}` : null
  const remaining = elapsed * (1 - ratio) / ratio
  return `elapsed ${formatDuration(elapsed)} · about ${formatDuration(remaining)} remaining`
}

function barPercent(job) {
  if (typeof job.percent === 'number') return Math.min(100, Math.max(0, job.percent))
  if (typeof job.current === 'number' && typeof job.total === 'number' && job.total > 0) {
    return Math.min(100, Math.max(0, Math.round((job.current / job.total) * 100)))
  }
  return null
}

export function ProgressBar({ job, compact }) {
  const [now, setNow] = useState(() => Date.now())
  const live = job.status === 'running' || job.status === 'cancelling'
  useEffect(() => {
    if (!live) return undefined
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [live])
  const pct = barPercent(job)
  const eta = formatEta(job, now)
  const height = compact ? 6 : 8
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: compact ? 4 : 6, minWidth: compact ? 180 : 0 }}>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
        aria-label={job.line || 'Workspace index'}
        style={{
          height,
          background: 'rgba(127,127,127,0.28)',
          borderRadius: 999,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: pct == null ? (live ? '35%' : '0%') : `${pct}%`,
            height: '100%',
            background: '#22c55e',
            opacity: pct == null && live ? 0.55 : 1,
            transition: 'width 0.35s ease',
          }}
        />
      </div>
      <div style={{ fontSize: compact ? 11 : '0.8em', opacity: 0.75, lineHeight: 1.35 }}>
        {pct != null ? `${pct}%` : (live ? 'working…' : job.status)}
        {job.line ? ` · ${job.line}` : ''}
        {eta ? ` · ${eta}` : ''}
      </div>
    </div>
  )
}

export async function requestIndexCancel(scope, job) {
  const token = job?.root || '1'
  await scope.set(INDEX_CANCEL_FIELD, token)
}

/** Settings-page progress + cancel, shown under Workspace search. */
export function IndexProgressPanel({ scope }) {
  const { job, writable } = useIndexJob(scope)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState()
  const live = job.status === 'running' || job.status === 'cancelling'
  if (job.status === 'idle' && !job.line) {
    return (
      <p style={hintText}>
        Indexing is off at session start by default. Turn it on above, or ask in chat to index later.
        While an index runs, a progress bar with estimated time and Cancel appear here and in the session header.
      </p>
    )
  }
  const onCancel = async () => {
    setBusy(true)
    setError(undefined)
    try {
      await requestIndexCancel(scope, job)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
      <label style={{ fontSize: '0.85em' }}>
        {live ? 'Indexing workspace' : job.status === 'ready' ? 'Index ready' : job.status === 'cancelled' ? 'Index cancelled' : job.status === 'failed' ? 'Index failed' : 'Workspace index'}
        {job.root ? ` — ${job.root}` : ''}
      </label>
      <ProgressBar job={job} />
      {live && (
        <div>
          <button type="button" disabled={busy || !writable || job.status === 'cancelling'} onClick={onCancel}>
            {job.status === 'cancelling' ? 'Cancelling…' : 'Cancel indexing'}
          </button>
        </div>
      )}
      {error && <p style={errorText}>{error}</p>}
    </div>
  )
}

/** Session-header chip: only visible while an index is running. */
export function ZvecIndexHeaderAction({ scope }) {
  const { job, writable } = useIndexJob(scope)
  const [busy, setBusy] = useState(false)
  const live = job.status === 'running' || job.status === 'cancelling'
  if (!live) return null
  const onCancel = async () => {
    setBusy(true)
    try {
      await requestIndexCancel(scope, job)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        maxWidth: 520,
        padding: '2px 8px',
        borderRadius: 8,
        background: 'var(--dsw-alias-fill-l2, rgba(127,127,127,0.12))',
      }}
    >
      <span style={{ fontSize: 12, whiteSpace: 'nowrap' }}>Indexing</span>
      <ProgressBar job={job} compact />
      <button
        type="button"
        disabled={busy || !writable || job.status === 'cancelling'}
        onClick={onCancel}
        style={{ fontSize: 12, flex: 'none' }}
      >
        {job.status === 'cancelling' ? 'Cancelling…' : 'Cancel'}
      </button>
    </div>
  )
}

function resultText(block) {
  if (!block || !('kind' in block)) return null
  const parts = Array.isArray(block.content)
    ? block.content.filter((c) => c && c.type === 'text').map((c) => c.text)
    : []
  if (parts.length) return parts.join('\n')
  if (block.isError) return 'Indexing failed'
  return null
}

/** Custom chat card for the zvec_index tool. */
export function ZvecIndexToolView({ block, scope, inspect }) {
  const { job } = useIndexJob(scope)
  const running = !block || !('kind' in block)
  const live = running && (job.status === 'running' || job.status === 'cancelling')
  const settled = resultText(block)
  const [busy, setBusy] = useState(false)
  const onCancel = async () => {
    setBusy(true)
    try {
      await requestIndexCancel(scope, job)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: '6px 8px',
        borderRadius: 8,
        background: 'var(--dsw-alias-fill-l2, rgba(127,127,127,0.08))',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
        <strong>Workspace index</strong>
        <span style={{ opacity: 0.7 }}>{live ? 'running' : running ? 'starting…' : (block?.isError ? 'failed' : 'done')}</span>
        {inspect && (
          <button type="button" onClick={inspect} style={{ marginLeft: 'auto', fontSize: 12 }}>Inspect</button>
        )}
      </div>
      {(live || running) && <ProgressBar job={job.status === 'idle' ? { status: 'running', line: 'Starting workspace index…', startedAt: Date.now() } : job} />}
      {live && (
        <div>
          <button type="button" disabled={busy || job.status === 'cancelling'} onClick={onCancel}>
            {job.status === 'cancelling' ? 'Cancelling…' : 'Cancel indexing'}
          </button>
        </div>
      )}
      {settled && !live && (
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12, opacity: 0.85 }}>{settled}</pre>
      )}
    </div>
  )
}
