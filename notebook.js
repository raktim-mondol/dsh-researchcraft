import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { notebookToMarkdown } from './notebook-export.js'

const TYPES = ['hypothesis', 'method', 'observation', 'decision', 'note']
const STANCES = ['supports', 'refutes', 'neutral']
const CONFIDENCE = ['low', 'medium', 'high']

function workspaceRoot(exec) {
  const session = exec.agent?.session
  const cwd = session?.cwd ?? session?.workingDirectory
  if (typeof cwd === 'string' && cwd.length > 0) return cwd
  return process.cwd()
}

function sessionKey(exec) {
  const session = exec.agent?.session
  const id = session?.id ?? exec.agent?.sessionId
  if (typeof id === 'string' && id.length > 0) return id.replace(/[^A-Za-z0-9._-]/g, '_')
  return 'default'
}

function notebookFile(exec) {
  return join(workspaceRoot(exec), '.dsh', 'notebook', `${sessionKey(exec)}.jsonl`)
}

function readEntries(file) {
  try {
    const raw = readFileSync(file, 'utf8')
    const out = []
    for (const line of raw.split('\n')) {
      if (!line.trim()) continue
      try {
        out.push(JSON.parse(line))
      } catch {
        // skip a corrupt line; the rest of the log is still usable
      }
    }
    return out
  } catch (err) {
    if (err && err.code === 'ENOENT') return []
    throw err
  }
}

function render(value) {
  if (value && typeof value.path === 'string' && typeof value.entries === 'number') {
    return [{ type: 'text', text: `wrote lab notebook to ${value.path} (${value.entries} entries)` }]
  }
  return [{ type: 'text', text: JSON.stringify(value, null, 2) }]
}

/** Register the living lab-notebook tool. */
export function applyNotebook(ctx) {
  ctx.tools.register(defineTool({
    name: 'notebook',
    description: [
      'Log or read the living lab notebook for this session.',
      'Use action "log" (default) for a hypothesis, method, observation, decision, or note as you work — not as a dump at the end.',
      'Attach artifacts (workspace-relative paths) for figures, tables, and scripts.',
      'Every log returns an id. Thread later results with relatesTo and stance. Correct an earlier entry by logging a new one with supersedes.',
      'Use action "read" to recall ids and earlier findings.',
      'Use action "export" to render the session\'s entries to a readable Markdown lab record and write it into the workspace.',
    ].join(' '),
    parameters: {
      action: {
        type: 'string',
        enum: ['log', 'read', 'export'],
        description: 'log appends an entry; read returns this session\'s entries; export renders them to a Markdown file.',
      },
      export_path: {
        type: 'string',
        description: 'Workspace-relative output path for action=export (default lab-notebook.md).',
      },
      type: {
        type: 'string',
        enum: TYPES,
        description: 'Entry kind for action=log.',
      },
      title: { type: 'string', description: 'One-line headline (required for log).' },
      body: { type: 'string', description: 'Markdown detail.' },
      artifacts: {
        type: 'array',
        items: { type: 'string' },
        description: 'Workspace-relative paths this entry produced or references.',
      },
      code: {
        type: 'object',
        properties: {
          source: { type: 'string', description: 'Code or snippet text.' },
          lang: { type: 'string', description: 'Language for highlighting.' },
        },
        additionalProperties: false,
      },
      confidence: {
        type: 'string',
        enum: CONFIDENCE,
        description: 'Confidence, mainly for hypothesis/decision.',
      },
      tags: { type: 'array', items: { type: 'string' } },
      relatesTo: { type: 'string', description: 'Id of an earlier entry this one responds to.' },
      stance: {
        type: 'string',
        enum: STANCES,
        description: 'How this entry bears on relatesTo.',
      },
      supersedes: { type: 'string', description: 'Id of an earlier entry this one replaces.' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => render(value),
    },
    async execute(args, exec) {
      const action = args.action ?? 'log'
      const file = notebookFile(exec)
      if (action === 'read') {
        const entries = readEntries(file)
        return { file, count: entries.length, entries }
      }
      if (action === 'export') {
        const entries = readEntries(file)
        const markdown = notebookToMarkdown(entries, { sessionId: sessionKey(exec) })
        const rel = typeof args.export_path === 'string' && args.export_path.trim()
          ? args.export_path.trim()
          : 'lab-notebook.md'
        const root = workspaceRoot(exec)
        const out = isAbsolute(rel) ? rel : resolve(root, rel)
        mkdirSync(dirname(out), { recursive: true })
        writeFileSync(out, markdown, 'utf8')
        return { path: rel, entries: entries.length }
      }

      const title = typeof args.title === 'string' ? args.title.trim() : ''
      if (!title) throw new Error('notebook log requires a non-empty title')
      const type = args.type ?? 'note'
      if (!TYPES.includes(type)) throw new Error(`invalid notebook type: ${type}`)
      if (args.stance && !args.relatesTo) {
        throw new Error('stance requires relatesTo')
      }

      const entry = {
        id: exec.callId,
        timestamp: Date.now(),
        type,
        title,
      }
      if (args.body) entry.body = args.body
      if (Array.isArray(args.artifacts) && args.artifacts.length) entry.artifacts = args.artifacts
      if (args.code && typeof args.code === 'object' && args.code.source) entry.code = args.code
      if (args.confidence) entry.confidence = args.confidence
      if (Array.isArray(args.tags) && args.tags.length) entry.tags = args.tags
      if (args.relatesTo) entry.relatesTo = args.relatesTo
      if (args.stance) entry.stance = args.stance
      if (args.supersedes) entry.supersedes = args.supersedes

      mkdirSync(dirname(file), { recursive: true })
      appendFileSync(file, `${JSON.stringify(entry)}\n`, 'utf8')
      return {
        id: entry.id,
        type: entry.type,
        title: entry.title,
        file,
        hint: 'reference this id in relatesTo/supersedes to link later entries',
      }
    },
  }))
}
