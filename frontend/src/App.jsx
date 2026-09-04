// The MAEC shell: title bar, product tabs, and the page stack — the web
// equivalent of hap_converter/ui/app_window.py's QStackedWidget.
//
// All session state lives here and is handed down as `ctx`, the same shape
// the desktop pages receive. Nothing is persisted server-side (see §4 of the
// migration brief): a sizing run happens in one sitting and the exported
// workbook is the artifact.

import { useCallback, useEffect, useState } from 'react'
import { SESSION_EXPIRED, airsizer as airApi, auth as authApi } from './api'
import Launcher from './Launcher.jsx'
import Login from './Login.jsx'
import { AIRSIZER, HAPEXT, save as saveRecent } from './recents'

import HapHome from './hapext/Home.jsx'
import HapUpload from './hapext/Upload.jsx'
import HapConvert from './hapext/Convert.jsx'
import HapResult from './hapext/Result.jsx'
import HapFailure from './hapext/Failure.jsx'
import ChangeRequest from './hapext/ChangeRequest.jsx'
import ChangeReview from './hapext/ChangeReview.jsx'

import AirHome from './airsizer/Home.jsx'
import AirUpload from './airsizer/Upload.jsx'
import AirWizard from './airsizer/Wizard.jsx'
import AirReview from './airsizer/Review.jsx'

const TABS = ['HAPExt', 'AirSizer Pro', 'HAPAudit']
const VERSION = '1.2'

export default function App() {
  const [tab, setTab] = useState('HAPExt')
  const [page, setPage] = useState('hap-home')

  // null while we ask the server; then {enabled, authenticated, name, email}
  const [session, setSession] = useState(null)

  // Signed in, but still on the MAEC One launcher rather than inside a
  // module. Reaching a module is always a deliberate choice, so this starts
  // false on every sign-in and on every reload of an existing session.
  const [opened, setOpened] = useState(false)

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

  // bumped whenever something is written to history, so the panels re-read
  const [recentsKey, setRecentsKey] = useState(0)

  // Ask who we are first; only then load anything the guard protects.
  useEffect(() => {
    authApi.me()
      .then(setSession)
      .catch(() => setSession({ enabled: true, authenticated: false }))
  }, [])

  useEffect(() => {
    if (!session?.authenticated) return
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
      setOpened(false)   // sign in again and you land on the launcher, not mid-module
      setSession((s) => ({ ...(s || {}), enabled: true, authenticated: false }))
    }
    window.addEventListener(SESSION_EXPIRED, expired)
    return () => window.removeEventListener(SESSION_EXPIRED, expired)
  }, [])

  const signOut = async () => {
    try { await authApi.logout() } catch { /* the cookie goes either way */ }
    setOpened(false)
    setSession({ enabled: true, authenticated: false })
    setConversion(null); setDetails(null); setLogo(null); setChangeResult(null)
    setSpaces([]); setSizingInputs({}); setResults({})
    setPage('hap-home'); setTab('HAPExt')
  }

  const goTab = (name) => {
    if (name === 'HAPAudit') return
    setTab(name)
    setPage(name === 'HAPExt' ? 'hap-home' : 'air-home')
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
    setTab('AirSizer Pro')
    setPage('air-wizard')
  }, [])

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
    setTab('HAPExt')
    setPage('hap-result')
  }, [])

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
    setTab('AirSizer Pro')
    setPage('air-wizard')
  }, [])

  const ctx = {
    // navigation
    page, setPage, tab, setTab: goTab,
    // HAPExt
    pdf, setPdf, conversion, setConversion,
    details, setDetails, logo, setLogo,
    changeResult, setChangeResult,
    // AirSizer
    airConfig, airError, spaces, sizingInputs, results,
    airSource, airBaseName, visibleColumns, setVisibleColumns,
    recordSizing, loadSpaces,
    // history
    recentsKey, rememberConversion, openConversion, rememberSizing, openSizing,
  }

  const pages = {
    'hap-home': HapHome,
    'hap-upload': HapUpload,
    'hap-convert': HapConvert,
    'hap-result': HapResult,
    'hap-failure': HapFailure,
    'hap-change': ChangeRequest,
    'hap-change-review': ChangeReview,
    'air-home': AirHome,
    'air-upload': AirUpload,
    'air-wizard': AirWizard,
    'air-review': AirReview,
  }
  const Page = pages[page] || HapHome

  if (session === null) {
    return <div className="shell" style={{ alignItems: 'center', justifyContent: 'center' }}>
      <span className="muted">Loading…</span>
    </div>
  }
  if (session.enabled && !session.authenticated) {
    return <Login onSignedIn={(who) => setSession({ ...who, authenticated: true })} />
  }

  if (!opened) {
    return (
      <Launcher
        name={session.name}
        email={session.email}
        onOpen={() => { setTab('HAPExt'); setPage('hap-home'); setOpened(true) }}
        onSignOut={signOut}
      />
    )
  }

  return (
    <div className="shell">
      <div className="titlebar">
        <button
          className="titlebar-home"
          title="Back to MAEC One"
          onClick={() => setOpened(false)}
        >
          <img className="titlebar-logo" src="/maec-logo.png" alt="MAEC" />
        </button>
        <span className="version">v{VERSION}</span>
        {session.enabled && (
          <>
            <span className="grow" />
            <button className="btn-ghost" onClick={signOut}>Sign out</button>
          </>
        )}
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
              onClick={() => goTab(name)}
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
