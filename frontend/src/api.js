// Engineering Tools' client. Thin fetch wrappers: every call maps to one
// endpoint that wraps one engine function — no logic lives here.
//
// Signing in and out are NOT here: they happen at MAEC One Core. On every
// request the server asks Core about the browser's MAEC One cookie. An API
// 401 means Core no longer knows this browser (signed out, or the session
// ended), and its body carries `login_url`: Core's sign-in, coming back here.

export const SESSION_EXPIRED = 'maec:session-expired'

// One trip to sign-in per visit. The trip reloads the page, so a plain
// variable would forget it had happened, and if the next answer is a 401 too
// that is a loop between two services with the user watching it flicker.
// sessionStorage survives the trip; a successful /api/auth/me clears it, so a
// later sign-out is free to send the window to sign-in once more.
const REAUTH_MARK = 'maec:reauthorizing'

/** Send the window to MAEC One's sign-in. False if we already tried. */
export function reauthorize(loginUrl) {
  try {
    if (sessionStorage.getItem(REAUTH_MARK)) return false
    sessionStorage.setItem(REAUTH_MARK, String(Date.now()))
  } catch { /* private mode: fall through and go once */ }
  // Without a login_url, reloading the page lets the server's gate send the
  // browser to sign-in itself.
  window.location.assign(loginUrl || window.location.href)
  return true
}

/** Called when /api/auth/me succeeds: the trip worked, so allow another. */
export function reauthorizationWorked() {
  try { sessionStorage.removeItem(REAUTH_MARK) } catch { /* nothing to clear */ }
}

async function readJson(response) {
  try { return await response.clone().json() } catch { return {} }
}

// What a refusal says to a person, from Core's `reason` or the API's `detail`.
const REASONS = {
  no_access: 'Your account does not have access to Engineering Tools.',
  org_suspended: "Your organisation's access to MAEC One is suspended.",
  bad_origin: 'This request did not come from Engineering Tools itself.',
  bad_app: 'Engineering Tools is not set up correctly with MAEC One.',
}

function reasonText(body) {
  return body.detail || REASONS[body.reason]
    || (body.reason ? `MAEC One refused access (${body.reason}).` : '')
}

async function checkAuth(response) {
  if (response.status !== 401) return
  const body = await readJson(response)
  window.dispatchEvent(new CustomEvent(SESSION_EXPIRED))
  if (reauthorize(body.login_url)) {
    throw new Error('You are signed out — taking you to MAEC One to sign in…')
  }
  throw new Error(
    'You are signed out, and signing in again did not bring you back. '
    + 'Open MAEC One and sign in there.')
}

async function asJson(response) {
  await checkAuth(response)
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    detail = reasonText(await readJson(response)) || detail
    throw new Error(detail)
  }
  return response.json()
}

// A file download: the server streams the built file back, and the browser
// saves it under the filename in Content-Disposition.
async function download(response, fallbackName) {
  await checkAuth(response)
  if (!response.ok) {
    let detail = `Download failed (${response.status})`
    detail = reasonText(await readJson(response)) || detail
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
  /** Who this browser is, or {authenticated: false, login_url} when MAEC One
   *  does not know it.
   *
   *  Deliberately not routed through checkAuth: this is the question "am I
   *  signed in?", and a 401 is one of its two valid answers, not a failure
   *  that should leave the page on its own. The caller decides.
   */
  async me() {
    const response = await fetch('/api/auth/me')
    if (response.status === 401) {
      const body = await readJson(response)
      return { authenticated: false, login_url: body.login_url }
    }
    if (!response.ok) {
      const body = await readJson(response)
      throw new Error(reasonText(body) || `Could not read the session (${response.status})`)
    }
    reauthorizationWorked()
    return response.json()
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
  await checkAuth(response)
  if (!response.ok) {
    let detail = `Rebadging failed (${response.status})`
    detail = reasonText(await readJson(response)) || detail
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
    await checkAuth(response)
    if (!response.ok) {
      let detail = `Preview failed (${response.status})`
      detail = reasonText(await readJson(response)) || detail
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
