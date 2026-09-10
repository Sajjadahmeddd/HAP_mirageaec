// Engineering Tools' screens, and the address each one has.
//
// The product keeps its page-state machine — a screen is still an id like
// 'hap-result', and every `ctx.setPage('...')` call around the app is
// unchanged. This table is the translation between that id and the URL, so
// react-router owns the address bar while the machine owns the screen.
//
// MAEC One Core's own addresses (/, /home, /admin/*) are not here: they
// belong to Core, and are routed in App.jsx.

/** Screen id -> the path that shows it. */
export const PATHS = {
  'hap-home': '/hapext',
  'hap-upload': '/hapext/upload',
  'hap-convert': '/hapext/converting',
  'hap-result': '/hapext/schedule',
  'hap-failure': '/hapext/unreadable',
  'hap-change': '/hapext/change-request',
  'hap-change-review': '/hapext/change-request/review',

  'air-home': '/airsizer',
  'air-upload': '/airsizer/upload',
  'air-wizard': '/airsizer/sizing',
  'air-review': '/airsizer/results',

  'rebadge-home': '/pdf-rebadging',
  'rebadge-wizard': '/pdf-rebadging/project',
}

const PAGE_OF = Object.fromEntries(
  Object.entries(PATHS).map(([page, path]) => [path, page]))

/** Which product tab owns a screen — the tab bar reads this rather than
 *  keeping its own state that could drift out of step with the page. */
export const TAB_OF = {
  'hap-home': 'HAPExt',
  'hap-upload': 'HAPExt',
  'hap-convert': 'HAPExt',
  'hap-result': 'HAPExt',
  'hap-failure': 'HAPExt',
  'hap-change': 'HAPExt',
  'hap-change-review': 'HAPExt',

  'air-home': 'AirSizer Pro',
  'air-upload': 'AirSizer Pro',
  'air-wizard': 'AirSizer Pro',
  'air-review': 'AirSizer Pro',

  'rebadge-home': 'PDF Rebadging',
  'rebadge-wizard': 'PDF Rebadging',
}

/** The screen each tab opens on. */
export const HOME_OF = {
  'HAPExt': 'hap-home',
  'AirSizer Pro': 'air-home',
  'PDF Rebadging': 'rebadge-home',
}

// Nothing is stored server-side, so a converted schedule or a half-finished
// sizing run exists only in memory. Those screens are reachable by Back and
// Forward within a session, but landing on one from a cold URL would render
// an empty shell — so a fresh load is sent to the module's home instead.
export const ENTRY_POINTS = new Set(Object.values(HOME_OF))

export const pathOf = (page) => PATHS[page] || PATHS['hap-home']

/** The screen a path shows, or null when the path is not one of ours. */
export function pageOf(pathname) {
  return PAGE_OF[pathname.replace(/\/+$/, '') || '/'] || null
}

/** True when this path belongs to Engineering Tools at all. */
export const isProductPath = (pathname) => pageOf(pathname) !== null
