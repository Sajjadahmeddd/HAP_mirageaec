// Engineering Tools' client. Thin fetch wrappers: every call maps to one
// endpoint that wraps one engine function — no logic lives here.
//
// Sign-in and the admin API are NOT here and never were: they belong to
// MAEC One Core, which is now a separate service. This name used to be
// imported from Core's client — the one thing the product borrowed from it.
// That client left with Core, so the name is defined here.
//
// A 401 now means the token behind this browser's session has expired —
// Core mints them for fifteen minutes. Because Core's own session cookie
// usually outlives that, sending the browser to /auth/login gets a fresh
// token and comes straight back with no sign-in screen shown.

export const SESSION_EXPIRED = 'maec:session-expired'

// One re-authorization per visit. The redirect reloads the page, so a plain
// variable would forget it had happened and the next 401 would redirect
// again — and if the fresh token is refused too (a revoked seat, a suspended
// organisation), that is a loop between two services with the user watching
// it flicker. sessionStorage survives the redirect; a successful call clears
// it, so a later expiry is free to re-authorize once more.
const REAUTH_MARK = 'maec:reauthorizing'

/** Send the browser to Core for a fresh token. False if we already tried. */
export function reauthorize() {
  try {
    if (sessionStorage.getItem(REAUTH_MARK)) return false
    sessionStorage.setItem(REAUTH_MARK, String(Date.now()))
  } catch { /* private mode: fall through and redirect once */ }
  window.location.assign('/auth/login')
  return true
}

/** Called when a request succeeds: the round trip worked, so allow another
 *  re-authorization the next time one is needed. */
export function reauthorizationWorked() {
  try { sessionStorage.removeItem(REAUTH_MARK) } catch { /* nothing to clear */ }
}

function checkAuth(response) {
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent(SESSION_EXPIRED))
    if (reauthorize()) {
      throw new Error('Your session expired — signing you in again…')
    }
    throw new Error(
      'Your session expired and signing in again did not work. '
      + 'You may no longer have access to Engineering Tools.')
  }
}

async function asJson(response) {
  checkAuth(response)
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch { /* non-JSON error body */ }
    throw new Error(detail)
  }
  return response.json()
}

// A file download: the server streams the built file back, and the browser
// saves it under the filename in Content-Disposition.
async function download(response, fallbackName) {
  checkAuth(response)
  if (!response.ok) {
    let detail = `Download failed (${response.status})`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch { /* non-JSON error body */ }
    throw new Error(detail)
  }
  const disposition = response.headers.get('content-disposition') || ''
  const match = /filename\*?=(?:utf-8'')?"?([^";]+)"?/i.exec(disposition)
  const name = match ? decodeURIComponent(match[1]) : fallbackName
  saveBlob(await response.blob(), name)
  return name
}

export function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function base64ToBlob(b64, type) {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return new Blob([bytes], { type })
}


// -------------------------------------------------------------------- auth
export const auth = {
  /** Who this browser is, or null when it is nobody.
   *
   *  Deliberately not routed through checkAuth: this is the question "am I
   *  signed in?", and a 401 is one of its two valid answers, not a failure
   *  that should redirect on its own. The caller decides what to do about it.
   */
  async me() {
    const response = await fetch('/api/auth/me')
    if (response.status === 401) return null
    if (!response.ok) throw new Error(`Could not read the session (${response.status})`)
    reauthorizationWorked()
    return response.json()
  },
  logout() {
    return fetch('/api/auth/logout', { method: 'POST' }).then(asJson)
  },
}

// ------------------------------------------------------------------ HAPExt
export const hapext = {
  inspect(file) {
    const form = new FormData()
    form.append('pdf', file)
    return fetch('/api/hapext/inspect', { method: 'POST', body: form }).then(asJson)
  },
  convert(file) {
    const form = new FormData()
    form.append('pdf', file)
    return fetch('/api/hapext/convert', { method: 'POST', body: form }).then(asJson)
  },
  download({ header, rows, baseName, details, logo, fmt }) {
    const form = new FormData()
    form.append('payload', JSON.stringify({ header, rows, base_name: baseName }))
    form.append('details', JSON.stringify(details))
    form.append('fmt', fmt)
    if (logo) form.append('logo', logo)
    return fetch('/api/hapext/download', { method: 'POST', body: form })
      .then((r) => download(r, `${baseName}.${fmt}`))
  },
  inspectSchedule(file) {
    const form = new FormData()
    form.append('xlsx', file)
    return fetch('/api/hapext/inspect-schedule', { method: 'POST', body: form }).then(asJson)
  },
  changeRequest(xlsxFile, pdfFile) {
    const form = new FormData()
    form.append('xlsx', xlsxFile)
    form.append('pdf', pdfFile)
    return fetch('/api/hapext/change-request', { method: 'POST', body: form }).then(asJson)
  },
}

// -------------------------------------------------------------- AirSizer Pro
export const airsizer = {
  config() {
    return fetch('/api/airsizer/config').then(asJson)
  },
  load(file) {
    const form = new FormData()
    form.append('schedule', file)
    return fetch('/api/airsizer/load', { method: 'POST', body: form }).then(asJson)
  },
  loadRows(payload) {
    return fetch('/api/airsizer/load-rows', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(asJson)
  },
  size(space, diffuser, values) {
    return fetch('/api/airsizer/size', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ space, diffuser, values }),
    }).then(asJson)
  },
  export(payload) {
    const form = new FormData()
    form.append('payload', JSON.stringify(payload))
    return fetch('/api/airsizer/export', { method: 'POST', body: form })
      .then((r) => download(r, `${payload.base_name} - sized.xlsx`))
  },
}

// A response that is both a file and a report: the batch summary rides in a
// header so the Export screen can show per-sheet notes without a second call.
async function downloadWithSummary(response, fallbackName, header) {
  checkAuth(response)
  if (!response.ok) {
    let detail = `Rebadging failed (${response.status})`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch { /* the body was the file, not an error */ }
    throw new Error(detail)
  }
  const disposition = response.headers.get('content-disposition') || ''
  const match = /filename\*?=(?:utf-8'')?"?([^";]+)"?/i.exec(disposition)
  const name = match ? decodeURIComponent(match[1]) : fallbackName
  const blob = await response.blob()
  let summary = null
  try { summary = JSON.parse(response.headers.get(header) || 'null') } catch { /* absent */ }
  return { name, blob, summary, size: blob.size }
}

export const rebadge = {
  /** Per-file report: labels found, current values, whether a row is free. */
  validate(files) {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    return fetch('/api/rebadge/validate', { method: 'POST', body: form }).then(asJson)
  },

  /** A PNG of the title block after the real edit, plus any warnings. */
  async preview(file, inputs) {
    const form = new FormData()
    form.append('file', file)
    form.append('payload', JSON.stringify(inputs))
    const response = await fetch('/api/rebadge/preview', { method: 'POST', body: form })
    checkAuth(response)
    if (!response.ok) {
      let detail = `Preview failed (${response.status})`
      try { detail = (await response.json()).detail || detail } catch { /* not JSON */ }
      throw new Error(detail)
    }
    let warnings = []
    try { warnings = JSON.parse(response.headers.get('X-Rebadge-Warnings') || '[]') } catch { /* absent */ }
    return { url: URL.createObjectURL(await response.blob()), warnings }
  },

  /** The rebadged set. Held, not saved: the Export screen offers the download. */
  apply(files, inputs) {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    form.append('payload', JSON.stringify(inputs))
    return fetch('/api/rebadge/apply', { method: 'POST', body: form })
      .then((r) => downloadWithSummary(r, 'Rebadged_Drawings.zip', 'X-Rebadge-Summary'))
  },
}
