// HAPExt converting screen — file card, progress, and the Conversion Status
// side panel from convert_page.py.
//
// The desktop drove the bar from the engine's per-page progress_cb. A single
// synchronous request cannot stream that, so the bar animates while the
// request is in flight and snaps to 100% on the response (§7 of the brief).
// A 212-page report parses in well under a second server-side.

import { useEffect, useRef, useState } from 'react'
import { hapext } from '../api'
import { INFO_CARDS, InfoCard, PdfBadge, StepTimeline, formatMb } from '../components.jsx'

const STEPS = ['File uploaded', 'Extracting data', 'Generate CSV']

export default function Convert({ ctx }) {
  const [percent, setPercent] = useState(0)
  const [status, setStatus] = useState('Preparing…')
  const started = useRef(false)

  useEffect(() => {
    if (started.current || !ctx.pdf) return
    started.current = true

    // creep towards 90% so the bar reads as live; the response finishes it
    const timer = setInterval(() => setPercent((p) => (p < 90 ? p + Math.max(1, (90 - p) / 12) : p)), 120)
    setStatus(`Parsing ${ctx.pdf.pages} pages…`)

    hapext.convert(ctx.pdf.file)
      .then((data) => {
        clearInterval(timer)
        setPercent(100)
        ctx.setConversion(data)
        if (data.ok) ctx.rememberConversion(data)   // browser-local history
        ctx.setPage(data.ok ? 'hap-result' : 'hap-failure')
      })
      .catch((err) => {
        clearInterval(timer)
        ctx.setConversion({ ok: false, issues: [{ page: 0, field: 'file', description: err.message }], stats: {} })
        ctx.setPage('hap-failure')
      })

    return () => clearInterval(timer)
  }, [ctx])

  if (!ctx.pdf) {
    return <div className="muted">No PDF selected. <button className="btn-ghost" onClick={() => ctx.setPage('hap-upload')}>Go back</button></div>
  }

  return (
    <div className="split">
      <div className="card" style={{ padding: '20px 24px' }}>
        <div className="row" style={{ gap: 16 }}>
          <PdfBadge size={56} />
          <div className="grow">
            <div className="h2">{ctx.pdf.name}</div>
            <div className="small">{formatMb(ctx.pdf.size)} • Uploaded just now</div>
          </div>
          <div className="col">
            <button className="btn" style={{ background: '#D8D8D3', color: '#6B6E78', border: 'none', fontWeight: 700 }} disabled>
              Processing…
            </button>
          </div>
        </div>

        <div className="row" style={{ marginTop: 20 }}>
          <h2 className="h2 grow">Converting PDF to CSV</h2>
          <span className="status-ok">{Math.round(percent)}%</span>
        </div>
        <div className="progress" style={{ margin: '8px 0' }}>
          <div style={{ width: `${percent}%` }} />
        </div>
        <div className="row">
          <span className="muted grow">{status}</span>
          <span className="chip">OUTPUT: CSV</span>
        </div>

        <div className="row" style={{ marginTop: 24, gap: 14, alignItems: 'stretch' }}>
          {INFO_CARDS.map(([t, b]) => <InfoCard key={t} title={t} body={b} />)}
        </div>
      </div>

      <div className="panel-card" style={{ padding: '18px 20px' }}>
        <h2 className="h2">Conversion Status</h2>
        <div className="small" style={{ margin: '10px 0 6px' }}>Current file</div>
        <div className="card row" style={{ padding: '12px 14px', marginBottom: 16 }}>
          <PdfBadge size={38} />
          <div>
            <div className="recent-name">{ctx.pdf.name}</div>
            <div className="small">Converting to .csv</div>
          </div>
        </div>
        <StepTimeline steps={STEPS} current={percent >= 100 ? 3 : 2} />
        <div className="small" style={{ marginTop: 16 }}>You can continue working while we process.</div>
      </div>
    </div>
  )
}
