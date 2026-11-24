// Writes the licence notices of everything bundled into world/orbs/shefa-orbs.js beside it
// (all MIT). Run after the orbs build, which empties that folder.
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
const out = new URL('../../src/shefa/static/world/orbs/LICENSES.txt', import.meta.url)
const pkgs = ['react', 'react-dom', 'scheduler', 'voice-ring', 'thinking-orbs']
const parts = pkgs.map((name) => {
  const dir = new URL(`../node_modules/${name}/`, import.meta.url)
  const pkg = JSON.parse(readFileSync(new URL('package.json', dir), 'utf8'))
  const file = ['LICENSE', 'LICENSE.md', 'LICENSE.txt'].map((f) => new URL(f, dir)).find((u) => existsSync(u))
  const text = file ? readFileSync(file, 'utf8').trim() : `${pkg.license} licence (no LICENSE file in the package)`
  return `${pkg.name} ${pkg.version} (${pkg.license})\n\n${text}`
})
writeFileSync(out, `shefa-orbs.js bundles the following packages.\n\n${parts.join('\n\n' + '-'.repeat(72) + '\n\n')}\n`)
console.log(`wrote ${out.pathname}`)
