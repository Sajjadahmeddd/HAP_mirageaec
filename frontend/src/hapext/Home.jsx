import { BuildingArt } from '../HeroArt.jsx'

// HAPExt home — hero + feature band on the left, Quick Start on the right.
// Ported from hap_converter/ui/pages/home_page.py.

const FEATURES = ['Accurate\nCalculations', 'Smart\nAutomation', 'Seamless\nIntegration', 'Reliable\nResults']

function QuickCard({ glyph, colour, title, body, enabled, onClick }) {
  return (
    <div
      className="card"
      style={{ padding: '16px 16px 14px', cursor: enabled ? 'pointer' : 'not-allowed', opacity: enabled ? 1 : 0.55 }}
      onClick={() => enabled && onClick()}
    >
      <div style={{
        background: colour, color: '#fff', borderRadius: 10, width: 44, height: 44,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 20, fontWeight: 800, marginBottom: 8,
      }}>{glyph}</div>
      <div className="h2">{title}</div>
      <p className="small" style={{ margin: '6px 0' }}>{enabled ? body : `${body}  (coming soon)`}</p>
      <div className="h2" style={{ textAlign: 'right' }}>→</div>
    </div>
  )
}

export default function Home({ ctx }) {
  return (
    <div className="split">
      <div className="col">
        <div className="muted">Welcome to</div>
        <h1 className="h1">Mirage <span style={{ color: 'var(--blue)' }}>AEC</span></h1>
        <div style={{ color: 'var(--blue)', fontSize: 10 }}>▬ ▪</div>
        <div className="muted" style={{ whiteSpace: 'pre-line' }}>
          {'Powerful tools for HVAC design and analysis.\nSimplify your workflow with intelligent\nautomation and precise calculations.'}
        </div>
        <div className="grow" style={{ display: 'flex', alignItems: 'center' }}><BuildingArt /></div>
        <div className="feature-band">
          {FEATURES.map((f) => <div key={f}>{f}</div>)}
        </div>
      </div>

      <div className="col">
        <h2 className="h2">Quick Start</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <QuickCard
            glyph="≋" colour="var(--blue)" title="HAPExt"
            body="Load, analyze and optimize HAP models with ease."
            enabled onClick={() => ctx.setPage('hap-upload')}
          />
          <QuickCard
            glyph="▦" colour="#3AA655" title="AirSizer Pro"
            body="Design and analyze duct systems efficiently."
            enabled={!!ctx.airConfig} onClick={() => ctx.setTab('AirSizer Pro')}
          />
        </div>

        <div className="panel-card" style={{ padding: '16px 18px', flex: 1 }}>
          <div className="row" style={{ marginBottom: 6 }}>
            <h2 className="h2 grow">Recent Projects</h2>
          </div>
          <div className="muted" style={{ textAlign: 'center', padding: '24px 0' }}>
            Conversion history is not kept on the server
          </div>
        </div>
      </div>
    </div>
  )
}
