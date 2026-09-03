// AirSizer Pro home — hero, Quick Start, Recent Projects, Help.
// Ported from hap_converter/airsizer/ui/home_page.py.

import { useRef, useState } from 'react'
import { airsizer } from '../api'
import { Modal } from '../components.jsx'
import { DuctArt, HeroImage } from '../HeroArt.jsx'
import RecentPanel from '../RecentPanel.jsx'
import { AIRSIZER } from '../recents'

const FEATURES = ['Accurate\nSizing', 'Smart\nSelection', 'Clear\nValidation', 'Reliable\nResults']

function QuickCard({ glyph, title, body, enabled, onClick }) {
  return (
    <div
      className="card"
      style={{ padding: '18px 18px 16px', cursor: enabled ? 'pointer' : 'not-allowed', opacity: enabled ? 1 : 0.55 }}
      onClick={() => enabled && onClick()}
    >
      <div className="quick-icon" style={{ marginBottom: 10 }}>{glyph}</div>
      <div className="h2">{title}</div>
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <p className="small grow" style={{ margin: '6px 0 0' }}>{body}</p>
        <span className="h2">→</span>
      </div>
    </div>
  )
}

export default function Home({ ctx }) {
  const input = useRef(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [help, setHelp] = useState(false)

  const pick = async (file) => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      ctx.loadSpaces(await airsizer.load(file))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="split">
      <div className="col">
        <div className="muted">Welcome to</div>
        <h1 className="h1">AirSizer <span style={{ color: 'var(--green)' }}>Pro</span></h1>
        <div style={{ color: 'var(--green)', fontSize: 10 }}>▬ ▪</div>
        <div className="muted" style={{ whiteSpace: 'pre-line' }}>
          {'Design and size air distribution systems\nwith catalog-based diffuser selection,\nperformance checks and clear project results.'}
        </div>
        <div className="hero-slot">
          <HeroImage
            src="/airsizer-home.jpg"
            alt="Duct network with airflow and performance readouts"
            fallback={DuctArt}
          />
        </div>
        <div className="feature-band">
          {FEATURES.map((f) => <div key={f}>{f}</div>)}
        </div>
      </div>

      <div className="col">
        <h2 className="h2">Quick Start</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <QuickCard
            glyph="▦" title="Size Diffusers"
            body="Select catalog products and check performance."
            enabled={!busy} onClick={() => input.current?.click()}
          />
          <QuickCard
            glyph="◷" title="Review Results"
            body="Compare throw, pressure, airflow and noise limits."
            enabled={ctx.spaces.length > 0} onClick={() => ctx.setPage('air-review')}
          />
        </div>
        <input
          ref={input} type="file" accept=".xlsx,.csv" style={{ display: 'none' }}
          onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }}
        />
        {busy && <div className="muted">Reading schedule…</div>}
        {error && <div className="banner-fail">{error}</div>}

        <h2 className="h2">Recent Projects</h2>
        <RecentPanel
          module={AIRSIZER}
          refreshKey={ctx.recentsKey}
          onOpen={ctx.openSizing}
          emptyText="No sizing sessions yet — size some diffusers and export"
        />

        <div className="help-card">
          <h4 className="grow" style={{ margin: 0, fontSize: 13 }}>AirSizer Pro — how sizing works</h4>
          <button className="btn-ghost" onClick={() => setHelp(true)}>Open →</button>
        </div>
      </div>

      {help && (
        <Modal title="How AirSizer Pro sizes" onClose={() => setHelp(false)} width={560}>
          <ol className="muted" style={{ lineHeight: 1.8, paddingLeft: 18 }}>
            <li>Load the schedule HAPExt produced (.xlsx or .csv).</li>
            <li>For each subspace, pick a diffuser type — only the inputs that type takes stay enabled.</li>
            <li>
              Sizing reads the TECNALCO catalog. A value read between two catalog entries is flagged as
              interpolated; inputs no cell can satisfy report no valid selection rather than a guess.
            </li>
            <li>Review the roll-up, choose the columns you want, and export.</li>
          </ol>
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button className="btn btn-primary" onClick={() => setHelp(false)}>Close</button>
          </div>
        </Modal>
      )}
    </div>
  )
}
