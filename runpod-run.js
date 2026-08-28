import { existsSync, mkdirSync, statSync } from 'node:fs'
import { dirname, posix, resolve } from 'node:path'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { DEFAULT_RUNPOD_INSTANCE_ID, RUNPOD_INSTANCE_IDS, resolveRunpodInstance } from './runpod-instances.js'
import {
  createPod,
  deletePod,
  ephemeralPodName,
  makeEphemeralSshKey,
  scpDownload,
  scpUpload,
  sshExec,
  tarUploadDir,
  waitForPodSsh,
} from './runpod-client.js'

const WORKDIR = '/workspace'
const DEFAULT_TIMEOUT_S = 600
const MAX_TIMEOUT_S = 3600
const PROVISION_TIMEOUT_S = 300
const MAX_OUTPUT_CHARS = 16000

function workspaceRoot(exec) {
  const session = exec.agent?.session
  const cwd = session?.cwd ?? session?.workingDirectory
  if (typeof cwd === 'string' && cwd.length > 0) return cwd
  return process.cwd()
}

function safeUnder(root, rel) {
  const target = resolve(root, rel)
  const normalizedRoot = resolve(root)
  if (target !== normalizedRoot && !target.startsWith(normalizedRoot + '/')) {
    throw new Error(`path escapes the workspace: ${rel}`)
  }
  return target
}

function truncate(s) {
  if (s.length <= MAX_OUTPUT_CHARS) return s
  return `…(${s.length - MAX_OUTPUT_CHARS} earlier chars truncated)\n${s.slice(-MAX_OUTPUT_CHARS)}`
}

function shellQuote(s) {
  return `'${s.replace(/'/g, "'\\''")}'`
}

/** Register the Runpod ephemeral-pod remote-compute offload tool. */
export function applyRunpodRun(ctx) {
  ctx.tools.register(defineTool({
    name: 'runpod_run',
    description: [
      'Run a command or script on an ephemeral Runpod Pod (on-demand CPU or GPU) and get the result back.',
      'Use for heavy or GPU work that should not run locally: model training/fine-tuning, GPU inference, large simulations.',
      `Pick an instance by GPU need (one of: ${RUNPOD_INSTANCE_IDS.join(', ')}; default "${DEFAULT_RUNPOD_INSTANCE_ID}").`,
      'Upload inputs with files_in (workspace-relative) and name expected outputs in files_out — they are copied back into the local workspace.',
      'Requires RUNPOD_API_KEY (https://console.runpod.io/user/settings). Always terminates the pod when done.',
    ].join(' '),
    parameters: {
      command: { type: 'string', required: true, description: 'Shell command to run remotely (via bash -lc) in /workspace.' },
      instance: { type: 'string', enum: RUNPOD_INSTANCE_IDS, description: `Runpod instance id (default "${DEFAULT_RUNPOD_INSTANCE_ID}").` },
      image: { type: 'string', description: 'Docker image to run (default is instance-specific).' },
      files_in: { type: 'array', items: { type: 'string' }, description: 'Workspace-relative paths to upload into the remote /workspace before running.' },
      files_out: { type: 'array', items: { type: 'string' }, description: 'Workspace-relative paths to download back after the job finishes.' },
      timeout_sec: { type: 'integer', description: `Max seconds for the remote command (default ${DEFAULT_TIMEOUT_S}, max ${MAX_TIMEOUT_S}). Pod provisioning has a separate ${PROVISION_TIMEOUT_S}s cap.` },
      cloud_type: { type: 'string', enum: ['SECURE', 'COMMUNITY'], description: 'Runpod cloud tier (default COMMUNITY).' },
    },
    output: {
      schema: { type: 'json' },
      render(_args, value) {
        return [{ type: 'text', text: value.text }]
      },
    },
    async execute(args, exec) {
      const key = process.env.RUNPOD_API_KEY?.trim()
      if (!key) {
        return { error: 'not_configured', text: 'Runpod is not configured. Set RUNPOD_API_KEY (get one at https://console.runpod.io/user/settings).' }
      }

      const instanceId = args.instance ?? DEFAULT_RUNPOD_INSTANCE_ID
      const spec = resolveRunpodInstance(instanceId)
      if (!spec) {
        return { error: 'unknown_instance', text: `Unknown Runpod instance "${instanceId}". Valid instances: ${RUNPOD_INSTANCE_IDS.join(', ')}.` }
      }

      const root = workspaceRoot(exec)
      const timeoutSec = Math.min(Math.max(Math.floor(args.timeout_sec ?? DEFAULT_TIMEOUT_S), 1), MAX_TIMEOUT_S)
      const timeoutMs = timeoutSec * 1000
      const cloudType = args.cloud_type === 'SECURE' ? 'SECURE' : 'COMMUNITY'
      const imageName = args.image?.trim() || spec.defaultImage
      const signal = exec.signal

      let keys = null
      let podId = null
      const startedAt = Date.now()

      const terminate = async () => {
        if (podId) {
          const id = podId
          podId = null
          await deletePod(id).catch(() => {})
        }
        keys?.cleanup()
        keys = null
      }
      const onAbort = () => { void terminate() }
      signal?.addEventListener('abort', onAbort, { once: true })

      try {
        keys = makeEphemeralSshKey()

        const createBody = {
          name: ephemeralPodName(),
          imageName,
          containerDiskInGb: spec.containerDiskInGb,
          volumeInGb: 0,
          ports: ['22/tcp'],
          env: { PUBLIC_KEY: keys.publicKeyOpenSsh },
          cloudType,
          supportPublicIp: true,
        }
        if (spec.gpuTypeId) {
          createBody.gpuTypeIds = [spec.gpuTypeId]
          createBody.gpuCount = spec.gpuCount || 1
          createBody.computeType = 'GPU'
        } else {
          createBody.computeType = 'CPU'
          createBody.cpuFlavorIds = ['cpu3c-2-4']
        }

        const created = await createPod(createBody)
        podId = created.id
        if (!podId) throw new Error('Runpod create-pod returned no pod id')

        const { ssh } = await waitForPodSsh(podId, { timeoutMs: PROVISION_TIMEOUT_S * 1000, signal })

        await sshExec(keys.privateKeyPath, ssh, `mkdir -p ${WORKDIR}`, { timeoutMs: 60_000, signal, retries: 15 })

        const stagedIn = []
        const missingIn = []
        for (const rel of args.files_in ?? []) {
          const local = safeUnder(root, rel)
          if (!existsSync(local)) { missingIn.push(rel); continue }
          const remote = posix.join(WORKDIR, rel)
          if (statSync(local).isDirectory()) {
            await sshExec(keys.privateKeyPath, ssh, `mkdir -p ${shellQuote(posix.dirname(remote))}`, { timeoutMs: 60_000, signal })
            await scpUpload(keys.privateKeyPath, ssh, local, remote, { signal }).catch(async () => {
              await tarUploadDir(keys.privateKeyPath, ssh, local, remote, signal)
            })
            stagedIn.push(rel)
            continue
          }
          const remoteDir = posix.dirname(remote)
          if (remoteDir && remoteDir !== '.') {
            await sshExec(keys.privateKeyPath, ssh, `mkdir -p ${shellQuote(remoteDir)}`, { timeoutMs: 60_000, signal })
          }
          await scpUpload(keys.privateKeyPath, ssh, local, remote, { signal })
          stagedIn.push(rel)
        }

        const remoteCmd = `cd ${WORKDIR} && bash -lc ${shellQuote(args.command)}`
        const result = await sshExec(keys.privateKeyPath, ssh, remoteCmd, { timeoutMs, signal, retries: 2 })

        const collectedOut = []
        const missingOut = []
        for (const rel of args.files_out ?? []) {
          const local = safeUnder(root, rel)
          const remote = posix.join(WORKDIR, rel)
          try {
            mkdirSync(dirname(local), { recursive: true })
            await scpDownload(keys.privateKeyPath, ssh, remote, local, { signal })
            collectedOut.push(rel)
          } catch {
            missingOut.push(rel)
          }
        }

        const durationMs = Date.now() - startedAt
        const costUsd = (durationMs / 3_600_000) * spec.pricePerHour
        const summary = {
          provider: 'runpod',
          pod_id: podId,
          instance: spec.id,
          gpu: spec.gpuTypeId,
          image: imageName,
          cloud_type: cloudType,
          exit_code: result.exitCode,
          duration_ms: durationMs,
          cost_usd: Number(costUsd.toFixed(4)),
          ...(stagedIn.length ? { files_in: stagedIn } : {}),
          ...(missingIn.length ? { files_in_missing: missingIn } : {}),
          files_out: collectedOut,
          ...(missingOut.length ? { files_out_missing: missingOut } : {}),
        }
        const text = `${JSON.stringify(summary, null, 2)}\n\n--- stdout ---\n${truncate(result.stdout) || '(empty)'}\n\n--- stderr ---\n${truncate(result.stderr) || '(empty)'}`
        return { ...summary, text }
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error)
        return {
          error: 'runpod_failure',
          instance: spec.id,
          pod_id: podId,
          text: `Runpod run failed on instance "${spec.id}"${podId ? ` (pod ${podId})` : ''}: ${msg}\n`
            + 'If this is an authentication error, check RUNPOD_API_KEY. If the GPU is out of stock, try another instance or cloud_type SECURE.',
        }
      } finally {
        signal?.removeEventListener('abort', onAbort)
        await terminate()
      }
    },
    presentCall() {
      return { card: 'generic', title: 'Runpod compute', kind: 'other' }
    },
  }))
}
