// The address bar is the app's navigation state.
//
// Every screen used to be a value in React state, which meant one URL for the
// whole app: nothing could be linked to, refreshing always landed on the
// HAPExt home screen, and the browser's Back button left the site entirely
// because there was no history to go back through. Each screen now has a path,
// and `App` pushes one whenever it moves.
//
// The backend already serves index.html for every non-API path (see the `spa`
// route in backend/main.py), so these paths survive a refresh and a pasted
// link without any server change.

export const LOGIN = '/'
export const LAUNCHER = '/home'

/** Screen id -> the path that shows it. Ids are unchanged, so `setPage` still
 *  takes the same strings it always did. */
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
// Forward within a session, but landing on one from a cold URL would render an
// empty shell — so a fresh load is sent to the module's home screen instead.
export const ENTRY_POINTS = new Set(Object.values(HOME_OF))

export const pathOf = (page) => PATHS[page] || PATHS['hap-home']

/** What a path means, or `null` if it is not one of ours. */
export function resolve(pathname) {
  const clean = pathname.replace(/\/+$/, '') || '/'
  if (clean === LAUNCHER) return { opened: false, page: HOME_OF['HAPExt'] }
  const page = PAGE_OF[clean]
  return page ? { opened: true, page } : null
}

/** Where a cold load of `pathname` should actually start. */
export function landing(pathname) {
  const found = resolve(pathname)
  if (!found) return { opened: false, page: HOME_OF['HAPExt'] }
  if (found.opened && !ENTRY_POINTS.has(found.page)) {
    return { opened: true, page: HOME_OF[TAB_OF[found.page]] }
  }
  return found
}
