import { applyNotebook } from './notebook.js'
import { applyImageGenerate } from './image-generate.js'
import { applySciInspect } from './sci-inspect.js'
import { applyLatexCompile } from './latex-compile.js'
import { applyModalRun } from './modal-run.js'
import { applyRunpodRun } from './runpod-run.js'
import { applyWorkflows } from './workflows.js'
import { seed } from './seed.js'
import { registerKeysSettings } from './settings-keys.js'

export const name = 'dsh-researchcraft'
export const inject = ['tools', 'settings']

// The ResearchCraft persona and system-prompt guidance are NOT registered
// here: they live in prompt-section.js, mounted as a row inside
// presets/researchcraft/agent.cordis.yml so they apply only to sessions on
// the ResearchCraft preset. This apply() runs at the bundle (host) level —
// every session on every preset — so it carries only the tools and settings
// that are meant to be available everywhere.
export function apply(ctx) {
  seed()
  registerKeysSettings(ctx)
  applyNotebook(ctx)
  applyImageGenerate(ctx)
  applySciInspect(ctx)
  applyLatexCompile(ctx)
  applyModalRun(ctx)
  applyRunpodRun(ctx)
  applyWorkflows(ctx)
}
