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
// Who the user is comes from MAEC One Core. The server asks Core about the
// browser's MAEC One cookie on every request, and sends a signed-out browser
// to Core's sign-in before this bundle even loads. On load this asks
// /api/auth/me for the name and the tabs; a 401 there means the person signed
// out at MAEC One meanwhile, and the window goes to the login_url it carries.

import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import { airsizer as airApi, auth, reauthorize } from './api'
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

// Which module in Core's registry each tab belongs to. The backend decides
// whether a tab is shown — it runs the tool rules through the same engine
// Core does — and this is only the name it answers under.
const MODULE_OF = {
  'HAPExt': 'hapext',
  'AirSizer Pro': 'airsizer',
  'HAPAudit': 'hapaudit',
  'PDF Rebadging': 'rebadge',
}

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
function EngineeringTools({ ctx, airConfig, airError, modules, coreUrl }) {
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
        <img className="titlebar-logo" src="/maec-logo.png" alt="MAEC" />
        <span className="version">v{VERSION}</span>
        <span className="grow" />
        {/* Signing out happens at MAEC One, and signs the person out of every
            app at once — this product holds no session of its own to end. */}
        {coreUrl && (
          <a className="btn-ghost" href={coreUrl} title="Sign out at MAEC One">Sign out</a>
        )}
      </div>

      <div className="tabbar">
        {/* A module Core lists in nav_hidden, or one the person may not view,
            is not offered. That is decluttering, not the boundary: the server
            refuses a route whose permission the person lacks whatever is
            rendered here. See maec_auth/guard.py. */}
        {TABS.filter((name) => modules?.[MODULE_OF[name]] !== false).map((name) => {
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

  // null while we are asking; then the answer from GET /api/auth/me, or a
  // refusal we could not recover from.
  const [session, setSession] = useState(null)

  useEffect(() => {
    auth.me()
      .then((who) => {
        if (who.authenticated) { setSession(who); return }
        // MAEC One no longer knows this browser. One trip to its sign-in, and
        // back. If we have already been sent once this visit, stop and say so
        // rather than bouncing between two services.
        if (!reauthorize(who.login_url)) {
          setSession({ authenticated: false, refused: true })
        }
      })
      .catch((err) => setSession({ authenticated: false, refused: true, error: err.message }))
  }, [])

  // Asked once there is a session: a 401 sends the window to sign-in, so
  // asking before /api/auth/me has answered could leave the page for nothing.
  useEffect(() => {
    if (!session?.authenticated) return
    airApi.config()
      .then((cfg) => {
        setAirConfig(cfg)
        setVisibleColumns(cfg.result_columns.filter((c) => c.default).map((c) => c.key))
      })
      .catch((err) => setAirError(err.message))
  }, [session?.authenticated])

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

  // The sign-in screen, the launcher and Global Admin are MAEC One's. The
  // server's gate stands in front of this bundle, so by the time it runs the
  // person is signed in; these two states cover asking, and a sign-out that
  // happened since.
  if (session === null) {
    return (
      <div className="shell" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="muted">Signing you in…</span>
      </div>
    )
  }

  if (!session.authenticated) {
    // Reached only when one trip to MAEC One's sign-in did not bring the
    // browser back signed in. The way back is a click, never an automatic
    // redirect — that is what keeps a refusal from becoming a loop.
    return (
      <div className="shell" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div className="card col" style={{ padding: '28px 32px', maxWidth: 460 }}>
          <h2 className="h2">You are not signed in to Engineering Tools</h2>
          <div className="small">
            {session.error
              || 'MAEC One did not sign this browser in. Open MAEC One, sign in '
                 + 'there, then come back.'}
          </div>
          <a className="btn btn-primary" href="/">Try again</a>
        </div>
      </div>
    )
  }

  return (
    <Routes>
      <Route path="*" element={
        <EngineeringTools ctx={ctx} airConfig={airConfig} airError={airError}
                          modules={session.modules} coreUrl={session.core_url} />
      } />
    </Routes>
  )
}
