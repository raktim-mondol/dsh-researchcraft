/**
 * zg CLI resolution, first-run install, and a small spawn helper.
 * Shared by the MCP mount (zvec-grep.js) and the native indexer
 * (zvec-index-engine.js). Keep inject: [] consumers importing this file —
 * do not put inject: ['tools'] on the MCP row.
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, statSync } from 'node:fs'
import { homedir } from 'node:os'
import { delimiter, dirname, isAbsolute, join, resolve } from 'node:path'

const STDIO_ARGS = ['server', '--stdio', '--mcp-toolset', 'agent']
const INSTALL_TIMEOUT_MS = 15 * 60 * 1000
/** Local retrieval model; no API key. ~130 MB on first download. */
export const DEFAULT_EMBEDDING = 'local/potion-retrieval-32m'
const BIN_NAMES = process.platform === 'win32' ? ['zg.cmd', 'zg.exe', 'zg'] : ['zg']
const NPM_BIN = process.platform === 'win32' ? 'npm.cmd' : 'npm'
export const LOG = '[dsh-researchcraft] zvec-grep'

export function dshHome() {
  return process.env.DSH_HOME || join(homedir(), '.dsh')
}

/** User-local npm prefix used when zg is not already installed. */
export function bundledInstallDir() {
  return join(dshHome(), 'zvec-grep')
}

function bundledCliJs() {
  return join(bundledInstallDir(), 'node_modules', '@zvec', 'zvec-grep', 'dist', 'cli', 'index.js')
}

function isJsEntry(path) {
  return path.endsWith('.js') || path.endsWith('.mjs') || path.endsWith('.cjs')
}

function launchFromCommand(command) {
  if (isJsEntry(command)) {
    return { command: process.execPath, args: [command, ...STDIO_ARGS], cli: [process.execPath, command] }
  }
  return { command, args: [...STDIO_ARGS], cli: [command] }
}

function findOnPath() {
  for (const dir of (process.env.PATH || '').split(delimiter)) {
    if (!dir) continue
    for (const bin of BIN_NAMES) {
      const candidate = join(dir, bin)
      if (existsSync(candidate)) return launchFromCommand(candidate)
    }
  }
  return undefined
}

function findGlobalNpm() {
  const execDir = dirname(process.execPath)
  for (const bin of BIN_NAMES) {
    const candidate = join(execDir, bin)
    if (existsSync(candidate)) return launchFromCommand(candidate)
  }
  const jsCandidates = [
    bundledCliJs(),
    join(execDir, '..', 'lib', 'node_modules', '@zvec', 'zvec-grep', 'dist', 'cli', 'index.js'),
    join(execDir, '..', 'node_modules', '@zvec', 'zvec-grep', 'dist', 'cli', 'index.js'),
    join(homedir(), '.npm-global', 'lib', 'node_modules', '@zvec', 'zvec-grep', 'dist', 'cli', 'index.js'),
    join(homedir(), '.local', 'lib', 'node_modules', '@zvec', 'zvec-grep', 'dist', 'cli', 'index.js'),
  ]
  for (const js of jsCandidates) {
    if (existsSync(js)) return launchFromCommand(js)
  }
  return undefined
}

/**
 * Resolve how DSH should spawn zg (stdio MCP + CLI).
 * Order: ZVEC_GREP_CLI, PATH, then a previous plugin install under $DSH_HOME/zvec-grep.
 */
export function resolveZgLaunch() {
  const override = process.env.ZVEC_GREP_CLI?.trim()
  if (override) return launchFromCommand(override)
  return findOnPath() || findGlobalNpm()
}

export function run(command, args, { cwd, timeoutMs, env, signal, onData, silent } = {}) {
  return new Promise((resolvePromise) => {
    const child = spawn(command, args, {
      cwd,
      env: env ?? process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    let out = ''
    const onChunk = (buf) => {
      const text = buf.toString()
      out += text
      onData?.(text)
      if (!silent) process.stderr.write(text)
    }
    child.stdout?.on('data', onChunk)
    child.stderr?.on('data', onChunk)
    let settled = false
    const finish = (code) => {
      if (settled) return
      settled = true
      if (timer) clearTimeout(timer)
      signal?.removeEventListener('abort', onAbort)
      resolvePromise({ code: code ?? 1, out, pid: child.pid })
    }
    const onAbort = () => {
      try { child.kill('SIGINT') } catch { /* already gone */ }
      setTimeout(() => { try { child.kill('SIGTERM') } catch { /* ignore */ } }, 1500)
      setTimeout(() => { try { child.kill('SIGKILL') } catch { /* ignore */ } }, 4000)
    }
    if (signal) {
      if (signal.aborted) onAbort()
      else signal.addEventListener('abort', onAbort, { once: true })
    }
    const timer = timeoutMs
      ? setTimeout(() => {
          child.kill('SIGTERM')
          finish(124)
        }, timeoutMs)
      : null
    child.on('close', (code) => finish(code ?? 1))
    child.on('error', (err) => {
      out += err.message
      finish(1)
    })
  })
}

function npmCommand() {
  const sibling = join(dirname(process.execPath), NPM_BIN)
  if (existsSync(sibling)) return sibling
  return NPM_BIN
}

export async function ensureZgInstalled() {
  const existing = resolveZgLaunch()
  if (existing) return existing
  if (process.env.ZVEC_GREP_SKIP_INSTALL === '1') return undefined

  const dir = bundledInstallDir()
  mkdirSync(dir, { recursive: true })
  console.warn(`${LOG}: installing @zvec/zvec-grep into ${dir} (first run; may take several minutes)`)
  const result = await run(npmCommand(), [
    'install',
    '--prefix', dir,
    '--no-fund',
    '--no-audit',
    '@zvec/zvec-grep',
  ], {
    cwd: dir,
    timeoutMs: INSTALL_TIMEOUT_MS,
    env: { ...process.env, npm_config_update_notifier: 'false' },
  })
  const launch = resolveZgLaunch()
  if (!launch) {
    console.warn(`${LOG}: install failed (exit ${result.code}); mcp__zvec_grep__* tools will be absent`)
    return undefined
  }
  console.warn(`${LOG}: CLI ready`)
  return launch
}

export function shouldIndexRoot(root) {
  if (typeof root !== 'string' || root.length === 0) return false
  if (!isAbsolute(root)) return false
  const abs = resolve(root)
  if (abs === resolve(homedir()) || abs === '/' || abs === homedir()) return false
  try {
    return statSync(abs).isDirectory()
  } catch {
    return false
  }
}

export function cliArgs(launch, rest) {
  return launch.cli.length === 2
    ? [launch.cli[1], ...rest]
    : rest
}

export function cliCommand(launch) {
  return launch.cli[0]
}

export function zgEnv(embedding, extra = {}) {
  const env = {
    ...process.env,
    ZVEC_GREP_EMBEDDING: embedding,
    ZVEC_GREP_MCP_TOOLSET: 'agent',
    ...extra,
  }
  return env
}

export function isAutoIndexOn(value) {
  const v = String(value || '').trim().toLowerCase()
  return v === 'yes' || v === 'true' || v === '1' || v === 'on'
}
