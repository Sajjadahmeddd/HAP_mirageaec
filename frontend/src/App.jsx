// The Engineering Tools shell.
//
// This file used to route between three areas: the sign-in screen, the MAEC
// One launcher, and Global Admin — with Engineering Tools mounted underneath
// them. The first three were MAEC One Core's and have moved to their own
// service. What is left is the product, now mounted at the root.
//
// All Engineering Tools session state lives here and is handed down as
// `ctx`, the same shape the desktop pages received. Nothing is persisted
// server-side: a sizing run happens in one sitting and the exported workbook
// is the artifact. That part is untouched.
//
// WHAT IS MISSING, deliberately and temporarily: there is no sign-in, and
// nothing here asks who the user is. The API does not ask either — see the
// block in backend/main.py. When the OIDC client lands, this file regains a
// /auth/callback route and the titlebar regains its two controls; until then
// it renders the tools to whoever opens the page.

import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import { airsizer as airApi } from './api'
import { AIRSIZER, HAPEXT, save as saveRecent } from './recents'
import { ENTRY_POINTS, HOME_OF, TAB_OF, pageOf, pathOf } from './routes'

import HapHome from './hapext/Home.jsx'
import HapUpload from './hapext/Upload.jsx'
import HapConvert from './hapext/Convert.jsx'
import HapResult from './hapext/Result.jsx'
import HapFailure from './hapext/Failure.jsx'
import ChangeRequest from './hapext/ChangeRequest.jsx'
import ChangeReview from './hapext/ChangeReview.jsx'

import RebadgeHome from './rebadge/Home.jsx'
import RebadgeWizard from './rebadge/Wizard.jsx'
import AirHome from './airsizer/Home.jsx'
import AirUpload from './airsizer/Upload.jsx'
import AirWizard from './airsizer/Wizard.jsx'
import AirReview from './airsizer/Review.jsx'

const TABS = ['HAPExt', 'AirSizer Pro', 'HAPAudit', 'PDF Rebadging']
const VERSION = '1.2'

const PAGES = {
  'hap-home': HapHome,
  'hap-upload': HapUpload,
  'hap-convert': HapConvert,
  'hap-result': HapResult,
  'hap-failure': HapFailure,
  'hap-change': ChangeRequest,
  'hap-change-review': ChangeReview,
  'rebadge-home': RebadgeHome,
  'rebadge-wizard': RebadgeWizard,
  'air-home': AirHome,
  'air-upload': AirUpload,
  'air-wizard': AirWizard,
  'air-review': AirReview,
}

// ------------------------------------------------------- Engineering Tools
function EngineeringTools({ ctx, airConfig, airError }) {
  const location = useLocation()
  const navigate = useNavigate()
  const page = pageOf(location.pathname)

  // A cold load of a mid-session screen would render an empty shell, because
  // the conversion or sizing run it needs lives only in memory. Send it to
  // the module's home instead; Back and Forward still reach it in-session.
  useEffect(() => {
    if (page && !ENTRY_POINTS.has(page) && !ctx.warm) {
      navigate(pathOf(HOME_OF[TAB_OF[page]]), { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!page) return <Navigate to={pathOf(HOME_OF['HAPExt'])} replace />

  const tab = TAB_OF[page] || 'HAPExt'
  const Page = PAGES[page] || HapHome

  return (
    <div className="shell">
      <div className="titlebar">
        {/* Three controls stood here and all three acted on a session: the
            logo returned to the MAEC One launcher, "Global Admin" opened the
            admin shell, and "Sign out" ended the session. All three are
            Core's now, and a button that cannot do what it says is worse
            than no button — so the logo is a plain mark until the OIDC
            client gives it somewhere real to go. */}
        <img className="titlebar-logo" src="/maec-logo.png" alt="MAEC" />
        <span className="version">v{VERSION}</span>
        <span className="grow" />
      </div>

      <div className="tabbar">
        {TABS.map((name) => {
          const disabled = name === 'HAPAudit' || (name === 'AirSizer Pro' && !airConfig)
          return (
            <button
              key={name}
              className={`tab${tab === name ? ' active' : ''}`}
              disabled={disabled}
              title={
                name === 'HAPAudit' ? 'Coming soon'
                  : (name === 'AirSizer Pro' && !airConfig)
                    ? (airError || 'Loading catalogs…')
                    : `Go to the ${name} home screen`
              }
              onClick={() => navigate(pathOf(HOME_OF[name] || 'hap-home'))}
            >
              {name}
            </button>
          )
        })}
      </div>

      <div className="page">
        <Page ctx={ctx} />
      </div>
    </div>
  )
}


// ------------------------------------------------------------------- shell
export default function App() {
  const navigate = useNavigate()

  // ---- HAPExt session
  const [pdf, setPdf] = useState(null)          // {file, name, pages, size}
  const [conversion, setConversion] = useState(null) // convert() response
  const [details, setDetails] = useState(null)  // the 8 mandatory fields
  const [logo, setLogo] = useState(null)        // File
  const [changeResult, setChangeResult] = useState(null)

  // ---- AirSizer session
  const [airConfig, setAirConfig] = useState(null)
  const [airError, setAirError] = useState('')
  const [spaces, setSpaces] = useState([])
  const [sizingInputs, setSizingInputs] = useState({})  // row -> {diffuser, values}
  const [results, setResults] = useState({})            // row -> SizingResult
  const [airSource, setAirSource] = useState('')
  const [airBaseName, setAirBaseName] = useState('')
  const [visibleColumns, setVisibleColumns] = useState(null)
  // the nine project inputs for the sizing sheet, and what the loaded
  // schedule already carried — the source the dialog's import button reads
  const [airDetails, setAirDetails] = useState(null)
  const [airLogo, setAirLogo] = useState(null)
  const [airImported, setAirImported] = useState(null)

  // bumped whenever something is written to history, so the panels re-read
  const [recentsKey, setRecentsKey] = useState(0)

  // True once this session has navigated within the app, so a deep screen is
  // known to have the state it needs rather than being a cold URL.
  const [warm, setWarm] = useState(false)

  const setPage = useCallback((name) => {
    setWarm(true)
    navigate(pathOf(name))
  }, [navigate])

  // Asked unconditionally now. It used to wait for GET /api/auth/me and
  // then for a seat on Engineering Tools, so that an unentitled person never
  // made a call the guard would refuse. There is no seat to check and no
  // guard to refuse it.
  useEffect(() => {
    airApi.config()
      .then((cfg) => {
        setAirConfig(cfg)
        setVisibleColumns(cfg.result_columns.filter((c) => c.default).map((c) => c.key))
      })
      .catch((err) => setAirError(err.message))
  }, [])

  const recordSizing = useCallback((row, diffuser, values, result) => {
    setSizingInputs((prev) => ({ ...prev, [row]: { diffuser, values } }))
    setResults((prev) => ({ ...prev, [row]: result }))
  }, [])

  const loadSpaces = useCallback((payload) => {
    setSpaces(payload.spaces)
    setAirSource(payload.source)
    setAirBaseName(payload.base_name)
    setSizingInputs({})
    setResults({})
    // What this schedule already carries, kept so the details dialog can
    // offer it. Held, not applied: the engineer decides whether to import.
    const found = payload.details && Object.keys(payload.details).length
      ? { details: payload.details, logo: payload.logo
            ? { name: 'Client logo (from schedule)', dataUrl: payload.logo }
            : null }
      : null
    setAirImported(found)
    setAirDetails(null)
    setAirLogo(null)
    setPage('air-wizard')
  }, [setPage])

  // ---- history (browser-local; see recents.js)
  const rememberConversion = useCallback((data) => {
    saveRecent(HAPEXT, {
      name: data.source,
      summary: `${data.stats?.units ?? 0} units • ${data.stats?.spaces ?? 0} spaces`,
      payload: {
        header: data.header, rows: data.rows,
        stats: data.stats, source: data.source, base_name: data.base_name,
      },
    })
    setRecentsKey((k) => k + 1)
  }, [])

  const openConversion = useCallback((entry) => {
    setConversion({ ok: true, issues: [], ...entry.payload })
    setPdf(null)                       // the original file is not kept
    setPage('hap-result')
  }, [setPage])

  /** Called from the AirSizer review screen once a session is worth keeping. */
  const rememberSizing = useCallback(() => {
    if (!spaces.length) return
    const sized = Object.values(results).filter((r) => r.ok).length
    saveRecent(AIRSIZER, {
      name: airSource || airBaseName || 'Sizing session',
      summary: `${sized} of ${spaces.filter((s) => s.sizable).length} subspaces sized`,
      payload: {
        spaces, sizingInputs, results,
        source: airSource, baseName: airBaseName, visibleColumns,
      },
    })
    setRecentsKey((k) => k + 1)
  }, [spaces, results, sizingInputs, airSource, airBaseName, visibleColumns])

  const openSizing = useCallback((entry) => {
    const p = entry.payload
    setSpaces(p.spaces || [])
    setSizingInputs(p.sizingInputs || {})
    setResults(p.results || {})
    setAirSource(p.source || '')
    setAirBaseName(p.baseName || '')
    if (p.visibleColumns) setVisibleColumns(p.visibleColumns)
    setPage('air-wizard')
  }, [setPage])

  const ctx = {
    // navigation
    setPage, warm,
    setTab: (name) => setPage(HOME_OF[name] || 'hap-home'),
    // HAPExt
    pdf, setPdf, conversion, setConversion,
    details, setDetails, logo, setLogo,
    changeResult, setChangeResult,
    // AirSizer
    airConfig, airError, spaces, sizingInputs, results,
    airSource, airBaseName, visibleColumns, setVisibleColumns,
    airDetails, setAirDetails, airLogo, setAirLogo, airImported,
    recordSizing, loadSpaces,
    // history
    recentsKey, rememberConversion, openConversion, rememberSizing, openSizing,
    bumpRecents: () => setRecentsKey((n) => n + 1),
  }

  // Three gates stood here — a loading state while GET /api/auth/me
  // answered, the forced password change, and the sign-in screen — followed
  // by routes for the launcher and Global Admin. All of it was Core's.
  //
  // Engineering Tools is now mounted at the root with nothing in front of
  // it. The route table is a single entry on purpose: adding a redirect to
  // Core here would look like authentication without being any, and this
  // branch is clearer being visibly open than subtly so.
  return (
    <Routes>
      <Route path="*" element={
        <EngineeringTools ctx={ctx} airConfig={airConfig} airError={airError} />
      } />
    </Routes>
  )
}
