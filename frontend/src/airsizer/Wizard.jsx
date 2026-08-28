// Steps 1-2 — the schedule table with a per-row sizing action.
// Ported from hap_converter/airsizer/ui/wizard_page.py.

import { useState } from 'react'
import { PreviewTable, StepChips } from '../components.jsx'
import SizingPanel from './SizingPanel.jsx'

export const STEPS = [
  'Select Diffuser Type', 'Configure Parameters', 'Review Results', 'Project Summary',
]

const COLUMNS = [
  'Zone Name / Space Name', 'Floor Area (m²)', 'Total Coil Load (KW)',
  'Sens Coil Load (KW)', 'Air Flow (L/s)',
]

export function rowTint(space, result) {
  if (space.is_unit || !result) return ''
  if (!result.ok) return 'failed'
  return result.interpolated ? 'interpolated' : 'sized'
}

export default function Wizard({ ctx }) {
  const [openRow, setOpenRow] = useState(null)

  if (!ctx.spaces.length) {
    return (
      <div className="muted">
        No schedule loaded.{' '}
        <button className="btn-ghost" onClick={() => ctx.setPage('air-home')}>Load one</button>
      </div>
    )
  }

  const rows = ctx.spaces.map((s) => [s.name, s.floor_area, s.total_coil, s.sens_coil, s.air_flow])
  const sizedCount = Object.values(ctx.results).filter((r) => r.ok).length
  const total = ctx.spaces.filter((s) => s.sizable).length

  return (
    <div className="col">
      <h2 className="h2">Air Diffuser Sizing</h2>
      <div className="small">
        Select a diffuser from the catalog. Available sizing options will update automatically.
      </div>

      <StepChips steps={STEPS} current={sizedCount ? 2 : 1} />

      <div className="card col" style={{ padding: '16px 18px', flex: 1 }}>
        <PreviewTable
          header={COLUMNS}
          rows={rows}
          isUnit={(r) => ctx.spaces[r].is_unit}
          rowClass={(r) => rowTint(ctx.spaces[r], ctx.results[ctx.spaces[r].row])}
          actions={(r) => {
            const space = ctx.spaces[r]
            if (!space.sizable) return null
            const done = !!ctx.results[space.row]
            return (
              <button className={`btn-row${done ? ' done' : ''}`} onClick={() => setOpenRow(space.row)}>
                {done ? 'Preview' : 'Click Here'}
              </button>
            )
          }}
        />
        <div className="small">Tip: Select the exact catalog type first to unlock its controls.</div>
      </div>

      <div className="row">
        <span className="small grow">
          {ctx.airSource} • {sizedCount} of {total} subspaces sized
        </span>
        <button
          className="btn btn-primary"
          disabled={sizedCount === 0}
          title="Review the sized schedule before exporting"
          onClick={() => ctx.setPage('air-review')}
        >
          Generate Excel
        </button>
      </div>

      {openRow !== null && (
        <SizingPanel ctx={ctx} startRow={openRow} onClose={() => setOpenRow(null)} />
      )}
    </div>
  )
}
