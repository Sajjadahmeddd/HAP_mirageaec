// Thin fetch wrappers. Every call maps to one endpoint that wraps one engine
// function — no logic lives here.

// A 401 means the session lapsed mid-use. Tell the shell so it can drop back
// to the login screen rather than surfacing a confusing error on the page.
export const SESSION_EXPIRED = 'maec:session-expired'

function checkAuth(response) {
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent(SESSION_EXPIRED))
    throw new Error('Your session has expired. Please sign in again.')
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

// A file the server built: its bytes, or the server's reason it could not.
async function fileFrom(response) {
  checkAuth(response)
  if (!response.ok) {
    let detail = `Download failed (${response.status})`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch { /* non-JSON error body */ }
    throw new Error(detail)
  }
  return response.blob()
}

// ------------------------------------------------------------ saving files
// EVERY download in this app goes through saveFile. The person chooses where
// the file lands, in the browser's own Save As dialog, which opens on their
// Downloads folder — they can keep it or pick anywhere else. This is a
// standing rule for new modules too; tests/test_frontend_downloads.py fails
// if a component downloads any other way.
//
// Order matters: the dialog opens FIRST, and only then is the file produced.
// Chrome lets a page open the dialog only in direct response to a click, and
// that permission lapses within seconds — a workbook the server takes longer
// to build would be refused the dialog if it were asked for afterwards.
// Asking first also makes cancelling free: the server is never called for a
// file nobody wants.
//
// Where the dialog cannot open, the file downloads the browser's normal way,
// straight into Downloads:
//   * Firefox and Safari, which do not implement showSaveFilePicker;
//   * any page not served from https:// or localhost — including this app
//     opened by network address, e.g. http://192.168.1.20:8000 — because
//     browsers only offer the API in a secure context.
const SAVE_TYPES = {
  xlsx: ['Excel workbook', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
  csv: ['CSV file', 'text/csv'],
  zip: ['ZIP archive', 'application/zip'],
  pdf: ['PDF document', 'application/pdf'],
}

function saveOptions(name) {
  const ext = name.includes('.') ? name.split('.').pop().toLowerCase() : ''
  const known = SAVE_TYPES[ext]
  return {
    suggestedName: name,
    startIn: 'downloads',
    ...(known && { types: [{ description: known[0], accept: { [known[1]]: [`.${ext}`] } }] }),
  }
}

/**
 * Ask where to save `name`, then produce the file and write it there.
 *
 * `produce` is the Blob itself, or a function returning a promise of it —
 * called only after a location is chosen. Resolves true once saved, or false
 * if the person closed the dialog, which callers treat as nothing having
 * happened rather than as an error. A failure producing the file rejects.
 */
export async function saveFile(name, produce) {
  let handle = null
  if (typeof window.showSaveFilePicker === 'function') {
    try {
      handle = await window.showSaveFilePicker(saveOptions(name))
    } catch (err) {
      if (err?.name === 'AbortError') return false   // they closed the dialog
      handle = null   // refused, e.g. the click's permission lapsed: fall back
    }
  }
  const blob = typeof produce === 'function' ? await produce() : produce
  if (handle) {
    const writable = await handle.createWritable()
    await writable.write(blob)
    await writable.close()
  } else {
    downloadBlob(blob, name)
  }
  return true
}

// The browser's own download, straight into Downloads. Deliberately not
// exported: it is only saveFile's fallback, never a way around the dialog.
function downloadBlob(blob, name) {
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
  me() {
    return fetch('/api/auth/me').then(asJson)
  },
  login(email, password) {
    return fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    }).then(async (response) => {
      if (response.status === 401) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || 'Incorrect email address or password.')
      }
      return asJson(response)
    })
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
  /** Resolves false if the Save As dialog was closed. The name is decided
   *  here, before the server is asked, because the dialog opens first — and
   *  it is the name the server gives the file: `<base_name>.<fmt>`, written
   *  into an empty folder, so never versioned. */
  download({ header, rows, baseName, details, logo, fmt }) {
    return saveFile(`${baseName || 'schedule'}.${fmt}`, () => {
      const form = new FormData()
      form.append('payload', JSON.stringify({ header, rows, base_name: baseName }))
      form.append('details', JSON.stringify(details))
      form.append('fmt', fmt)
      if (logo) form.append('logo', logo)
      return fetch('/api/hapext/download', { method: 'POST', body: form }).then(fileFrom)
    })
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
  /** Resolves false if the Save As dialog was closed. Named up front for the
   *  same reason as hapext.download, matching the server's
   *  `<base_name> - sized.xlsx`.
   *
   *  `payload.logo` may be a promise of the data URL. It is awaited only after
   *  a location is chosen, so reading the image cannot use up the click the
   *  dialog needs. */
  export(payload) {
    const base = payload.base_name || 'air_diffuser_sizing'
    return saveFile(`${base} - sized.xlsx`, async () => {
      const form = new FormData()
      form.append('payload', JSON.stringify({ ...payload, logo: await payload.logo }))
      return fetch('/api/airsizer/export', { method: 'POST', body: form }).then(fileFrom)
    })
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
  /** Per-file report: labels found and the values the sheet carries today. */
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
