#!/usr/bin/env node
/* check-ui.mjs — the v0.19.0 dependency rule, mechanically.
 *
 *   ui.jsx  <-  kit.jsx  <-  views
 *
 * ui.jsx owns every visual primitive and imports nothing from the app.
 * kit.jsx holds domain helpers and stage-aware compositions, never a primitive.
 * A view may not re-define what ui.jsx already exports.
 *
 * Prose contracts drift; this one fails the build. Run standalone or via
 * `make check`; tests/test_ui_contract.py asserts it also catches a planted
 * violation, because a checker with no negative test is decoration.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join, basename, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..', 'src')
const root = process.argv[2] ? process.argv[2] : SRC

const NON_VIEW = new Set(['ui.jsx', 'kit.jsx', 'main.jsx'])
const read = f => readFileSync(join(root, f), 'utf8')
const files = readdirSync(root).filter(f => f.endsWith('.jsx'))
const views = files.filter(f => !NON_VIEW.has(f))

const exportsOf = src => [...src.matchAll(/export function (\w+)/g)].map(m => m[1])
const uiExports = new Set(files.includes('ui.jsx') ? exportsOf(read('ui.jsx')) : [])

const problems = []
const fail = (file, rule, detail) => problems.push({ file, rule, detail })

// 1. a view may not re-define a ui primitive
for (const f of views) {
  for (const name of exportsOf(read(f))) {
    if (uiExports.has(name)) fail(f, 'redefines-primitive', `exports ${name}, which ui.jsx already exports`)
  }
}

// 2. kit.jsx may not export a visual primitive
if (files.includes('kit.jsx')) {
  for (const name of exportsOf(read('kit.jsx'))) {
    if (uiExports.has(name)) fail('kit.jsx', 'kit-owns-primitive', `exports ${name}; primitives live in ui.jsx`)
  }
}

// 3. no hand-rolled loading text outside the primitive
for (const f of files) {
  if (f === 'ui.jsx') continue
  const src = read(f)
  src.split('\n').forEach((line, i) => {
    if (/\bloading\s*…/i.test(line) && !line.trimStart().startsWith('//') && !line.trimStart().startsWith('*'))
      fail(f, 'hand-rolled-loading', `line ${i + 1}: use <Loading /> instead`)
  })
}

// 4. colour literals belong to the stylesheet, not to components
for (const f of files) {
  const src = read(f)
  src.split('\n').forEach((line, i) => {
    const code = line.split('//')[0]           // strip trailing comments, not the whole line
    const m = code.match(/#[0-9a-fA-F]{3,8}\b|oklch\(|rgba?\(/)
    if (m) fail(f, 'raw-colour', `line ${i + 1}: ${m[0]} — use a token`)
  })
}

// 5. raw font sizes bypass the six-step scale.
//    A RATCHET, not a gate: 43 sites remain that have no exact scale equivalent
//    (10px sits below --text-micro; 13px falls between --text-meta and --text-body),
//    so converting them is a visual decision, not a mechanical one. The count may
//    only fall. Lower BASELINE whenever you retire some; never raise it.
const BASELINE = 43
const rawSizes = []
for (const f of files) {
  read(f).split('\n').forEach((line, i) => {
    const m = line.match(/text-\[\d+(px|rem)\]/)
    if (m) rawSizes.push(`${f}:${i + 1} ${m[0]}`)
  })
}
if (rawSizes.length > BASELINE) {
  fail('(ratchet)', 'raw-font-size',
    `${rawSizes.length} raw font sizes, baseline is ${BASELINE} — new ones added:\n      ` +
    rawSizes.slice(BASELINE).join('\n      '))
}

// 6. the primitive layer stays pure: no network, no upward imports
if (files.includes('ui.jsx')) {
  const src = read('ui.jsx')
  if (/\bfetch\(/.test(src)) fail('ui.jsx', 'ui-impure', 'contains fetch( — primitives take props, not data')
  for (const m of src.matchAll(/from '\.\/(\w[\w-]*)'/g)) {
    if (m[1] !== 'react') fail('ui.jsx', 'ui-imports-app', `imports ./${m[1]} — ui.jsx must sit at the bottom`)
  }
}

if (problems.length) {
  console.error(`check-ui: ${problems.length} violation${problems.length > 1 ? 's' : ''}\n`)
  for (const p of problems) console.error(`  ${p.file}  [${p.rule}]  ${p.detail}`)
  console.error('\nSee docs/cycles/GOAL PROMPT — The Face §7.')
  process.exit(1)
}
console.log(`check-ui: clean (${views.length} views, ${uiExports.size} primitives)`)
