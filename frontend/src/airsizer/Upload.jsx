// AirSizer upload — the step between the home screen and the sizing wizard.
//
// Mirrors hapext/Upload.jsx: choose the schedule, upload it, then start.
// Picking a file used to open the wizard the moment the file dialog closed,
// which gave no chance to see what had been read or to change your mind.

import { useState } from 'react'
import { airsizer } from '../api'
import { DropZone, INFO_CARDS, InfoCard, formatMb } from '../components.jsx'

export default function Upload({ ctx }) {
  const [picked, setPicked] = useState(null)
  const [loaded, setLoaded] = useState(null)   // the response, once read
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const onPick = (file) => {
    setPicked(file)
    setLoaded(null)
    setError('')
  }

  // Read the schedule but stay put, so the counts can be checked before
  // committing to a sizing run.
  const upload = async () => {
    if (!picked) return
    setBusy(true)
    setError('')
    try {
      setLoaded(await airsizer.load(picked))
    } catch (err) {
      setError(err.message)
      setLoaded(null)
    } finally {
      setBusy(false)
    }
  }

  const start = () => {
    if (!loaded) return
    ctx.loadSpaces(loaded)      // this is what moves us to the wizard
  }

  const sizable = loaded?.spaces?.filter((s) => s.sizable).length ?? 0
  const meta = loaded
    ? `${formatMb(picked.size)} • ${sizable} subspaces to size`
    : picked ? formatMb(picked.size) : ''

  return (
    <div className="split">
      <div className="card col" style={{ padding: '18px 24px' }}>
        <h2 className="h2" style={{ marginBottom: 14 }}>Load a HAPExt schedule</h2>

        <div style={{ display: 'grid', gridTemplateColumns: '11fr 8fr', gap: 22, flex: 1, minHeight: 0 }}>
          <DropZone
            accept={['.xlsx', '.csv']}
            badge="XLS"
            prompt="Drop your schedule here"
            hint="*Upload only .xlsx or .csv"
            file={picked}
            meta={meta}
            error={error}
            onFile={onPick}
          />

          <div className="col" style={{ justifyContent: 'center' }}>
            <button className="btn btn-primary" disabled={!picked || busy} onClick={upload}>
              {busy ? 'Reading…' : 'Upload'}
            </button>
            <button className="btn btn-secondary" disabled={!loaded} onClick={start}>
              ⊞  Start Sizing
            </button>
            <div className="small">
              {loaded
                ? `${loaded.spaces.length} rows read from ${loaded.source}`
                : 'The schedule HAPExt produced, as .xlsx or .csv'}
            </div>
          </div>
        </div>

        <div className="row" style={{ gap: 14, alignItems: 'stretch' }}>
          {INFO_CARDS.map(([t, b]) => <InfoCard key={t} title={t} body={b} />)}
        </div>
      </div>

      <div className="col">
        <div className="panel-card" style={{ padding: '16px 18px' }}>
          <h2 className="h2">How it works</h2>
          <ol className="small" style={{ paddingLeft: 18, lineHeight: 1.9 }}>
            <li>Upload the schedule HAPExt produced (.xlsx or .csv).</li>
            <li>Pick a diffuser type per subspace — only the inputs that type takes stay enabled.</li>
            <li>
              Sizing reads the TECNALCO catalog. A value read between two entries is flagged as
              interpolated; inputs no cell can satisfy report no valid selection rather than a guess.
            </li>
            <li>Review the roll-up, choose your columns, then generate the workbook.</li>
          </ol>
        </div>
        <div className="row">
          <span className="small">Need help?</span>
          <a className="btn-ghost" href="mailto:support@mirageaec.com">Contact Support</a>
        </div>
      </div>
    </div>
  )
}
