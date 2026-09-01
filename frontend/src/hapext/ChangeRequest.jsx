// Change Request — upload the previously generated Excel plus the revised
// PDF, then append the new line items.
// Ported from hap_converter/ui/pages/change_request_page.py.
//
// No project details are collected: the existing workbook's header block and
// embedded logo are carried over untouched by the engine.

import { useState } from 'react'
import { hapext } from '../api'
import { DropZone, StepTimeline, formatMb } from '../components.jsx'

const STEPS = [
  'Previous Excel loaded',
  'Revised PDF extracted',
  'Comparing line items',
  'Generate updated Excel',
]

function UploadCard({ glyph, colour, title, subtitle, prompt, accept, file, meta, ok, onFile, onClear }) {
  return (
    <div className="card grow" style={{ padding: '16px 18px' }}>
      <div className="row" style={{ marginBottom: 12 }}>
        <span style={{
          background: colour, color: '#fff', borderRadius: 10, width: 40, height: 40,
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, fontWeight: 800,
        }}>{glyph}</span>
        <div>
          <div className="h2">{title}</div>
          <div className="small">{subtitle}</div>
        </div>
      </div>

      {file ? (
        <div className="info-card row">
          <div className="grow">
            <div className="recent-name">{file.name}</div>
            <div className="small">{meta}</div>
          </div>
          <span className={ok ? 'pill-ok' : 'pill-fail'}>{ok ? 'READY' : 'PROBLEM'}</span>
          <button className="btn-ghost" onClick={onClear}>Remove</button>
        </div>
      ) : (
        <DropZone accept={accept} prompt={prompt} hint="" onFile={onFile} compact />
      )}
    </div>
  )
}

export default function ChangeRequest({ ctx }) {
  const [xlsx, setXlsx] = useState(null)
  const [xlsxInfo, setXlsxInfo] = useState(null)
  const [pdf, setPdf] = useState(null)
  const [busy, setBusy] = useState(false)
  const [step, setStep] = useState(0)
  const [error, setError] = useState('')

  const loadXlsx = async (file) => {
    setError('')
    setXlsx(file)
    try {
      const info = await hapext.inspectSchedule(file)
      setXlsxInfo(info)
    } catch (err) {
      setXlsxInfo({ ok: false, message: err.message })
    }
  }

  const generate = async () => {
    if (!xlsx || !pdf) return
    setBusy(true)
    setError('')
    setStep(1)
    const creep = setInterval(() => setStep((s) => (s < 3 ? s + 1 : s)), 500)
    try {
      const data = await hapext.changeRequest(xlsx, pdf)
      clearInterval(creep)
      setStep(4)
      ctx.setChangeResult(data)
      if (data.ok) {
        ctx.setPage('hap-change-review')
      } else {
        ctx.setConversion(null)
        ctx.setPage('hap-failure')
      }
    } catch (err) {
      clearInterval(creep)
      setStep(0)
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const ready = !!(xlsx && xlsxInfo?.ok && pdf)

  return (
    <div className="card col" style={{ padding: '18px 24px' }}>
      <div className="radios">
        <label onClick={() => ctx.setPage('hap-upload')}>
          <input type="radio" checked={false} readOnly /> New Project
        </label>
        <label><input type="radio" checked readOnly /> Change Request</label>
      </div>

      <h2 className="h2">Create Change Request</h2>
      <div className="small">
        Upload the previous Excel and the revised PDF. Mirage AEC will append the new line items.
      </div>

      <div className="row" style={{ gap: 18, alignItems: 'stretch' }}>
        <UploadCard
          glyph="▤" colour="#4E8A3A" title="Previous Excel"
          subtitle="Upload the latest approved .xlsx file"
          prompt="Drop the previous Excel here" accept={['.xlsx']}
          file={xlsx}
          ok={xlsxInfo?.ok}
          meta={xlsxInfo?.ok ? `${xlsxInfo.rows} rows • ${xlsxInfo.columns} columns` : (xlsxInfo?.message || 'Checking…')}
          onFile={loadXlsx}
          onClear={() => { setXlsx(null); setXlsxInfo(null) }}
        />
        <UploadCard
          glyph="▦" colour="var(--red)" title="New PDF"
          subtitle="Upload the revised HAP schedule"
          prompt="Drop revised PDF here" accept={['.pdf']}
          file={pdf} ok
          meta={pdf ? `${formatMb(pdf.size)} • revised report` : ''}
          onFile={(f) => { setPdf(f); setError('') }}
          onClear={() => setPdf(null)}
        />
      </div>

      <h2 className="h2">Change Request Settings</h2>
      <div className="row" style={{ gap: 18, alignItems: 'stretch' }}>
        {[
          ['Append new line items', 'Existing records remain unchanged'],
          ['Highlight new records', 'New rows highlighted in the preview'],
        ].map(([t, s]) => (
          <div className="info-card row grow" key={t}>
            <span className="dot done">✓</span>
            <div>
              <h4>{t}</h4>
              <p>{s}</p>
            </div>
          </div>
        ))}
      </div>

      {busy && (
        <div className="panel-card" style={{ padding: '16px 20px' }}>
          <h2 className="h2" style={{ marginBottom: 10 }}>Generating Change Request</h2>
          <StepTimeline steps={STEPS} current={step} />
        </div>
      )}

      {error && <div className="banner-fail">{error}</div>}

      <div className="grow" />

      <div className="info-card row" style={{ background: '#F7F7F4' }}>
        <div className="grow">
          <h4>How it works</h4>
          <p>Compare previous Excel → extract revised PDF → append new line items → highlight changes</p>
        </div>
        <button className="btn btn-primary" disabled={!ready || busy} onClick={generate}>
          {busy ? 'Generating…' : 'Generate New Excel'}
        </button>
      </div>
    </div>
  )
}
