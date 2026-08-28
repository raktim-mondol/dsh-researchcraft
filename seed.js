import { cpSync, existsSync, mkdirSync, readdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))

function dshHome() {
  return process.env.DSH_HOME || join(homedir(), '.dsh')
}

function copyMissing(src, dest) {
  if (!existsSync(src)) return 0
  mkdirSync(dest, { recursive: true })
  let n = 0
  for (const ent of readdirSync(src, { withFileTypes: true })) {
    if (!ent.isDirectory()) continue
    const from = join(src, ent.name)
    const to = join(dest, ent.name)
    if (existsSync(to)) continue
    if (!existsSync(join(from, 'SKILL.md'))) continue
    cpSync(from, to, { recursive: true })
    n++
  }
  return n
}

/**
 * Install the ResearchCraft agent preset and first-party skills into DSH home.
 * Scientific catalogue skills stay on disk (scientific-agent-skills or a
 * fallback checkout) and are wired through the preset's skill-filesystem row.
 */
export function seed() {
  const home = dshHome()
  const presetDest = join(home, '.agent-presets', 'researchcraft')
  const presetSrc = join(here, 'presets', 'researchcraft')
  mkdirSync(dirname(presetDest), { recursive: true })
  if (!existsSync(join(presetDest, 'agent.cordis.yml'))) {
    cpSync(presetSrc, presetDest, { recursive: true })
  } else {
    // Keep composition current when the plugin is updated.
    cpSync(presetSrc, presetDest, { recursive: true })
  }

  copyMissing(join(here, 'skills'), join(home, 'skills'))
}
