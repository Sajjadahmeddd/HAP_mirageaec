// The MAEC shell: title bar, product tabs, and the page stack — the web
// equivalent of hap_converter/ui/app_window.py's QStackedWidget.
//
// All session state lives here and is handed down as `ctx`, the same shape
// the desktop pages receive. Nothing is persisted server-side (see §4 of the
// migration brief): a sizing run happens in one sitting and the exported
// workbook is the artifact.

import { useCallback, useEffect, useState } from 'react'
import { airsizer as airApi } from './api'

import HapHome from './hapext/Home.jsx'
import HapUpload from './hapext/Upload.jsx'
import HapConvert from './hapext/Convert.jsx'
import HapResult from './hapext/Result.jsx'
import HapFailure from './hapext/Failure.jsx'
import ChangeRequest from './hapext/ChangeRequest.jsx'
import ChangeReview from './hapext/ChangeReview.jsx'

import AirHome from './airsizer/Home.jsx'
import AirWizard from './airsizer/Wizard.jsx'
import AirReview from './airsizer/Review.jsx'

const TABS = ['HAPExt', 'AirSizer Pro', 'HAPAudit']
const VERSION = '1.2'

export default function App() {
  const [tab, setTab] = useState('HAPExt')
  const [page, setPage] = useState('hap-home')

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

  useEffect(() => {
    airApi.config()
      .then((cfg) => {
        setAirConfig(cfg)
        setVisibleColumns(cfg.result_columns.filter((c) => c.default).map((c) => c.key))
      })
      .catch((err) => setAirError(err.message))
  }, [])

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
    'air-wizard': AirWizard,
    'air-review': AirReview,
  }
  const Page = pages[page] || HapHome

  return (
    <div className="shell">
      <div className="titlebar">
        <img src="/logo.png" alt="" onError={(e) => { e.currentTarget.style.display = 'none' }} />
        <span className="brand">M<span className="accent">AEC</span></span>
        <span className="version">v{VERSION}</span>
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
