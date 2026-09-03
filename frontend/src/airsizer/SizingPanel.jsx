// The per-subspace sizing panel.
// Ported from hap_converter/airsizer/ui/sizing_dialog.py, including the
// ▲/▼ stepper that walks the subspaces without closing the panel, and the
// prompt that fires when you'd leave a sized-but-unsaved subspace behind.

import { useEffect, useMemo, useState } from 'react'
import { airsizer } from '../api'
import { Modal } from '../components.jsx'

// Fixed running order, so the form never reshuffles when the type changes.
const INPUT_ORDER = [
  'no_of_outlets', 'velocity', 'nc', 'slot_width',
  'no_of_slots', 'grille_height', 'bar_pitch', 'deflection',
]

const BLANK = '--'
const NA = 'NA'
const PENDING = 'Yet to Calculate'

export default function SizingPanel({ ctx, startRow, onClose }) {
  const config = ctx.airConfig
  const sizable = useMemo(() => ctx.spaces.filter((s) => s.sizable), [ctx.spaces])
  const inputsByKey = useMemo(
    () => Object.fromEntries(config.inputs.map((i) => [i.key, i])), [config])
  const diffusersByKey = useMemo(
    () => Object.fromEntries(config.diffusers.map((d) => [d.key, d])), [config])

  const [index, setIndex] = useState(() => Math.max(0, sizable.findIndex((s) => s.row === startRow)))
  const space = sizable[index]

  const [diffuser, setDiffuser] = useState('')
  const [values, setValues] = useState({})
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [hint, setHint] = useState('')
  const [prompt, setPrompt] = useState(null)   // pending navigation awaiting an answer

  const spec = diffuser ? diffusersByKey[diffuser] : null

  // Load whatever is already saved for this subspace, and re-size it so the
  // outputs come back exactly as they were.
  useEffect(() => {
    if (!space) return
    const saved = ctx.sizingInputs[space.row]
    setDiffuser(saved?.diffuser || '')
    setValues(saved?.values || {})
    setResult(null)
    setHint('')
    if (saved) {
      airsizer.size(space, saved.diffuser, saved.values).then(setResult).catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, space?.row])

  const optionsFor = (key) => {
    if (spec?.options?.[key]?.length) return spec.options[key]
    return inputsByKey[key]?.options || []
  }

  const takes = (key) => !!spec?.inputs.includes(key)

  const setValue = (key, value) => {
    setValues((prev) => ({ ...prev, [key]: value }))
    setResult(null)          // a stale result must never linger
    setHint('')
  }

  const changeType = (key) => {
    setDiffuser(key)
    setValues({})
    setResult(null)
    setHint('')
  }

  const runSizing = async () => {
    if (!spec) return
    setBusy(true)
    try {
      const active = {}
      spec.inputs.forEach((key) => { active[key] = values[key] || '' })
      setResult(await airsizer.size(space, diffuser, active))
    } catch (err) {
      setResult({ ok: false, message: err.message, status: 'No valid selection' })
    } finally {
      setBusy(false)
    }
  }

  const dirty = () => {
    if (!result?.ok) return false
    const saved = ctx.sizingInputs[space.row]
    if (!saved || saved.diffuser !== diffuser) return true
    return spec.inputs.some((key) => (saved.values[key] || '') !== (values[key] || ''))
  }

  const commit = () => {
    const active = {}
    spec.inputs.forEach((key) => { active[key] = values[key] || '' })
    ctx.recordSizing(space.row, diffuser, active, result)
  }

  const save = () => {
    if (!result?.ok) return
    commit()
    setHint('Saved ✓')
    setTimeout(() => setHint(''), 2500)
  }

  // Any navigation goes through here so unsaved work is never dropped silently.
  const leave = (action) => {
    if (dirty()) { setPrompt(() => action); return }
    action()
  }

  const step = (delta) => {
    const next = index + delta
    if (next < 0 || next >= sizable.length) return
    leave(() => setIndex(next))
  }

  if (!space) return null

  const outputs = result?.ok
    ? {
        lsm: result.group === 'A' ? result.lsm : NA,
        throw: result.throw,
        size: result.group === 'B' ? result.size : NA,
      }
    : result
      ? { lsm: NA, throw: NA, size: NA }
      : { lsm: PENDING, throw: PENDING, size: PENDING }

  const outputClass = (value) => {
    if (value === PENDING) return 'pending'
    if (value === NA) return 'na'
    return result?.interpolated ? 'interpolated' : ''
  }

  const derived = result?.ok
    ? result.group === 'A'
      ? `Air outlet length ${result.length_m} m  •  ${result.pieces} pcs  •  NC ${result.nc}`
      : `${result.outlets} outlet(s)  •  ${result.velocity} m/s  •  NC ${result.nc}` +
        (result.alt_sizes?.length ? `  •  also ${result.alt_sizes.join(', ')}` : '')
    : ''

  return (
    <Modal onClose={() => leave(onClose)} width={1060}>
      <div className="sizing-grid">
        {/* ------------------------------------------------ inputs */}
        <div className="sizing-form">
          <div className="row" style={{ marginBottom: 12, gap: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 700 }}>Zone Name / Space Name</span>
            <select
              className="grow"
              value={space.row}
              onChange={(e) => {
                const next = sizable.findIndex((s) => String(s.row) === e.target.value)
                if (next >= 0 && next !== index) leave(() => setIndex(next))
              }}
            >
              {sizable.map((s) => (
                <option key={s.row} value={s.row}>
                  {ctx.sizingInputs[s.row] ? `✓  ${s.name}` : s.name}
                </option>
              ))}
            </select>
            <div className="spinner">
              <button title="Previous subspace" disabled={index === 0} onClick={() => step(-1)}>▲</button>
              <button title="Next subspace" disabled={index === sizable.length - 1} onClick={() => step(1)}>▼</button>
            </div>
            <span className="position">{index + 1} of {sizable.length}</span>
            <span title="Values below come from the HAPExt schedule">⚡</span>
          </div>

          <div className="row" style={{ gap: 12, marginBottom: 14, alignItems: 'stretch' }}>
            {[
              ['Floor Area (m²)', space.floor_area],
              ['Total Coil Load (KW)', space.total_coil],
              ['Sens Coil Load (KW)', space.sens_coil],
              ['Air Flow (L/s)', space.air_flow],
            ].map(([caption, value]) => (
              <div className="grow" key={caption}>
                <div className="field-caption">{caption}</div>
                <div className="readonly-field">{value || '—'}</div>
              </div>
            ))}
          </div>

          <div className="form-row">
            <span>Diffuser Type</span>
            <select value={diffuser} onChange={(e) => changeType(e.target.value)}>
              <option value="">{BLANK}</option>
              {config.diffusers.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
            </select>
          </div>

          {INPUT_ORDER.map((key) => {
            const input = inputsByKey[key]
            const enabled = takes(key)
            return (
              <div className="form-row" key={key}>
                <span>{input.title}</span>
                {input.kind === 'count' ? (
                  <input
                    type="text" inputMode="numeric" placeholder={NA} disabled={!enabled}
                    value={enabled ? (values[key] || '') : ''}
                    onChange={(e) => setValue(key, e.target.value.replace(/[^0-9]/g, ''))}
                  />
                ) : (
                  <select
                    disabled={!enabled}
                    value={enabled ? (values[key] || '') : ''}
                    onChange={(e) => setValue(key, e.target.value)}
                  >
                    {enabled
                      ? [<option key="" value="">{BLANK}</option>,
                         ...optionsFor(key).map((o) => <option key={o} value={o}>{o}</option>)]
                      : <option value="">{NA}</option>}
                  </select>
                )}
              </div>
            )
          })}
        </div>

        {/* ------------------------------------------------ outputs */}
        <div className="sizing-side">
          <div className="diagram-frame">
            {spec
              ? <img src={spec.diagram} alt={`${spec.label} construction detail`} />
              : <span className="small">Select a diffuser type</span>}
          </div>

          <button className="btn-sizing" disabled={!spec || busy} onClick={runSizing}>
            {busy ? 'Sizing…' : 'Sizing'}
          </button>

          {result?.ok && result.interpolated && (
            <div className="banner-interp">
              {ctx.airConfig.interpolation_remark}
            </div>
          )}
          {result && !result.ok && <div className="banner-fail">{result.message}</div>}

          {[['lsm', 'Output (l/s/m)'], ['throw', 'Flow Throw (m)'], ['size', 'Output (mmxmm)']].map(([key, caption]) => (
            <div className="output-row" key={key}>
              <span>{caption}</span>
              <span className={`output-field ${outputClass(outputs[key])}`}>{outputs[key]}</span>
            </div>
          ))}

          <div className="output-note"><span className="small">{derived}</span></div>
          <div className="output-note"><span className="saved-hint">{hint}</span></div>
          <div className="grow" />

          <div className="row">
            <button className="btn btn-primary grow" disabled={!result?.ok} onClick={save}>SAVE</button>
            <button className="btn btn-close grow" onClick={() => leave(onClose)}>CLOSE</button>
          </div>
        </div>
      </div>

      {prompt && (
        <Modal title="Save this sizing?" onClose={() => setPrompt(null)} width={420}>
          <p className="muted">{space.name} has been sized but not saved.</p>
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button className="btn btn-secondary" onClick={() => setPrompt(null)}>Cancel</button>
            <button className="btn btn-secondary" onClick={() => { const go = prompt; setPrompt(null); go() }}>
              Discard
            </button>
            <button className="btn btn-primary" onClick={() => { commit(); const go = prompt; setPrompt(null); go() }}>
              Save
            </button>
          </div>
        </Modal>
      )}
    </Modal>
  )
}
