// Recent Projects, held in the browser.
//
// Isolation is the browser's job, not ours: localStorage is scoped to this
// origin *and* this browser profile, so one engineer's history is physically
// unreadable by another. The server never sees any of it, which is why this
// needs no login and no database.
//
// This mirrors what the desktop app already does — %APPDATA%\MAEC\
// recent_projects.json is per-machine too, and never followed anyone between
// PCs. Same behaviour, same limitation.
//
// A full sizing session from a 212-page report measures ~146 KB (813 rows +
// 601 sizings), and localStorage gives ~5 MB, so MAX_ENTRIES is set well
// inside the budget and the oldest entry is evicted if a write ever overruns.

const KEY = 'maec.recents.v1'
const MAX_ENTRIES = 10

export const HAPEXT = 'hapext'
export const AIRSIZER = 'airsizer'
export const REBADGE = 'rebadge'

// Every module that keeps history. This list is the only place that needs to
// know: the store, the readers and the quota shedding all work off it, so a
// fourth module is one line rather than three functions to remember.
const MODULES = [HAPEXT, AIRSIZER, REBADGE]

const empty = () => Object.fromEntries(MODULES.map((module) => [module, []]))

/** Every read is guarded: private-browsing mode throws on access. */
function readAll() {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return empty()
    const parsed = JSON.parse(raw)
    const store = empty()
    MODULES.forEach((module) => {
      if (Array.isArray(parsed[module])) store[module] = parsed[module]
    })
    return store
  } catch {
    return empty()                            // missing, corrupt, or blocked
  }
}

/**
 * Persist, shedding the oldest entries if the quota is hit rather than
 * losing the save outright.
 */
function writeAll(store) {
  for (let attempt = 0; attempt < MAX_ENTRIES; attempt += 1) {
    try {
      localStorage.setItem(KEY, JSON.stringify(store))
      return true
    } catch (err) {
      const longest = [...MODULES]
        .sort((a, b) => store[b].length - store[a].length)[0]
      if (!store[longest].length) return false      // nothing left to shed
      store[longest] = store[longest].slice(0, -1)  // drop the oldest
    }
  }
  return false
}

export function isAvailable() {
  try {
    const probe = `${KEY}.probe`
    localStorage.setItem(probe, '1')
    localStorage.removeItem(probe)
    return true
  } catch {
    return false
  }
}

export function list(module) {
  return readAll()[module] || []
}

/**
 * Add an entry, newest first. `payload` is whatever `open` needs to restore
 * the session without asking for the file again.
 */
export function save(module, { name, summary, payload }) {
  const store = readAll()
  const entry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name,
    summary,
    saved: new Date().toISOString(),
    payload,
  }
  // one entry per source name: re-converting the same report replaces it
  store[module] = [entry, ...store[module].filter((e) => e.name !== name)]
    .slice(0, MAX_ENTRIES)
  writeAll(store)
  return entry
}

export function remove(module, id) {
  const store = readAll()
  store[module] = store[module].filter((e) => e.id !== id)
  writeAll(store)
}

export function clear(module) {
  const store = readAll()
  store[module] = []
  writeAll(store)
}

/** "29 Aug 2026 • 14:32" — short enough for the panel row. */
export function formatWhen(iso) {
  if (!iso) return ''
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ''
  return `${at.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })} • ${
    at.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`
}
