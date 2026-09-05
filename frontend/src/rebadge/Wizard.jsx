// The four-step rebadging wizard, built to the design pages:
//   1 Import    — drop zone, imported files, processing mode, output safety
//   2 Configure — the six title-block fields beside a live preview
//   3 Preview   — full-batch confirmation before anything is written
//   4 Export    — what was produced, and what it did to each sheet
//
// The preview is the real thing: the server runs the same edit apply will run
// and sends back a picture of the result, so what is approved here is what
// comes out. Panels the design shows for features that are not built
// (templates, logo, PDF metadata) are rendered disabled rather than dropped,
// so the screen matches the design without offering dead controls.

import { useCallback, useEffect, useRef, useState } from 'react'
import { rebadge } from '../api'
import { FileBadge, StepChips, formatMb } from '../components.jsx'
import { REBADGE, save as saveRecent } from '../recents'

export const STEPS = ['Import', 'Configure', 'Preview', 'Export']

const FIELDS = [
  ['project_stage', 'PROJECT STAGE', 'Detailed Design'],
  ['sheet_status', 'SHEET STATUS', 'For Construction'],
  ['rev', 'REV', 'B'],
  ['description', 'DESCRIPTION', '100% Detailed Design Submission'],
  ['date', 'DATE', '03 Sep 2026'],
  ['approved_by', 'APPROVED BY', 'CK'],
]

// Shown on the Import screen. Everything in it is out of scope for v1, which
// is why the whole panel is inert.
const TEMPLATE_RULES = [
  'Corporate logo', 'Project title', 'Client name',
  'Drawing number', 'Revision / date', 'PDF metadata',
]

const blankInputs = () => Object.fromEntries(FIELDS.map(([key]) => [key, '']))


// ------------------------------------------------------------- 1. Import
function Import({ state, set }) {
  const input = useRef(null)
  const [dragging, setDragging] = useState(false)

  const add = (incoming) => {
    const pdfs = [...incoming].filter((f) => f.name.toLowerCase().endsWith('.pdf'))
    if (!pdfs.length) {
      set({ error: 'Those are not PDF files. Drawing sheets must be .pdf.' })
      return
    }
    const seen = new Set(state.files.map((f) => f.name))
    set({
      error: '',
      checks: null,
      files: [...state.files, ...pdfs.filter((f) => !seen.has(f.name))],
    })
  }

  const remove = (name) => set({
    checks: null,
    files: state.files.filter((f) => f.name !== name),
    selected: state.selected.filter((n) => n !== name),
  })

  const checkFor = (name) => state.checks?.sheets.find((s) => s.filename === name)

  return (
    <div className="split">
      <div className="card col" style={{ padding: '18px 24px' }}>
        <div>
          <h2 className="h2">1. Import Drawing Package</h2>
          <div className="small">Add PDF sheets or a complete drawing-set PDF.</div>
        </div>

        <div
          className={`dropzone${dragging ? ' active' : ''}${state.error ? ' error' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); add(e.dataTransfer.files) }}
        >
          <FileBadge size={52} />
          <div className="h2">Drop PDF files here</div>
          <div className="muted">or</div>
          <button className="btn btn-secondary" onClick={() => input.current?.click()}>
            Browse Files
          </button>
          <div className={state.error ? 'status-fail' : 'small'}>
            {state.error || '*Upload only .pdf'}
          </div>
          <input
            ref={input} type="file" accept=".pdf" multiple style={{ display: 'none' }}
            onChange={(e) => { add(e.target.files); e.target.value = '' }}
          />
        </div>

        {state.files.length > 0 && (
          <>
            <div className="h2" style={{ fontSize: 13 }}>Imported Files</div>
            <div className="import-list">
              {state.files.map((file) => {
                const check = checkFor(file.name)
                const chosen = state.selected.includes(file.name)
                return (
                  <div key={file.name} className="import-row">
                    <FileBadge size={30} />
                    {state.mode === 'selected' && (
                      <input
                        type="checkbox"
                        checked={chosen}
                        disabled={check ? !check.ok : false}
                        onChange={(e) => set({
                          selected: e.target.checked
                            ? [...state.selected, file.name]
                            : state.selected.filter((n) => n !== file.name),
                        })}
                      />
                    )}
                    <div className="grow">
                      <div className="recent-name">{file.name}</div>
                      <div className="small">
                        1 sheet • {formatMb(file.size)}
                        {check && ` • rotation ${check.rotation}°`}
                      </div>
                    </div>
                    {check && (
                      <span className={check.ok ? 'pill-ok' : 'pill-fail'}
                            title={(check.errors.join('; ') || 'Ready')}>
                        {check.ok ? `✓ REV ${check.current.rev || '—'}` : 'CANNOT REBADGE'}
                      </span>
                    )}
                    <button className="btn-ghost" title="Remove"
                            onClick={() => remove(file.name)}>×</button>
                  </div>
                )
              })}
            </div>
            {state.checks && state.checks.error_count > 0 && (
              <div className="banner-fail">
                {state.checks.error_count} sheet(s) cannot be rebadged and will be
                left out: {state.checks.sheets.filter((s) => !s.ok)
                  .map((s) => `${s.filename} — ${s.errors.join('; ')}`).join(' · ')}
              </div>
            )}
          </>
        )}

        <div className="row" style={{ gap: 14, alignItems: 'stretch' }}>
          <div className="info-card grow">
            <h4>Processing Mode</h4>
            <label className="radio-line">
              <input type="radio" checked={state.mode === 'all'}
                     onChange={() => set({ mode: 'all',
                                           selected: state.files.map((f) => f.name) })} />
              Entire drawing set
            </label>
            <label className="radio-line">
              <input type="radio" checked={state.mode === 'selected'}
                     onChange={() => set({ mode: 'selected' })} />
              Selected sheets only
            </label>
          </div>
          <div className="info-card grow">
            <h4>Output Safety</h4>
            <label className="radio-line">
              <input type="checkbox" checked readOnly disabled />
              Keep original PDF unchanged
            </label>
            <p>A new rebadged PDF will be created. This cannot be switched off.</p>
          </div>
        </div>
      </div>

      <div className="col">
        <div className="panel-card is-disabled" style={{ padding: '16px 18px' }}>
          <div className="row">
            <h2 className="h2 grow">Selected Template</h2>
            <span className="chip">Coming soon</span>
          </div>
          <div className="small" style={{ margin: '8px 0 10px' }}>Replacement Rules</div>
          <div className="rule-grid">
            {TEMPLATE_RULES.map((rule) => (
              <span key={rule} className="small">✓ {rule}</span>
            ))}
          </div>
          <p className="small" style={{ marginBottom: 0 }}>
            Technical drawing geometry will remain unchanged.
          </p>
        </div>
        <div className="small">
          Templates are not built yet. In this version the six title-block values
          are typed on the next step and applied to every selected sheet.
        </div>
      </div>
    </div>
  )
}


// ---------------------------------------------------------- 2. Configure
function Configure({ state, set }) {
  const chosen = state.files.filter((f) => state.selected.includes(f.name))
  const [sheet, setSheet] = useState(0)
  const [zoom, setZoom] = useState(100)
  const [preview, setPreview] = useState({ url: '', warnings: [], busy: false, error: '' })
  const complete = FIELDS.every(([key]) => state.inputs[key].trim())
  const file = chosen[Math.min(sheet, Math.max(chosen.length - 1, 0))]

  // The preview costs a real edit on the server, so it follows the typing
  // rather than racing it.
  const load = useCallback(async () => {
    if (!file || !complete) { setPreview((p) => ({ ...p, url: '', error: '' })); return }
    setPreview((p) => ({ ...p, busy: true, error: '' }))
    try {
      const shot = await rebadge.preview(file, state.inputs)
      setPreview((p) => {
        if (p.url) URL.revokeObjectURL(p.url)
        return { ...shot, busy: false, error: '' }
      })
    } catch (err) {
      setPreview((p) => ({ ...p, busy: false, error: err.message }))
    }
  }, [file, complete, JSON.stringify(state.inputs)])

  useEffect(() => {
    const timer = setTimeout(load, 450)
    return () => clearTimeout(timer)
  }, [load])

  useEffect(() => () => { if (preview.url) URL.revokeObjectURL(preview.url) }, [])

  return (
    <div className="split">
      <div className="card col" style={{ padding: '18px 24px' }}>
        <div>
          <h2 className="h2">Rebadging Rules</h2>
          <div className="small">
            Changes apply only to selected sheets. Drawing geometry remains untouched.
          </div>
        </div>

        <div>
          <div className="h2" style={{ fontSize: 13 }}>Title Block Fields</div>
          <div className="small">Change values to the new client / project standard.</div>
        </div>

        <div className="field-grid">
          {FIELDS.map(([key, label, hint]) => (
            <label key={key} className="stacked-field">
              <span>{label}</span>
              <input
                type="text"
                value={state.inputs[key]}
                placeholder={hint}
                onChange={(e) => set({ inputs: { ...state.inputs, [key]: e.target.value } })}
              />
            </label>
          ))}
        </div>

        <div className="grow" />

        <div className="panel-card is-disabled" style={{ padding: '12px 16px' }}>
          <div className="row">
            <h4 className="grow" style={{ margin: 0, fontSize: 13 }}>PDF Metadata</h4>
            <span className="chip">Coming soon</span>
          </div>
          <label className="radio-line">
            <input type="checkbox" disabled /> Update document title, author and project metadata
          </label>
          <label className="radio-line">
            <input type="checkbox" disabled /> Preserve original PDF metadata in output audit record
          </label>
        </div>
      </div>

      <div className="col">
        <div>
          <h2 className="h2">Live Sheet Preview</h2>
          <div className="small">
            Sheet {chosen.length ? Math.min(sheet, chosen.length - 1) + 1 : 0} of{' '}
            {chosen.length} • Changes shown in context
          </div>
        </div>

        <div className="row preview-bar">
          <select value={Math.min(sheet, Math.max(chosen.length - 1, 0))}
                  onChange={(e) => setSheet(Number(e.target.value))}
                  style={{ maxWidth: 260 }}>
            {chosen.map((f, i) => <option key={f.name} value={i}>{f.name}</option>)}
          </select>
          <div className="grow" />
          <span className="small">Zoom</span>
          <button className="btn-step" onClick={() => setZoom((z) => Math.max(50, z - 10))}>−</button>
          <span className="small" style={{ minWidth: 38, textAlign: 'center' }}>{zoom}%</span>
          <button className="btn-step" onClick={() => setZoom((z) => Math.min(200, z + 10))}>+</button>
        </div>

        <div className="preview-stage grow">
          {!complete && <span className="small">Fill all six fields to see the result</span>}
          {complete && preview.busy && <span className="small">Rendering the title block…</span>}
          {complete && !preview.busy && preview.error && (
            <span className="status-fail">{preview.error}</span>
          )}
          {complete && !preview.busy && !preview.error && preview.url && (
            <div className="preview-frame">
              <span className="preview-tag">Updated title block</span>
              <img src={preview.url} alt="Title block after rebadging"
                   style={{ width: `${zoom}%` }} />
            </div>
          )}
        </div>

        {preview.warnings.length > 0 && (
          <div className="banner-interp">{preview.warnings.join(' · ')}</div>
        )}

        <div className="row status-strip">
          <span className={`dot ${complete ? 'ok' : 'idle'}`} />
          <span className="small grow">
            {FIELDS.filter(([k]) => state.inputs[k].trim()).length} of 6 fields set
            {'  •  '}{chosen.length} sheet(s) selected{'  •  '}No geometry changes
          </span>
          <span className="small" style={{ fontWeight: 700 }}>
            {complete ? 'Validation passed' : 'Incomplete'}
          </span>
        </div>
      </div>
    </div>
  )
}


// ------------------------------------------------------------ 3. Preview
function Confirm({ state }) {
  const chosen = state.files.filter((f) => state.selected.includes(f.name))
  const excluded = state.checks?.sheets.filter((s) => !s.ok) || []
  const noop = (state.checks?.sheets || []).filter(
    (s) => s.ok && s.current?.rev &&
           s.current.rev.trim().toUpperCase() === state.inputs.rev.trim().toUpperCase())

  return (
    <div className="card col" style={{ padding: '18px 24px' }}>
      <div>
        <h2 className="h2">Confirm the rebadge</h2>
        <div className="small">
          These values will be written to every selected sheet. Nothing has been
          changed yet, and your originals are never overwritten.
        </div>
      </div>

      <div className="table-wrap" style={{ minHeight: 0 }}>
        <table className="grid">
          <thead>
            <tr><th>Field</th><th>Value applied</th><th>Sheets</th></tr>
          </thead>
          <tbody>
            {FIELDS.map(([key, label]) => (
              <tr key={key}>
                <td>{label}</td>
                <td style={{ fontWeight: 700 }}>{state.inputs[key]}</td>
                <td>{chosen.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {noop.length > 0 && (
        <div className="banner-interp">
          {noop.length} sheet(s) already carry revision {state.inputs.rev} — rebadging
          them changes the history but not the revision. Likely a typo; you can proceed.
        </div>
      )}
      {excluded.length > 0 && (
        <div className="banner-fail">
          Left out: {excluded.map((s) => `${s.filename} (${s.errors.join('; ')})`).join(' · ')}
        </div>
      )}

      <div className="small">
        {chosen.length} sheet(s) will be rebadged. Each becomes a new file named
        <code> &lt;original&gt;_rebadged.pdf</code>
        {chosen.length > 1 && ', delivered as one ZIP with an audit record'}.
      </div>
    </div>
  )
}


// ------------------------------------------------------------- 4. Export
function Export({ state, onRestart, onHome }) {
  const summary = state.result?.summary
  const notes = (summary?.sheets || []).filter((s) => s.ok && s.warnings.length)
  const failed = (summary?.sheets || []).filter((s) => !s.ok)
  const isZip = state.result?.name?.toLowerCase().endsWith('.zip')

  return (
    <div className="split">
      <div className="card col" style={{ padding: '18px 24px' }}>
        <div className="banner-ok">
          <div className="grow">
            <div className="h2">Export successful</div>
            <div className="small">
              {summary?.ok_count} of {summary?.total} sheets processed •{' '}
              {summary?.error_count} errors • {summary?.warning_count} informational
              note(s) • Audit record {isZip ? 'created' : 'available in a batch run'}
            </div>
          </div>
          <span className="small">Completed {state.finishedAt}</span>
        </div>

        <div>
          <h2 className="h2">Generated Files</h2>
          <div className="small">Files created from the validated rebadging configuration.</div>
        </div>

        <div className="import-row">
          <FileBadge size={34} kind={isZip ? 'ZIP' : 'PDF'} />
          <div className="grow">
            <div className="recent-name">{state.result?.name}</div>
            <div className="small">
              {summary?.ok_count} sheet(s) • {formatMb(state.result?.size || 0)} • Vector PDF
              {isZip && ' • includes the audit record'}
            </div>
          </div>
          <button className="btn btn-primary" onClick={() => state.download()}>
            Download {isZip ? 'ZIP' : 'PDF'}
          </button>
        </div>

        <div className="banner-ok" style={{ alignItems: 'flex-start' }}>
          <div>
            <div className="status-ok">✓ Original drawings protected</div>
            <div className="small">
              The source files were never opened for writing — every rebadged sheet
              is a new file.
            </div>
          </div>
        </div>

        {notes.length > 0 && (
          <div className="banner-interp">
            <strong>Informational notes</strong>
            <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
              {notes.map((s) => (
                <li key={s.filename} className="small">
                  {s.filename}: {s.warnings.join('; ')}
                </li>
              ))}
            </ul>
          </div>
        )}
        {failed.length > 0 && (
          <div className="banner-fail">
            <strong>Skipped</strong>
            <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
              {failed.map((s) => (
                <li key={s.filename} className="small">
                  {s.filename}: {s.errors.join('; ')}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="col">
        <div>
          <h2 className="h2">Processing Summary</h2>
          <div className="small">Final results for this rebadging job.</div>
        </div>

        <div className="stat-row">
          <div className="stat-tile">
            <div className="key">SHEETS PROCESSED</div>
            <div className="stat">{summary?.ok_count}</div>
            <div className="small">
              {summary?.total ? Math.round(100 * summary.ok_count / summary.total) : 0}%
            </div>
          </div>
          <div className="stat-tile">
            <div className="key">ERRORS</div>
            <div className="stat">{summary?.error_count}</div>
            <div className="small">{summary?.error_count ? 'Review' : 'Passed'}</div>
          </div>
          <div className="stat-tile">
            <div className="key">INFORMATIONAL</div>
            <div className="stat">{summary?.warning_count}</div>
            <div className="small">Reviewed</div>
          </div>
        </div>

        <div className="h2" style={{ fontSize: 13 }}>Applied rule groups</div>
        <div className="table-wrap" style={{ minHeight: 0 }}>
          <table className="grid">
            <tbody>
              {FIELDS.map(([key, label]) => (
                <tr key={key}>
                  <td>{label}</td>
                  <td>{summary?.ok_count} sheets</td>
                  <td style={{ fontWeight: 700 }}>Complete</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grow" />
        <div className="row">
          <button className="btn btn-secondary grow" onClick={onHome}>Open Project</button>
          <button className="btn btn-primary grow" onClick={onRestart}>
            Start New Rebadging →
          </button>
        </div>
      </div>
    </div>
  )
}


// -------------------------------------------------------------- the shell
export default function Wizard({ ctx }) {
  const [step, setStep] = useState(1)
  const [state, setState] = useState({
    files: [], selected: [], mode: 'all', inputs: blankInputs(),
    checks: null, busy: '', error: '', result: null, finishedAt: '',
  })
  const set = (patch) => setState((prev) => ({ ...prev, ...patch }))

  const chosen = state.files.filter((f) => state.selected.includes(f.name))
  const complete = FIELDS.every(([key]) => state.inputs[key].trim())

  const apply = async () => {
    set({ busy: 'applying', error: '' })
    try {
      const result = await rebadge.apply(chosen, state.inputs)
      const download = () => {
        const url = URL.createObjectURL(result.blob)
        const anchor = document.createElement('a')
        anchor.href = url
        anchor.download = result.name
        document.body.appendChild(anchor)
        anchor.click()
        anchor.remove()
        URL.revokeObjectURL(url)
      }
      const when = new Date()
      setState((prev) => ({
        ...prev, busy: '', result, download,
        finishedAt: when.toTimeString().slice(0, 5),
      }))
      saveRecent(REBADGE, {
        name: `${chosen[0]?.name.replace(/\.pdf$/i, '') || 'Drawing set'}`
              + (chosen.length > 1 ? ` +${chosen.length - 1}` : ''),
        summary: `${result.summary?.ok_count ?? chosen.length} sheets rebadged`
                 + ` • rev ${state.inputs.rev}`,
      })
      ctx.bumpRecents?.()
      setStep(4)
    } catch (err) {
      set({ busy: '', error: err.message })
    }
  }

  const restart = () => {
    setState({
      files: [], selected: [], mode: 'all', inputs: blankInputs(),
      checks: null, busy: '', error: '', result: null, finishedAt: '',
    })
    setStep(1)
  }

  const canContinue = {
    1: state.files.length > 0 && !state.busy,
    2: complete && chosen.length > 0,
    3: complete && chosen.length > 0 && !state.busy,
  }[step]

  return (
    <div className="col">
      <div className="row">
        <div className="grow">
          <div className="small">
            PDF Rebadging / {step === 4 ? 'Export Complete' : 'New Project'}
          </div>
          <h2 className="h1" style={{ fontSize: 22 }}>
            {step === 1 && 'Start Rebadging'}
            {step === 2 && 'Configure Rebadging'}
            {step === 3 && 'Review before applying'}
            {step === 4 && 'Rebadging Complete'}
          </h2>
          <div className="small">
            {step === 1 && 'Import your drawing package, then select the sheets to rebadge.'}
            {step === 2 && 'Set the six title block values and verify the live preview.'}
            {step === 3 && 'Confirm what will be written to every selected sheet.'}
            {step === 4 && 'Your drawing package was generated and the originals remain unchanged.'}
          </div>
        </div>
        <StepChips steps={STEPS} current={step} />
      </div>

      {state.error && <div className="banner-fail">{state.error}</div>}

      {step === 1 && <Import state={state} set={set} />}
      {step === 2 && <Configure state={state} set={set} />}
      {step === 3 && <Confirm state={state} />}
      {step === 4 && (
        <Export state={state} onRestart={restart}
                onHome={() => ctx.setPage('rebadge-home')} />
      )}

      {step < 4 && (
        <div className="row">
          <span className="small grow">
            Step {step} of 4 • {['Import & check the drawing set',
                                'Configure replacement values and verify the preview',
                                'Confirm and apply'][step - 1]}
          </span>
          <button className="btn btn-secondary"
                  onClick={() => (step === 1 ? ctx.setPage('rebadge-home') : setStep(step - 1))}>
            {step === 1 ? 'Cancel' : '← Back'}
          </button>
          {step === 1 && (
            <button className="btn btn-primary" disabled={!canContinue}
                    onClick={async () => {
                      set({ busy: 'validating', error: '' })
                      try {
                        // Every sheet is checked before anything is configured.
                        // A clean set goes straight on; a set with problems
                        // stays here so the verdicts can be read and the bad
                        // sheets removed or left out.
                        const report = state.checks
                          || await rebadge.validate(state.files)
                        set({
                          busy: '', checks: report,
                          selected: report.sheets.filter((s) => s.ok).map((s) => s.filename),
                        })
                        if (report.ok_count === 0) {
                          set({ error: 'No sheet in this set can be rebadged.' })
                        } else if (report.error_count === 0 || state.checks) {
                          setStep(2)
                        }
                      } catch (err) {
                        set({ busy: '', error: err.message })
                      }
                    }}>
              {state.busy === 'validating' ? 'Checking sheets…' : 'Continue →'}
            </button>
          )}
          {step === 2 && (
            <button className="btn btn-primary" disabled={!canContinue}
                    onClick={() => setStep(3)}>
              Preview →
            </button>
          )}
          {step === 3 && (
            <button className="btn btn-primary" disabled={!canContinue} onClick={apply}>
              {state.busy === 'applying'
                ? `Rebadging ${chosen.length} sheet(s)…`
                : `Apply to ${chosen.length} sheet(s)`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
