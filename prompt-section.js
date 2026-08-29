/**
 * Registers RESEARCHCRAFT_PROMPT as a system-prompt section, mounted as a row
 * inside `presets/researchcraft/agent.cordis.yml` rather than called from
 * `index.js`'s host-level `apply()`. `ctx.systemPrompt.section()` scopes to
 * whatever context registers it (the same scope-only mechanism
 * `@deepseek-ai/dsh-persona` relies on) — called from a preset row, the
 * section is visible only to sessions joined to that preset. Called from the
 * plugin's bundle-level apply() (as it originally was) it registers globally
 * instead, so every session on every preset got the ResearchCraft persona and
 * tool guidance even in Standard/PTC/Minimal/Creator mode.
 */
import { RESEARCHCRAFT_PROMPT } from './prompt.js'

export const name = 'dsh-researchcraft-prompt-section'
export const inject = ['systemPrompt']

export function apply(ctx) {
  ctx.systemPrompt.section({
    name: 'researchcraft',
    order: 20,
    text: RESEARCHCRAFT_PROMPT,
  })
}
