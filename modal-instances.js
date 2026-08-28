/**
 * Modal compute instance catalog — maps a user-facing instance id (e.g. "h100")
 * onto concrete Modal Sandbox resources (GPU string, CPU, memory) and the
 * hourly rate used to estimate compute cost. GPU strings are the values
 * Modal's SDK accepts (SandboxCreateParams.gpu).
 */

const DEFAULT_IMAGE = 'python:3.13-slim'

export const MODAL_INSTANCES = [
  { id: 'cpu', label: 'CPU', gpu: null, cpu: 1, memoryMiB: 2048, pricePerHour: 0.05, defaultImage: DEFAULT_IMAGE },
  { id: 't4', label: 'T4', gpu: 'T4', cpu: 2, memoryMiB: 8192, pricePerHour: 0.59, defaultImage: DEFAULT_IMAGE },
  { id: 'l4', label: 'L4', gpu: 'L4', cpu: 2, memoryMiB: 8192, pricePerHour: 0.8, defaultImage: DEFAULT_IMAGE },
  { id: 'a10g', label: 'A10G', gpu: 'A10G', cpu: 4, memoryMiB: 16384, pricePerHour: 1.1, defaultImage: DEFAULT_IMAGE },
  { id: 'a100-40gb', label: 'A100 40GB', gpu: 'A100-40GB', cpu: 4, memoryMiB: 32768, pricePerHour: 2.78, defaultImage: DEFAULT_IMAGE },
  { id: 'a100-80gb', label: 'A100 80GB', gpu: 'A100-80GB', cpu: 8, memoryMiB: 65536, pricePerHour: 3.4, defaultImage: DEFAULT_IMAGE },
  { id: 'h100', label: 'H100', gpu: 'H100', cpu: 8, memoryMiB: 65536, pricePerHour: 4.56, defaultImage: DEFAULT_IMAGE },
]

const BY_ID = new Map(MODAL_INSTANCES.map((i) => [i.id, i]))

export const MODAL_INSTANCE_IDS = MODAL_INSTANCES.map((i) => i.id)
export const DEFAULT_MODAL_INSTANCE_ID = 'cpu'

export function resolveModalInstance(id) {
  if (!id) return null
  return BY_ID.get(id) ?? null
}
