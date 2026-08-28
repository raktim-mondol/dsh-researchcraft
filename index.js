import { applyNotebook } from './notebook.js'
import { applyImageGenerate } from './image-generate.js'
import { RESEARCHCRAFT_PROMPT } from './prompt.js'
import { seed } from './seed.js'

export const name = 'dsh-researchcraft'
export const inject = ['tools', 'systemPrompt']

export function apply(ctx) {
  seed()
  ctx.systemPrompt.section({
    name: 'researchcraft',
    order: 20,
    text: RESEARCHCRAFT_PROMPT,
  })
  applyNotebook(ctx)
  applyImageGenerate(ctx)
}
