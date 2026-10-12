// The MAEC shell: title bar, product tabs, and the page stack — the web
// equivalent of hap_converter/ui/app_window.py's QStackedWidget.
//
// All session state lives here and is handed down as `ctx`, the same shape
// the desktop pages receive. Nothing is persisted server-side (see §4 of the
// migration brief): a sizing run happens in one sitting and the exported
// workbook is the artifact.
//
// Sign-in is MAEC One Core's. The server asks Core about the browser's MAEC
// One cookie on every request; /api/auth/me says who this is and which tabs
// to show, and a 401 sends the window to Core's sign-in once (api.js). The
// sign-in screen and the launcher are Core's pages now: the logo and "Sign
// out" go there. Everything else here is the live app unchanged.

import { useCallback, useEffect, useState } from 'react'
import { airsizer as airApi, auth as authApi, reauthorize } from './api'
import { AIRSIZER, HAPEXT, save as saveRecent } from './recents'
import { HOME_OF, TAB_OF, landing, pathOf } from './routes'

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

// Which module in Core's registry each tab belongs to: /api/auth/me answers
// whether each is shown, from Core's nav_hidden and the person's permissions.
const MODULE_OF = {
  'HAPExt': 'hapext',
  'AirSizer Pro': 'airsizer',
  'HAPAudit': 'hapaudit',
  'PDF Rebadging': 'rebadge',
}

// The launcher is MAEC One's own page now, so where the live app showed it
// (`opened` false: the root, /home, an unknown path) this opens HAPExt.
const entry = (pathname) => {
  const found = landing(pathname)
  return found.opened ? found : { opened: true, page: HOME_OF['HAPExt'] }
}

export default function App() {
  // Where we are, read from the address bar so a refresh and a pasted link
  // both land somewhere real. A cold load of a module's inner screen is sent
  // to that module's home (see routes.js).
  const [route, setRoute] = useState(() => entry(window.location.pathname))
  const { page } = route
  const tab = TAB_OF[page] || 'HAPExt'

  // null while we ask the server; then /api/auth/me's answer, or a refusal
  // we could not recover from
  const [session, setSession] = useState(null)

  /** Move to a screen, leaving the browser an entry to come Back to. */
  const go = useCallback((next, { replace = false } = {}) => {
    const path = pathOf(next.page)
    if (replace || window.location.pathname === path) {
      window.history.replaceState(next, '', path)
    } else {
      window.history.pushState(next, '', path)
    }
    setRoute(next)
  }, [])

  // Back and Forward. The entry we pushed carries the screen; the pathname is
  // the fallback for an entry this build did not create.
  useEffect(() => {
    const popped = (event) =>
      setRoute(event.state || entry(window.location.pathname))
    window.addEventListener('popstate', popped)
    return () => window.removeEventListener('popstate', popped)
  }, [])

  const setPage = useCallback((name) => go({ opened: true, page: name }), [go])

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

  // Ask who we are first; only then load anything the gate protects. Not
  // signed in at MAEC One: one trip to its sign-in, and back. Sent once
  // already this visit: stop and say so rather than bouncing between two
  // services.
  useEffect(() => {
    authApi.me()
      .then((who) => {
        if (who.authenticated) { setSession(who); return }
        if (!reauthorize(who.login_url)) {
          setSession({ authenticated: false, refused: true })
        }
      })
      .catch((err) => setSession({ authenticated: false, refused: true, error: err.message }))
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

  // The bar agrees with what is on screen however we got there — including a
  // root, /home or unknown address, which opens HAPExt.
  useEffect(() => {
    if (!session?.authenticated) return
    const path = pathOf(page)
    if (window.location.pathname !== path) {
      window.history.replaceState(route, '', path)
    }
  }, [session, page, route])

  // Signing out happens at MAEC One and signs the person out of every app at
  // once; this product holds no session of its own to end. A session that
  // lapses mid-module is handled in api.js: one trip to sign-in, and back.
  const toMaecOne = () => window.location.assign(session.core_url)

  const goTab = (name) => {
    if (name === 'HAPAudit') return
    go({ opened: true, page: HOME_OF[name] || HOME_OF['HAPExt'] })
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
    go({ opened: true, page: 'air-wizard' })
  }, [go])

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
    go({ opened: true, page: 'hap-result' })
  }, [go])

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
    go({ opened: true, page: 'air-wizard' })
  }, [go])

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
    airDetails, setAirDetails, airLogo, setAirLogo, airImported,
    recordSizing, loadSpaces,
    // history
    recentsKey, rememberConversion, openConversion, rememberSizing, openSizing,
    bumpRecents: () => setRecentsKey((n) => n + 1),
  }

  const pages = {
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
  const Page = pages[page] || HapHome

  if (session === null) {
    return <div className="shell" style={{ alignItems: 'center', justifyContent: 'center' }}>
      <span className="muted">Loading…</span>
    </div>
  }
  if (!session.authenticated) {
    // Reached only when one trip to MAEC One's sign-in did not bring the
    // browser back signed in, or MAEC One could not be asked. The way back is
    // a click, never an automatic redirect — that is what keeps a refusal
    // from becoming a loop.
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
    <div className="shell">
      <div className="titlebar">
        <button
          className="titlebar-home"
          title="Back to MAEC One"
          onClick={toMaecOne}
        >
          <img className="titlebar-logo" src="/maec-logo.png" alt="MAEC" />
        </button>
        <span className="version">v{VERSION}</span>
        <span className="grow" />
        <button className="btn-ghost" onClick={toMaecOne} title="Sign out at MAEC One">Sign out</button>
      </div>

      <div className="tabbar">
        {/* A module Core leaves out of this person's navigation is not
            offered. Decluttering, not the boundary: the server refuses a
            route whose permission the person lacks whatever is shown. */}
        {TABS.filter((name) => session.modules?.[MODULE_OF[name]] !== false).map((name) => {
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
