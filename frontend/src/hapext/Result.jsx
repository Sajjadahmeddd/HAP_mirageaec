// HAPExt result — preview, summary strip and the download gate.
// Ported from hap_converter/ui/pages/result_page.py.

import { useState } from 'react'
import { airsizer, hapext } from '../api'
import { PreviewTable, SummaryStrip } from '../components.jsx'
import ProjectDetails from './ProjectDetails.jsx'

export default function Result({ ctx }) {
  const [showDetails, setShowDetails] = useState(false)
  const [pendingFormat, setPendingFormat] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState(null)   // keeps the form filled between opens

  const conversion = ctx.conversion
  if (!conversion?.ok) {
    return <div className="muted">Nothing converted yet.</div>
  }

  const { header, rows, stats, source, base_name: baseName } = conversion

  const send = async (fmt, details, logo) => {
    setBusy(true)
    setError('')
    try {
      await hapext.download({ header, rows, baseName, details, logo, fmt })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  // Download is gated on the details block, exactly as on the desktop.
  const requestDownload = (fmt) => {
    if (ctx.details && ctx.logo) {
      send(fmt, ctx.details, ctx.logo)
      return
    }
    setPendingFormat(fmt)
    setShowDetails(true)
  }

  return (
    <div className="card col" style={{ padding: '18px 24px' }}>
      <div className="row">
        <h2 className="h2">Excel Preview</h2>
        <span className="pill-ok">COMPLETED</span>
        <div className="grow" />
        <button className="btn btn-secondary" onClick={() => ctx.setPage('hap-home')}>Home</button>
        <button className="btn btn-secondary" onClick={() => ctx.setPage('hap-upload')}>Convert another PDF</button>
        <button className="btn btn-secondary" onClick={() => setShowDetails(true)}>
          Project Details{ctx.details ? ' ✓' : ''}
        </button>
        {ctx.airConfig && (
          <button
            className="btn btn-secondary"
            title="Carry this schedule straight into AirSizer Pro"
            onClick={async () => {
              try {
                ctx.loadSpaces(await airsizer.loadRows({
                  header, rows, source, base_name: baseName,
                }))
              } catch (err) { setError(err.message) }
            }}
          >
            Size diffusers →
          </button>
        )}
        <button className="btn btn-primary" disabled={busy} onClick={() => requestDownload('xlsx')}>
          {busy ? 'Preparing…' : 'Download'}
        </button>
      </div>

      <div className="small">{source}  →  {baseName}.xlsx</div>

      <SummaryStrip items={[
        ['FILE', `${baseName}.xlsx`],
        ['ROWS', String(stats.rows ?? rows.length)],
        ['COLUMNS', String(header.length)],
        ['SOURCE', source],
        ['STATUS', 'Ready for review', 'ok'],
      ]} />

      <span className="sheet-tab">HAP Zone Sizing Summary</span>
      {/* every row, scrolling inside the card — the engineer reviews the
          whole schedule here before downloading it */}
      <PreviewTable header={header} rows={rows} isUnit={(r) => !!rows[r][2]} />

      {error && <div className="status-fail">{error}</div>}

      <div className="row">
        <div className="grow">
          <div className="small">
            {header.length} extracted columns • {stats.rows ?? rows.length} records •
            Review the extracted HAP schedule before downloading.
          </div>
        </div>
        <button className="btn btn-secondary" disabled={busy} onClick={() => requestDownload('csv')}>
          Download CSV
        </button>
        <button className="btn btn-primary" disabled={busy} onClick={() => requestDownload('xlsx')}>
          Download Excel
        </button>
      </div>

      {showDetails && (
        <ProjectDetails
          initial={draft}
          initialLogo={ctx.logo}
          onClose={() => { setShowDetails(false); setPendingFormat(null) }}
          onSave={(details, logo, formState) => {
            ctx.setDetails(details)
            ctx.setLogo(logo)
            setDraft(formState)
            setShowDetails(false)
            if (pendingFormat) {
              send(pendingFormat, details, logo)
              setPendingFormat(null)
            }
          }}
        />
      )}
    </div>
  )
}
