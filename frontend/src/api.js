// Thin fetch wrappers. Every call maps to one endpoint that wraps one engine
// function — no logic lives here.

async function asJson(response) {
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
