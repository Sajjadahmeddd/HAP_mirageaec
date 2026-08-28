// HAPExt failure page — dynamic reason cards plus the per-page issue list.
// The categorisation mirrors _categorize() in
// hap_converter/ui/pages/failure_page.py, keyed off the same issue.field
// strings the engine emits.

import { PdfBadge, StepTimeline, formatMb } from '../components.jsx'

const STEPS = ['File uploaded', 'Extracting data', 'Generate Excel']

function categorize(issues) {
  const fields = new Set(issues.map((i) => i.field))
  const reason = (icon, title, desc, step, caption) => ({ icon, title, desc, step, caption })

  if (fields.has('file')) {
    return {
      reasons: [reason('✕', 'File Could Not Be Read',
        'The file could not be opened as a PDF.\nIt may be corrupted or not a PDF document.',
        1, 'Failed – File could not be read')],
      details: [],
      summary: 'The uploaded file could not be opened as a PDF document.',
    }
  }
  if (fields.has('protected')) {
    return {
      reasons: [reason('🔒', 'Content Protected',
        'This PDF is password protected or\nrestricted from data extraction.',
        1, 'Failed – PDF is protected')],
      details: [],
      summary: 'The uploaded PDF is protected and cannot be read for data extraction.',
    }
  }
  if (fields.has('scanned')) {
    return {
      reasons: [reason('T', 'Scanned Document',
        'The PDF appears to be scanned.\nText cannot be extracted.',
        2, 'Failed – Unable to extract data')],
      details: [],
      summary: 'The uploaded PDF does not contain extractable text to generate an Excel file.',
    }
  }
  if (fields.has('document')) {
    return {
      reasons: [reason('▦', 'No HAP Data Detected',
        'No HAP Zone Sizing Summary pages were found.\nCheck that the correct report was exported from HAP.',
        2, 'Failed – Unable to extract data')],
      details: [],
      summary: 'The uploaded PDF does not contain enough structured or tabular data to generate an Excel file.',
    }
  }
  if (fields.has('no_changes')) {
    return {
      reasons: [reason('=', 'No New Line Items',
        'Every unit in the revised PDF is already\npresent in the uploaded Excel.',
        3, 'Stopped – Nothing to append')],
      details: [],
      summary: issues.find((i) => i.field === 'no_changes')?.description || '',
    }
  }
  if (fields.has('excel_format')) {
    return {
      reasons: [reason('▤', 'Not a HAPExt Schedule',
        'The uploaded workbook was not generated\nby HAPExt, so it cannot be appended to.',
        1, 'Failed – Unrecognised workbook')],
      details: issues.filter((i) => i.field === 'excel_format'),
      summary: 'The uploaded Excel file is not in the HAPExt schedule format.',
    }
  }
  if (fields.has('error')) {
    return {
      reasons: [reason('!', 'Output Could Not Be Written',
        'The converted file could not be saved.\nThe folder may be locked, full, or read-only.',
        3, 'Failed – Could not write file')],
      details: issues.filter((i) => i.field === 'error'),
      summary: 'The conversion failed while writing the output file.',
    }
  }

  // otherwise: mandatory-value validation issues
  const unreadable = issues.filter(
    (i) => i.description.includes('Unreadable') || i.description.toLowerCase().includes('zero'))
  const missing = issues.filter((i) => !unreadable.includes(i))
  const reasons = []
  if (missing.length) {
    reasons.push(reason('!', 'Missing Mandatory Values',
      `${missing.length} required value(s) are missing across ${new Set(missing.map((i) => i.page)).size} page(s).\nThe full list is shown below.`,
      2, 'Failed – Missing mandatory data'))
  }
  if (unreadable.length) {
    reasons.push(reason('≠', 'Unreadable Values',
      `${unreadable.length} value(s) could not be read as numbers.\nThey are listed below with their page numbers.`,
      2, 'Failed – Unreadable data'))
  }
  return {
    reasons,
    details: [...issues].sort((a, b) => a.page - b.page),
    summary: 'The uploaded PDF is missing mandatory values, so the Excel file\nwas not generated (all-or-nothing validation).',
  }
}

export default function Failure({ ctx }) {
  const result = ctx.conversion || ctx.changeResult
  const issues = result?.issues || []
  const { reasons, details, summary } = categorize(issues)
  const first = reasons[0]
  const name = ctx.pdf?.name || result?.source || '—'

  return (
    <div className="split">
      <div className="card col" style={{ padding: '18px 28px', alignItems: 'stretch' }}>
        <div style={{ textAlign: 'center', position: 'relative' }}>
          <PdfBadge size={52} />
          <span style={{
            background: 'var(--red)', color: '#fff', borderRadius: 10, padding: '2px 8px',
            fontWeight: 800, fontSize: 12, marginLeft: -10, verticalAlign: 'top',
          }}>!</span>
        </div>
        <h2 className="h2" style={{ textAlign: 'center', fontSize: 18 }}>Unable to Generate Excel</h2>
        <div className="muted" style={{ textAlign: 'center', whiteSpace: 'pre-line' }}>{summary}</div>

        <h2 className="h2">Failure Reasons</h2>
        <div className="reason-frame">
          {reasons.map((r) => (
            <div className="reason" key={r.title}>
              <span className="reason-icon">{r.icon}</span>
              <span className="reason-title">{r.title}</span>
              <span className="reason-desc">{r.desc}</span>
            </div>
          ))}
        </div>

        {details.length > 0 && (
          <div className="issue-list">
            {details.map((issue, i) => (
              <div className="reason-desc" key={i}>
                {issue.page ? `Page ${issue.page}` : 'File'} — {issue.field}: {issue.description}
              </div>
            ))}
          </div>
        )}

        <div className="row" style={{ justifyContent: 'center' }}>
          <button className="btn btn-secondary" onClick={() => ctx.setPage('hap-upload')}>
            ⬆  Upload Another File
          </button>
          <button className="btn btn-primary" onClick={() => ctx.setPage('hap-home')}>Go to Dashboard</button>
        </div>
      </div>

      <div className="panel-card" style={{ padding: '18px 20px' }}>
        <h2 className="h2">Conversion Status</h2>
        <div className="small" style={{ margin: '10px 0 6px' }}>Current file</div>
        <div className="card row" style={{ padding: '12px 14px', marginBottom: 16 }}>
          <PdfBadge size={38} />
          <div>
            <div className="recent-name">{name}</div>
            <div className="small">
              {ctx.pdf ? `${formatMb(ctx.pdf.size)} • Conversion failed` : 'Conversion failed'}
            </div>
          </div>
        </div>
        <StepTimeline
          steps={STEPS}
          current={0}
          failedStep={first?.step || 2}
          caption={first?.caption || 'Failed'}
        />
        <div className="banner-fail" style={{ marginTop: 16 }}>Failed</div>
        <div className="small" style={{ marginTop: 8 }}>Please resolve the issues above and try again.</div>
      </div>
    </div>
  )
}
