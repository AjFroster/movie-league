/** Fails if a className used in JSX has no rule in styles.css.
 *
 *  Exists because a rebase's auto-merge silently deleted an entire block of rules from
 *  styles.css -- no conflict, no build error, and CI stayed green because a bundler does
 *  not care whether your CSS is complete. The component rendered as an unstyled browser
 *  button and nothing said a word.
 *
 *  Only static class names are checked. A name assembled at runtime cannot be resolved
 *  here, and guessing would trade a real signal for false alarms.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

// Classes with no rule today, and deliberately so: markup hooks and dead leftovers. A NEW
// name appearing here is the signal -- shrink this list when you delete one, never grow it
// to silence a failure.
const KNOWN_UNSTYLED = new Set([
  'clock-main', 'create-form', 'create-header', 'reject-actions', 'setup-main', 'snake',
])

function walk(dir) {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry)
    return statSync(path).isDirectory() ? walk(path) : [path]
  })
}

const css = readFileSync('src/styles.css', 'utf8')
const defined = new Set([...css.matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1]))

const used = new Set()
for (const file of walk('src').filter((f) => f.endsWith('.jsx'))) {
  const text = readFileSync(file, 'utf8')
  for (const m of text.matchAll(/className="([^"{}]+)"/g)) {
    m[1].split(/\s+/).forEach((c) => c && used.add(c))
  }
  // Template literals: drop the ${...} holes and keep the literal parts.
  for (const m of text.matchAll(/className=\{`([^`]*)`\}/g)) {
    m[1].split(/\$\{[^}]*\}/).forEach((part) =>
      part.split(/\s+/).forEach((c) => c && used.add(c)))
  }
}

const missing = [...used].filter((c) => !defined.has(c) && !KNOWN_UNSTYLED.has(c)).sort()

if (missing.length > 0) {
  console.error(`\nclassName with no rule in styles.css (${missing.length}):`)
  for (const c of missing) console.error(`  .${c}`)
  console.error('\nEither the rule was lost -- check a recent merge or rebase -- or the')
  console.error('class is intentionally unstyled, in which case add it to KNOWN_UNSTYLED.')
  process.exit(1)
}

console.log(`CSS coverage ok: ${used.size} class names, all styled or known-unstyled.`)
