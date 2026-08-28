// Shared building blocks, ported from hap_converter/ui/widgets.py and
// hap_converter/airsizer/ui/widgets.py.

import { useEffect, useRef, useState } from 'react'

export function PdfBadge({ size = 40 }) {
  return (
    <span className="pdf-badge" style={{ width: size, height: size, fontSize: Math.max(8, size / 4.5) }}>
      PDF
    </span>
  )
}

export function InfoCard({ title, body }) {
  return (
    <div className="info-card grow">
      <h4>{title}</h4>
      <p>{body}</p>
    </div>
  )
}

export const INFO_CARDS = [
  ['Fast & Accurate', 'Extract data with high precision'],
  ['Secure', 'Your data is safe with us'],
  ['Smart Workflow', 'Streamline your AEC process'],
]

/** Drag-and-drop + browse, matching the desktop DropZone's three states. */
export function DropZone({ accept, prompt, hint, onFile, file, meta, error, compact }) {
  const input = useRef(null)
  const [active, setActive] = useState(false)

  const accepts = (name) => accept.some((s) => name.toLowerCase().endsWith(s))

  const onDrop = (event) => {
    event.preventDefault()
    setActive(false)
    const dropped = event.dataTransfer.files?.[0]
    if (dropped && accepts(dropped.name)) onFile(dropped)
  }

  return (
    <div
      className={`dropzone${active ? ' active' : ''}${error ? ' error' : ''}${compact ? ' small' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setActive(true) }}
      onDragLeave={() => setActive(false)}
      onDrop={onDrop}
    >
      {!compact && <PdfBadge size={52} />}
      <div className="h2">{file ? file.name : prompt}</div>
      <div className="muted">{file ? meta : 'or'}</div>
      <button className="btn btn-secondary" onClick={() => input.current?.click()}>Browse</button>
      <div className={error ? 'status-fail' : 'small'}>{error || hint}</div>
      <input
        ref={input}
        type="file"
        accept={accept.join(',')}
        style={{ display: 'none' }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = '' }}
      />
    </div>
  )
}

/** Vertical 3/4-step timeline with a failure state (HAPExt side panel). */
export function StepTimeline({ steps, current, failedStep, caption }) {
  return (
    <div className="timeline">
      {steps.map((text, index) => {
        const number = index + 1
        let state = 'pending'
        if (failedStep) {
          if (number < failedStep) state = 'done'
          else if (number === failedStep) state = 'fail'
        } else if (number <= current) state = 'done'
        return (
          <div key={text}>
            {index > 0 && <div className="connector" />}
            <div className="step">
              <span className={`dot ${state}`}>
                {state === 'done' ? '✓' : state === 'fail' ? '✕' : number}
              </span>
              <div>
                <div className="h2">{text}</div>
                {state === 'fail' && caption && <div className="step-caption">{caption}</div>}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** The AirSizer four-step wizard bar. */
export function StepChips({ steps, current }) {
  return (
    <div className="chips">
      {steps.map((text, index) => (
        <div key={text} style={{ display: 'contents' }}>
          {index > 0 && <span className="line" />}
          <span className={`wchip${index + 1 === current ? ' active' : index + 1 < current ? ' done' : ''}`}>
            {index + 1} {text}
          </span>
        </div>
      ))}
    </div>
  )
}

export function SummaryStrip({ items }) {
  return (
    <div className="summary">
      {items.map(([key, value, tone]) => (
        <div key={key}>
          <div className="key">{key}</div>
          <div className={tone === 'ok' ? 'status-ok' : 'val'}>{value}</div>
        </div>
      ))}
    </div>
  )
}

/**
 * Read-only preview table. `rowClass` tints a row (sized / interpolated /
 * failed / new-row) and `indent` steps subspace names in under their unit,
 * both mirroring the desktop tables.
 */
export function PreviewTable({ header, rows, rowClass, isUnit, actions, actionHeader }) {
  return (
    <div className="table-wrap grow">
      <table className="grid">
        <thead>
          <tr>
            {header.map((h, i) => <th key={`${h}-${i}`}>{h}</th>)}
            {actions && <th>{actionHeader || 'Sizing'}</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => {
            const unit = isUnit ? isUnit(r) : false
            return (
              <tr key={r} className={`${unit ? 'unit ' : ''}${rowClass ? rowClass(r) : ''}`}>
                {row.map((value, c) => (
                  <td
                    key={c}
                    className={`${!value ? 'blank' : ''}${c === 0 && !unit ? ' indent' : ''}`}
                  >
                    {value || (unit ? '' : '—')}
                  </td>
                ))}
                {actions && <td>{actions(r)}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function Modal({ title, children, onClose, width = 520 }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.() }}>
      <div className="modal" style={{ width }} onMouseDown={(e) => e.stopPropagation()}>
        {title && <h2 className="h2" style={{ marginBottom: 12 }}>{title}</h2>}
        {children}
      </div>
    </div>
  )
}

export function Spinner({ label = 'Working…' }) {
  return <div className="muted">{label}</div>
}

export function formatMb(bytes) {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
