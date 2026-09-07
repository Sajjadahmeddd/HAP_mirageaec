// PDF Rebadging home — hero on the left, Quick Start and history on the right.
// Built to "PDF Rebadging landing(first) page.png".
//
// "Create Rebadging Template" is drawn because the design has it, and
// disabled because templates are not built: a card that looked live and did
// nothing would be worse than one that says so.

import { useState } from 'react'
import { Modal } from '../components.jsx'
import { HeroImage } from '../HeroArt.jsx'
import RecentPanel from '../RecentPanel.jsx'
import { REBADGE } from '../recents'

const FEATURES = ['Batch\nProcessing', 'Branding\nConsistency',
                  'Metadata\nAlignment', 'Drawing\nPreservation']

function QuickCard({ glyph, title, body, enabled, onClick, note }) {
  return (
    <div
      className="card"
      style={{ padding: '18px 18px 16px', cursor: enabled ? 'pointer' : 'not-allowed',
               opacity: enabled ? 1 : 0.55 }}
      title={enabled ? title : note}
      onClick={() => enabled && onClick()}
    >
      <div className="quick-icon" style={{ marginBottom: 10 }}>{glyph}</div>
      <div className="h2">{title}</div>
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <p className="small grow" style={{ margin: '6px 0 0' }}>
          {enabled ? body : `${body}  (coming soon)`}
        </p>
        <span className="h2">→</span>
      </div>
    </div>
  )
}

/** Stands in for the supplied artwork if it is ever missing, so the home
 *  screen still reads rather than showing a broken image. */
function RebadgeArt() {
  return (
    <svg viewBox="0 0 420 190" style={{ width: '100%', maxHeight: 210 }} aria-hidden="true">
      <rect x="8" y="18" width="196" height="154" rx="8" fill="#fff" stroke="#C9D3AE" />
      <g stroke="#C9CBD2" strokeWidth="3" strokeLinecap="round">
        <path d="M32 52h118M32 74h140M32 96h104M32 118h126" />
      </g>
      <g stroke="#8DA55F" strokeWidth="1" fill="none">
        <rect x="120" y="128" width="72" height="32" />
        <path d="M120 140h72M156 128v32" />
      </g>
      <path d="M222 95h44" stroke="#6E8B23" strokeWidth="2" />
      <path d="m262 89 10 6-10 6z" fill="#6E8B23" />
      <rect x="286" y="62" width="126" height="66" rx="8" fill="#fff" stroke="#C9D3AE" />
      <text x="349" y="92" textAnchor="middle" fontSize="13" fontWeight="700" fill="#141B4D">
        REBADGE
      </text>
      <text x="349" y="108" textAnchor="middle" fontSize="8" fill="#8A8D98">
        Title Block • Revision
      </text>
    </svg>
  )
}

export default function Home({ ctx }) {
  const [help, setHelp] = useState(false)

  return (
    <div className="split">
      <div className="col">
        <div className="muted">Welcome to</div>
        <h1 className="h1">PDF <span style={{ color: 'var(--green)' }}>Rebadging</span></h1>
        <div style={{ color: 'var(--green)', fontSize: 10 }}>▬ ▪</div>
        <div className="muted" style={{ whiteSpace: 'pre-line' }}>
          {'Update drawing branding, title blocks and PDF metadata\nacross complete AEC drawing packages without changing\nthe underlying technical drawing content.'}
        </div>
        <div className="hero-slot">
          <HeroImage
            src="/rebadging-home.jpg"
            alt="A drawing sheet before and after rebadging: updated branding, metadata and title block, with the drawing itself unchanged"
            fallback={RebadgeArt}
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
            glyph="▤" title="Start Rebadging"
            body="Import a drawing set and start branding and title block updates."
            enabled onClick={() => ctx.setPage('rebadge-wizard')}
          />
          <QuickCard
            glyph="▦" title="Create Rebadging Template"
            body="Define reusable logo, title block and metadata replacement rules."
            enabled={false}
            note="Templates are not built yet"
          />
        </div>

        <h2 className="h2">Recent Projects</h2>
        <RecentPanel
          module={REBADGE}
          refreshKey={ctx.recentsKey}
          onOpen={() => ctx.setPage('rebadge-wizard')}
          emptyText="No rebadging projects yet — import a drawing set to begin"
        />

        <div className="help-card">
          <h4 className="grow" style={{ margin: 0, fontSize: 13 }}>
            PDF Rebadging — how it works
          </h4>
          <button className="btn-ghost" onClick={() => setHelp(true)}>Open →</button>
        </div>
      </div>

      {help && (
        <Modal title="How PDF Rebadging works" onClose={() => setHelp(false)} width={580}>
          <ol className="muted" style={{ lineHeight: 1.8, paddingLeft: 18 }}>
            <li>Import one or many A1 drawing sheets exported from your CAD tool.</li>
            <li>
              Each sheet is checked: the title block must be found by its printed
              labels, and the revision table must have a blank row to grow into.
            </li>
            <li>
              Give the six values once. They are applied to every sheet — that is
              what rebadging a submission set means.
            </li>
            <li>
              Project Stage and Sheet Status are replaced in place: the old text is
              removed from the file, not painted over. The revision history gains a
              new row above the newest one; nothing already there is touched.
            </li>
            <li>
              The drawing itself is never edited, and your originals are never
              overwritten — every sheet comes back as a new file, with an audit
              record of what was applied.
            </li>
          </ol>
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button className="btn btn-primary" onClick={() => setHelp(false)}>Close</button>
          </div>
        </Modal>
      )}
    </div>
  )
}
