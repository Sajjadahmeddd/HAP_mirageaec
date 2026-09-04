// The mandatory project-details block that heads the downloaded schedule.
// Ported from hap_converter/ui/project_details_dialog.py — all 8 fields plus
// the client's logo are required before a download is allowed. The logo is
// the client's own: these schedules are issued to them, so it heads the
// sheet rather than MAEC's mark.

import { useState } from 'react'
import { Modal } from './components.jsx'

export const PROJECT_FIELDS = [
  ['project', 'Project:'],
  ['project_no', 'Project No:'],
  ['stage', 'Stage:'],
  ['discipline', 'Discipline:'],
  ['author', 'Author:'],
  ['checked', 'Checked:'],
  ['revision', 'Revision:'],
  ['date', 'Date:'],
]

const LOGO_TYPES = ['.png', '.jpg', '.jpeg']

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

/** dd.MM.yyyy — the format the desktop writes into the sheet header. */
function toDisplayDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

/** Where to point an <img> at a logo, whether it was picked here as a File
 *  or imported out of a schedule as a data URL. */
export function logoSrc(logo) {
  if (!logo) return ''
  return logo.dataUrl || URL.createObjectURL(logo)
}

/** The same logo as a data URL, which is how the AirSizer export carries it. */
export function logoDataUrl(logo) {
  if (!logo) return Promise.resolve('')
  if (logo.dataUrl) return Promise.resolve(logo.dataUrl)
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => resolve('')
    reader.readAsDataURL(logo)
  })
}

export default function ProjectDetails({ initial, initialLogo, onSave, onClose, onImport }) {
  const [values, setValues] = useState(() => {
    const seed = { ...(initial || {}) }
    if (!seed.dateIso) seed.dateIso = todayIso()
    return seed
  })
  const [logo, setLogo] = useState(initialLogo || null)
  const [error, setError] = useState('')

  const set = (key, value) => setValues((prev) => ({ ...prev, [key]: value }))

  const save = () => {
    const missing = PROJECT_FIELDS
      .filter(([key]) => key !== 'date' && !String(values[key] || '').trim())
      .map(([, label]) => label.replace(':', ''))
    if (!logo) missing.unshift('Client Logo')
    if (missing.length) {
      setError(`Please fill: ${missing.join(', ')}`)
      return
    }
    const details = {}
    PROJECT_FIELDS.forEach(([key]) => { details[key] = String(values[key] || '').trim() })
    details.date = toDisplayDate(values.dateIso)
    onSave(details, logo, { ...values })
  }

  // Fill the form from a schedule that already carries these nine inputs,
  // rather than making an engineer retype what they just uploaded.
  const importFrom = () => {
    const found = onImport?.()
    if (!found) { setError('That schedule carries no project details.'); return }
    const { details, logo: imported } = found
    setValues((prev) => {
      const next = { ...prev }
      // Date is deliberately not imported: it stamps when this schedule is
      // issued, not when the one it was read from was. Today's stands.
      PROJECT_FIELDS
        .filter(([key]) => key !== 'date')
        .forEach(([key]) => { if (details[key]) next[key] = details[key] })
      return next
    })
    if (imported) setLogo(imported)
    setError(imported ? '' : 'Details imported. The schedule had no logo — pick one.')
  }

  return (
    <Modal title="Project details" onClose={onClose} width={520}>
      {onImport && (
        <button type="button" className="btn-import" onClick={importFrom}>
          Import from HAP Excel
        </button>
      )}
      <p className="muted" style={{ marginTop: 0 }}>
        These details head the downloaded schedule (FCU schedule format).
        All fields are mandatory. The logo is placed in the sheet header.
      </p>

      <div style={{ marginBottom: 12 }}>
        <label className="field">Client Logo:</label>
        <div className="row">
          <div style={{
            width: 90, height: 34, border: '1px solid var(--border)', borderRadius: 6,
            background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
          }}>
            {logo && <img src={logoSrc(logo)} alt="" style={{ maxWidth: 88, maxHeight: 32 }} />}
          </div>
          <span className="small grow">{logo ? logo.name : 'No image selected  (PNG / JPG / JPEG)'}</span>
          <label className="btn btn-secondary" style={{ margin: 0 }}>
            Browse…
            <input
              type="file" accept={LOGO_TYPES.join(',')} style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (!file) return
                if (!LOGO_TYPES.some((t) => file.name.toLowerCase().endsWith(t))) {
                  setError('Logo must be a PNG, JPG or JPEG image.')
                  return
                }
                setError('')
                setLogo(file)
              }}
            />
          </label>
        </div>
      </div>

      {PROJECT_FIELDS.filter(([key]) => key !== 'date').map(([key, label]) => (
        <div key={key} style={{ marginBottom: 10 }}>
          <label className="field">{label}</label>
          <input
            type="text" value={values[key] || ''} placeholder={label.replace(':', '')}
            onChange={(e) => set(key, e.target.value)}
          />
        </div>
      ))}

      <div style={{ marginBottom: 10 }}>
        <label className="field">Date:</label>
        <input type="date" value={values.dateIso || ''} onChange={(e) => set('dateIso', e.target.value)} />
      </div>

      {error && <div className="status-fail" style={{ marginBottom: 10 }}>{error}</div>}

      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save}>Save</button>
      </div>
    </Modal>
  )
}
