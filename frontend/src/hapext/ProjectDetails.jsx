// The mandatory project-details block that heads the downloaded schedule.
// Ported from hap_converter/ui/project_details_dialog.py — all 8 fields plus
// the company logo are required before a download is allowed.

import { useState } from 'react'
import { Modal } from '../components.jsx'

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

export default function ProjectDetails({ initial, initialLogo, onSave, onClose }) {
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
    if (!logo) missing.unshift('Company Logo')
    if (missing.length) {
      setError(`Please fill: ${missing.join(', ')}`)
      return
    }
    const details = {}
    PROJECT_FIELDS.forEach(([key]) => { details[key] = String(values[key] || '').trim() })
    details.date = toDisplayDate(values.dateIso)
    onSave(details, logo, { ...values })
  }

  return (
    <Modal title="Project details" onClose={onClose} width={520}>
      <p className="muted" style={{ marginTop: 0 }}>
        These details head the downloaded schedule (FCU schedule format).
        All fields are mandatory. The logo is placed in the sheet header.
      </p>

      <div style={{ marginBottom: 12 }}>
        <label className="field">Company Logo:</label>
        <div className="row">
          <div style={{
            width: 90, height: 34, border: '1px solid var(--border)', borderRadius: 6,
            background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
          }}>
            {logo && <img src={URL.createObjectURL(logo)} alt="" style={{ maxWidth: 88, maxHeight: 32 }} />}
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
