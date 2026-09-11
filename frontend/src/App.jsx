// The MAEC shell.
//
// Three areas live under one address bar, and this file routes between them:
//
//   /            the sign-in screen, until we know who you are
//   /home        the MAEC One launcher — the products you hold a seat on
//   /admin/*     Global Admin (MAEC One Core)
//   everything   Engineering Tools, whose own page-state machine is
//   else         unchanged and simply mounted under these routes
//
// All Engineering Tools session state lives here and is handed down as
// `ctx`, the same shape the desktop pages received. Nothing is persisted
// server-side: a sizing run happens in one sitting and the exported workbook
// is the artifact.
//
// Where you land after signing in — and which tiles are openable — is
// decided by the server, not here. Every one of these routes is a
// convenience; the API refuses what this person may not do regardless of
// what the browser renders.

import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import { airsizer as airApi } from './api'
import Launcher from './maecone/Launcher.jsx'
import ChangePassword from './maecone/ChangePassword.jsx'
import Login from './maecone/Login.jsx'
import AdminShell from './maecone/admin/AdminShell.jsx'
import { SESSION_EXPIRED, auth as authApi } from './maecone/api'
import { INTERNAL } from './maecone/MaecOne.jsx'
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

/** Where a signed-in person belongs when they have not asked for anywhere. */
const homeFor = (session) => (session?.is_global_admin ? '/admin' : '/home')

const entitledTo = (session, key) =>
  !!(session?.apps || []).find((app) => app.key === key && app.entitled)


// ------------------------------------------------------- Engineering Tools
function EngineeringTools({ ctx, session, onSignOut, airConfig, airError }) {
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

  if (!page) return <Navigate to={homeFor(session)} replace />

  const tab = TAB_OF[page] || 'HAPExt'
  const Page = PAGES[page] || HapHome

  return (
    <div className="shell">
      <div className="titlebar">
        <button
          className="titlebar-home"
          title="Back to MAEC One"
          onClick={() => navigate('/home')}
        >
          <img className="titlebar-logo" src="/maec-logo.png" alt="MAEC" />
        </button>
        <span className="version">v{VERSION}</span>
        <span className="grow" />
        {session?.is_global_admin && (
          <button className="btn-ghost" onClick={() => navigate('/admin')}>
            Global Admin
          </button>
        )}
        <button className="btn-ghost" onClick={onSignOut}>Sign out</button>
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
  const location = useLocation()

  // null while we ask the server; then the payload from GET /api/auth/me
  const [session, setSession] = useState(null)

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

  // Ask who we are first; only then load anything the guard protects.
  useEffect(() => {
    authApi.me()
      .then(setSession)
      .catch(() => setSession({ authenticated: false, apps: [] }))
  }, [])

  useEffect(() => {
    if (!session?.authenticated) return
    if (!entitledTo(session, INTERNAL)) return   // no seat: do not even ask
    airApi.config()
      .then((cfg) => {
        setAirConfig(cfg)
        setVisibleColumns(cfg.result_columns.filter((c) => c.default).map((c) => c.key))
      })
      .catch((err) => setAirError(err.message))
  }, [session?.authenticated])

  // A lapsed session anywhere in the app drops straight back to the login
  useEffect(() => {
    const expired = () => {
      setSession({ authenticated: false, apps: [] })
      navigate('/', { replace: true })
    }
    window.addEventListener(SESSION_EXPIRED, expired)
    return () => window.removeEventListener(SESSION_EXPIRED, expired)
  }, [navigate])

  const signOut = async () => {
    try { await authApi.logout() } catch { /* the cookie goes either way */ }
    setSession({ authenticated: false, apps: [] })
    setConversion(null); setDetails(null); setLogo(null); setChangeResult(null)
    setSpaces([]); setSizingInputs({}); setResults({})
    setAirConfig(null)
    setWarm(false)
    navigate('/', { replace: true })
  }

  const signedIn = (who) => {
    setSession(who)
    navigate(homeFor(who), { replace: true })
  }

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

  if (session === null) {
    return (
      <div className="shell" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="muted">Loading…</span>
      </div>
    )
  }

  // An administrator set this password, so the server refuses every call
  // but /api/auth/*. There is nowhere else to send them until it is theirs.
  if (session.must_change_password) {
    return (
      <ChangePassword
        session={session}
        onChanged={(who) => { setSession(who); navigate(homeFor(who), { replace: true }) }}
        onSignOut={signOut}
      />
    )
  }

  if (!session.authenticated) {
    // The sign-in screen is the only thing at any address until we know who
    // you are — a deep link is answered by the login form, and the API would
    // refuse the request behind it in any case.
    return (
      <>
        {location.pathname !== '/' && <Navigate to="/" replace />}
        <Login apps={session.apps} onSignedIn={signedIn} />
      </>
    )
  }

  return (
    <Routes>
      <Route path="/" element={<Navigate to={homeFor(session)} replace />} />

      <Route path="/home" element={
        <Launcher
          session={session}
          onOpen={() => setPage(HOME_OF['HAPExt'])}
          onAdmin={() => navigate('/admin')}
          onSignOut={signOut}
        />
      } />

      {/* Convenience only: require_global_admin refuses /api/admin/* to
          anyone else, so a non-admin who types this URL gets an empty shell
          and 403s from every call it makes. */}
      <Route path="/admin/*" element={
        session.is_global_admin
          ? <AdminShell session={session} onSignOut={signOut} />
          : <Navigate to="/home" replace />
      } />

      {/* Engineering Tools. Without a seat the product API answers 403, so
          there is nothing to show — go back to the launcher. */}
      <Route path="*" element={
        entitledTo(session, INTERNAL)
          ? <EngineeringTools
              ctx={ctx} session={session} onSignOut={signOut}
              airConfig={airConfig} airError={airError}
            />
          : <Navigate to="/home" replace />
      } />
    </Routes>
  )
}
