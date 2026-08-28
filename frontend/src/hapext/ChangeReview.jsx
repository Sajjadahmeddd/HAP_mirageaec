// Change Request review — the updated schedule with the appended rows
// highlighted, then Approve & Download.
// Ported from hap_converter/ui/pages/change_review_page.py.

import { base64ToBlob, saveBlob } from '../api'
import { PreviewTable, SummaryStrip } from '../components.jsx'

const PREVIEW_LIMIT = 40
const CONTEXT_ROWS = 6
const XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

export default function ChangeReview({ ctx }) {
  const result = ctx.changeResult
  if (!result?.ok) return <div className="muted">No change request to review.</div>

  const { header, rows, stats, previous_name: previousName, filename, existing_rows: existing } = result
  const total = stats.total_rows ?? rows.length
  const newRows = stats.new_rows ?? 0

  // window the preview on the boundary: a few existing rows for context,
  // then the appended ones, so the change is visible at a glance
  const start = Math.max(0, existing - CONTEXT_ROWS)
  const window = rows.slice(start, start + PREVIEW_LIMIT)
  const firstNew = Math.max(0, existing - start)

  const approve = () => {
    saveBlob(base64ToBlob(result.file_b64, XLSX_TYPE), filename)
  }

  return (
    <div className="card col" style={{ padding: '18px 24px' }}>
      <div className="radios">
        <label onClick={() => ctx.setPage('hap-upload')}>
          <input type="radio" checked={false} readOnly /> New Project
        </label>
        <label><input type="radio" checked readOnly /> Change Request</label>
      </div>

      <div className="row">
        <h2 className="h2" style={{ fontSize: 18 }}>Review Changes</h2>
        <span className="chip">{newRows} NEW ITEMS</span>
        <div className="grow" />
        <button className="btn btn-secondary" onClick={() => ctx.setPage('hap-change')}>Re-process</button>
        <button className="btn btn-primary" onClick={approve}>Approve &amp; Download</button>
      </div>

      <div className="small">
        {previousName} • New line items are appended to the end and highlighted
      </div>

      <SummaryStrip items={[
        ['PREVIOUS', `${existing} rows`],
        ['NEW', `${newRows} rows`],
        ['UPDATED FILE', `${total} rows • ${stats.columns ?? header.length} columns`],
        ['CHANGE RULE', 'Append only • No existing rows changed'],
      ]} />

      <span className="sheet-tab">HAP Zone Sizing Summary</span>
      <PreviewTable
        header={header}
        rows={window}
        isUnit={(r) => !!window[r][2]}
        rowClass={(r) => (r >= firstNew ? 'new-row' : '')}
      />

      <div className="row">
        <span style={{
          width: 14, height: 14, background: '#E9F3DA',
          border: '1px solid #C9D9AE', borderRadius: 3, display: 'inline-block',
        }} />
        <span className="small grow">
          Highlighted rows = newly appended line items    (showing {window.length} of {total} rows)
        </span>
        <button className="btn btn-primary" onClick={approve}>Approve &amp; Download</button>
      </div>
    </div>
  )
}
