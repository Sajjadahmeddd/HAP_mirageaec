// Engineering Tools' client. Thin fetch wrappers: every call maps to one
// endpoint that wraps one engine function — no logic lives here.
//
// Sign-in and the admin API are NOT here. They belong to MAEC One Core, and
// live in maecone/api.js. This file imports one thing from there — the name
// of the session-lapsed event — because the dependency runs that way round:
// the product may lean on Core, never the reverse.

import { SESSION_EXPIRED } from './maecone/api'

export { SESSION_EXPIRED }

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
