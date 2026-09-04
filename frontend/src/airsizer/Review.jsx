// Steps 3-4 — Review Results and Project Summary, with the Jira-style column
// picker governing both the preview and the export.
// Ported from hap_converter/airsizer/ui/review_page.py.
//
// Row assembly mirrors airsizer/engine/export.py's build_rows so what you
// approve on screen is what the server writes.

import { useEffect, useRef, useState } from 'react'
import { airsizer } from '../api'
import { Modal, PreviewTable, StepChips, SummaryStrip } from '../components.jsx'
import ProjectDetails, { logoDataUrl } from '../ProjectDetails.jsx'
import SizingPanel from './SizingPanel.jsx'
import { STEPS, rowTint } from './Wizard.jsx'

function cellValue(key, space, entry, result, interpRemark) {
  switch (key) {
    case 'name': return space.name
    case 'floor_area': return space.floor_area
    case 'total_coil': return space.total_coil
    case 'sens_coil': return space.sens_coil
    case 'air_flow': return space.air_flow
    default: break
  }
  if (space.is_unit || !result) return ''
  if (key === 'diffuser') return entry?.label || ''
  if (key === 'status') return result.status
  if (!result.ok) return ''
  switch (key) {
    case 'lsm': return result.lsm
    case 'length':
      return result.group === 'A'
        ? (result.length_m ? `${result.length_m} / ${result.pieces}` : '')
        : (result.outlets ? String(result.outlets) : '')
    case 'throw': return result.throw
    case 'size': return result.size
    case 'nc_out': return result.nc
    case 'velocity_out': return result.velocity
    case 'pt': return result.pt
    case 'interpolated': return result.interpolated ? 'Yes' : ''
    case 'remarks': return result.interpolated ? interpRemark : ''
    default: return ''
  }
}

function ColumnPicker({ columns, visible, onChange }) {
  const [open, setOpen] = useState(false)
  const box = useRef(null)

  useEffect(() => {
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  const toggle = (key) => {
    onChange(visible.includes(key) ? visible.filter((k) => k !== key) : [...visible, key])
  }

  return (
    <div className="picker" ref={box}>
      <button title="Show or hide columns" onClick={() => setOpen((o) => !o)}>‖‖</button>
      {open && (
        <div className="picker-menu">
          {columns.map((c) => (
            <label key={c.key} className={c.locked ? 'locked' : ''}>
              <input
                type="checkbox"
                checked={c.locked || visible.includes(c.key)}
                disabled={c.locked}
                onChange={() => toggle(c.key)}
              />
              {c.label}{c.locked ? '  (always shown)' : ''}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Review({ ctx }) {
  const [stage, setStage] = useState(3)
  const [busy, setBusy] = useState(false)
  const [downloaded, setDownloaded] = useState(false)
  const [confirmUnsized, setConfirmUnsized] = useState(false)
  const [showDetails, setShowDetails] = useState(false)
  const [draft, setDraft] = useState(null)      // keeps the form between opens
  const [error, setError] = useState('')
  const [openRow, setOpenRow] = useState(null)

  if (!ctx.spaces.length || !ctx.airConfig) {
    return <div className="muted">No sizing session open.</div>
  }

  const all = ctx.airConfig.result_columns
  const visible = ctx.visibleColumns || all.filter((c) => c.default).map((c) => c.key)
  const columns = all.filter((c) => visible.includes(c.key) || c.locked)

  const labelFor = (key) => ctx.airConfig.diffusers.find((d) => d.key === key)?.label || key

  const rows = ctx.spaces.map((space) => {
    const entry = ctx.sizingInputs[space.row]
    const result = ctx.results[space.row]
    const withLabel = entry ? { ...entry, label: labelFor(entry.diffuser) } : null
    return columns.map((c) =>
      cellValue(c.key, space, withLabel, result, ctx.airConfig.interpolation_remark || ''))
  })

  const results = Object.values(ctx.results)
  const sized = results.filter((r) => r.ok).length
  const sizableCount = ctx.spaces.filter((s) => s.sizable).length
  const unsized = sizableCount - sized
  const failed = results.filter((r) => !r.ok).length
  const interpolated = results.filter((r) => r.ok && r.interpolated).length

  const exportFile = async (details = ctx.airDetails, logo = ctx.airLogo) => {
    setBusy(true)
    setError('')
    try {
      await airsizer.export({
        spaces: ctx.spaces,
        inputs: ctx.sizingInputs,
        visible_columns: visible,
        base_name: ctx.airBaseName,
        project_name: ctx.airSource,
        details,
        logo: await logoDataUrl(logo),
      })
      ctx.rememberSizing()          // keep it in this browser's history
      setDownloaded(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  // The sheet is headed by the same nine inputs the HAPExt schedule carries,
  // so they are asked for before the workbook is written, not after.
  const requestExport = () => {
    if (unsized > 0) { setConfirmUnsized(true); return }
    if (!ctx.airDetails || !ctx.airLogo) { setShowDetails(true); return }
    exportFile()
  }

  const notes = [`${rows.length} rows • ${columns.length} columns • ${sized} sized`]
  if (interpolated) notes.push(`${interpolated} interpolated (amber)`)
  if (failed) notes.push(`${failed} with no valid selection (red)`)

  return (
    <div className="col">
      <h2 className="h2">Air Diffuser Sizing</h2>
      <div className="small">
        Select a diffuser from the catalog. Available sizing options will update automatically.
      </div>

      <StepChips steps={STEPS} current={stage} />

      <div className="card col" style={{ padding: '16px 18px', flex: 1 }}>
        {stage === 4 && (
          <SummaryStrip items={[
            ['FILE', `${ctx.airBaseName} - sized.xlsx`],
            ['ROWS', String(rows.length)],
            ['COLUMNS', String(columns.length)],
            ['SIZED', String(sized)],
            ['STATUS', downloaded ? 'Downloaded' : 'Ready to generate', downloaded ? 'ok' : ''],
          ]} />
        )}

        <div className="row">
          <span className="sheet-tab">HAP Air Diffuser Schedule</span>
          <div className="grow" />
          <ColumnPicker columns={all} visible={visible} onChange={ctx.setVisibleColumns} />
        </div>

        <PreviewTable
          header={columns.map((c) => c.label)}
          rows={rows}
          isUnit={(r) => ctx.spaces[r].is_unit}
          rowClass={(r) => rowTint(ctx.spaces[r], ctx.results[ctx.spaces[r].row])}
          actions={stage === 3 ? (r) => {
            const space = ctx.spaces[r]
            if (!space.sizable) return null
            const done = !!ctx.results[space.row]
            return (
              <button
                className={`btn-row${done ? '' : ' todo'}`}
                onClick={() => setOpenRow(space.row)}
              >
                {done ? 'Preview' : 'Yet to be sized'}
              </button>
            )
          } : null}
        />

        <div className="small">{notes.join('    ')}</div>
        {error && <div className="banner-fail">{error}</div>}
      </div>

      <div className="row">
        {stage === 4 ? (
          <button className="btn btn-secondary" onClick={() => setStage(3)}>Review Results</button>
        ) : (
          <button className="btn btn-secondary" onClick={() => ctx.setPage('air-wizard')}>Back to sizing</button>
        )}
        <div className="grow" />
        {stage === 3 ? (
          <button
            className="btn btn-primary"
            disabled={sized === 0}
            title="Review the roll-up, then generate the workbook from the summary"
            onClick={() => setStage(4)}
          >
            Project Summary
          </button>
        ) : (
          <>
            <button className="btn btn-secondary" onClick={() => setShowDetails(true)}>
              Project Details{ctx.airDetails ? ' ✓' : ''}
            </button>
            <button
              className="btn btn-primary"
              disabled={sized === 0 || busy}
              onClick={requestExport}
            >
              {busy ? 'Generating…' : downloaded ? 'Download again' : 'Generate Excel'}
            </button>
          </>
        )}
      </div>

      {openRow !== null && (
        <SizingPanel ctx={ctx} startRow={openRow} onClose={() => setOpenRow(null)} />
      )}

      {showDetails && (
        <ProjectDetails
          initial={draft}
          initialLogo={ctx.airLogo}
          onImport={() => ctx.airImported}
          onClose={() => setShowDetails(false)}
          onSave={(details, logo, formState) => {
            ctx.setAirDetails(details)
            ctx.setAirLogo(logo)
            setDraft(formState)
            setShowDetails(false)
            if (stage === 4) exportFile(details, logo)
          }}
        />
      )}

      {confirmUnsized && (
        <Modal title="Some subspaces are not sized yet" onClose={() => setConfirmUnsized(false)} width={460}>
          <p className="muted">
            {unsized} of {sizableCount} subspaces have no sizing — their sizing
            columns will be blank in the workbook. Generate it anyway?
          </p>
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button className="btn btn-secondary" onClick={() => setConfirmUnsized(false)}>Cancel</button>
            <button
              className="btn btn-primary"
              onClick={() => {
                setConfirmUnsized(false)
                if (!ctx.airDetails || !ctx.airLogo) setShowDetails(true)
                else exportFile()
              }}
            >
              Generate anyway
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}
