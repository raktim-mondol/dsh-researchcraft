/**
 * Bundle a session's lab notebook as a zip: lab-notebook.md (artifact links
 * rewritten to resolve inside the bundle) plus every referenced artifact
 * file under artifacts/<workspace-relative-path>. Missing, path-escaping, or
 * non-file artifacts are skipped and reported in `missing` rather than
 * failing the whole export.
 */
import { statSync } from 'node:fs'
import { posix, resolve } from 'node:path'
import AdmZip from 'adm-zip'
import { notebookToMarkdown } from './notebook-export.js'

/** Resolve a workspace-relative path, refusing traversal outside the workspace root. */
function safeUnder(root, rel) {
  const target = resolve(root, rel)
  const normalizedRoot = resolve(root)
  if (target !== normalizedRoot && !target.startsWith(normalizedRoot + '/')) return undefined
  return target
}

function normalizeRel(rel) {
  return rel.replaceAll('\\', '/').replace(/^\/+/, '')
}

export function buildNotebookZip(entries, opts) {
  const zip = new AdmZip()
  const missing = new Set()
  const bundled = new Map() // original rel -> abs path
  for (const e of entries) {
    for (const p of e.artifacts ?? []) {
      if (bundled.has(p) || missing.has(p)) continue
      const abs = safeUnder(opts.sandboxRoot, normalizeRel(p))
      let ok = false
      try {
        ok = abs !== undefined && statSync(abs).isFile()
      } catch {
        ok = false
      }
      if (ok) bundled.set(p, abs)
      else missing.add(p)
    }
  }
  for (const [rel, abs] of bundled) {
    const archived = `artifacts/${normalizeRel(rel)}`
    zip.addLocalFile(abs, posix.dirname(archived), posix.basename(archived))
  }
  const md = notebookToMarkdown(entries, {
    sessionId: opts.sessionId,
    artifactHref: (p) => (bundled.has(p) ? `artifacts/${normalizeRel(p)}` : undefined),
    missingArtifacts: missing,
  })
  zip.addFile('lab-notebook.md', Buffer.from(md, 'utf-8'))
  return { buffer: zip.toBuffer(), missing: [...missing] }
}
