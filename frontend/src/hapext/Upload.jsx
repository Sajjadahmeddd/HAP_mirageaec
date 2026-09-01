// HAPExt upload — New Project / Change Request radios, drop zone, and the
// two-step Upload → Convert action pair from upload_page.py.

import { useState } from 'react'
import { hapext } from '../api'
import { DropZone, INFO_CARDS, InfoCard, formatMb } from '../components.jsx'

export default function Upload({ ctx }) {
  const [picked, setPicked] = useState(null)
  const [info, setInfo] = useState(null)      // {name, pages, size} once uploaded
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const onPick = (file) => {
    setPicked(file)
    setInfo(null)
    setError('')
    ctx.setPdf(null)
    ctx.setConversion(null)
  }

  const upload = async () => {
    if (!picked) return
    setBusy(true)
    setError('')
    try {
      const meta = await hapext.inspect(picked)
      setInfo(meta)
      ctx.setPdf({ file: picked, ...meta })
    } catch (err) {
      setError(err.message)
      setInfo(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="split">
      <div className="card col" style={{ padding: '18px 24px' }}>
        <div className="radios" style={{ marginBottom: 14 }}>
          <label>
            <input type="radio" checked readOnly /> New Project
          </label>
          <label onClick={() => ctx.setPage('hap-change')}>
            <input type="radio" checked={false} readOnly /> Change Request
          </label>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '11fr 8fr', gap: 22, flex: 1, minHeight: 0 }}>
          <DropZone
            accept={['.pdf']}
            prompt="Drop your PDF here"
            hint="*Upload only .pdf"
            file={picked}
            meta={info ? `${formatMb(info.size)} • ${info.pages} pages` : picked ? formatMb(picked.size) : ''}
            error={error}
            onFile={onPick}
          />

          <div className="col" style={{ justifyContent: 'center' }}>
            <button className="btn btn-primary" disabled={!picked || busy} onClick={upload}>
              {busy ? 'Checking…' : 'Upload'}
            </button>
            <button
              className="btn btn-secondary"
              disabled={!info}
              onClick={() => ctx.setPage('hap-convert')}
            >
              ⊞  Convert CSV
            </button>
            <div className="small">Output: chosen when you download</div>
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
            <li>Upload the merged HAP “System Design” PDF.</li>
            <li>Convert — every unit and space is extracted, values kept exactly as printed.</li>
            <li>If any mandatory value is missing, nothing is exported and the page + field is named.</li>
            <li>Fill the project details, then download as Excel or CSV.</li>
          </ol>
        </div>
        <div className="row">
          <span className="small">Need help?</span>
          <a className="btn-ghost" href="mailto:support@mirageinc.example">Contact Support</a>
        </div>
      </div>
    </div>
  )
}
