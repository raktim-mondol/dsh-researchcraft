import { applyNotebook } from './notebook.js'
import { applyImageGenerate } from './image-generate.js'
import { applySciInspect } from './sci-inspect.js'
import { applyLatexCompile } from './latex-compile.js'
import { applyModalRun } from './modal-run.js'
import { applyRunpodRun } from './runpod-run.js'
import { applyWorkflows } from './workflows.js'
import { RESEARCHCRAFT_PROMPT } from './prompt.js'
import { seed } from './seed.js'
import { registerKeysSettings } from './settings-keys.js'

export const name = 'dsh-researchcraft'
export const inject = ['tools', 'systemPrompt', 'settings']

export function apply(ctx) {
  seed()
  registerKeysSettings(ctx)
  ctx.systemPrompt.section({
    name: 'researchcraft',
    order: 20,
    text: RESEARCHCRAFT_PROMPT,
  })
  applyNotebook(ctx)
  applyImageGenerate(ctx)
  applySciInspect(ctx)
  applyLatexCompile(ctx)
  applyModalRun(ctx)
  applyRunpodRun(ctx)
  applyWorkflows(ctx)
}
