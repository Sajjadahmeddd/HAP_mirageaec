// The MAEC One sign-in screen.
//
// Follows the "MAEC One" reference design: the platform pitch and its module
// tiles on the left, the sign-in card on the right, in MAEC's own navy/gold
// brand palette.
//
// Only the email + password exchange is live. The eight module tiles, the
// capability strip and the compliance badges are presentational — the other
// MAEC One products are not part of this app yet, so nothing there is a
// control that could be clicked and do nothing.
//
// One shared account for now; RBAC comes later. When it does, this file
// stays as it is and only auth.verify() on the server changes.

import { useEffect, useState } from 'react'
import { auth } from './api'

const REMEMBER_KEY = 'maec.signin.email'

/** The address is remembered per browser; the session itself is not. */
function readRemembered() {
  try {
    return localStorage.getItem(REMEMBER_KEY) || ''
  } catch {
    return ''            // private windows and blocked site data
  }
}

function writeRemembered(value) {
  try {
    if (value) localStorage.setItem(REMEMBER_KEY, value)
    else localStorage.removeItem(REMEMBER_KEY)
  } catch {
    /* nothing to do — remembering is a convenience, not a requirement */
  }
}

// ---------------------------------------------------------------- icons
const Svg = (props) => (
  <svg
    viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}
  />
)

const ICONS = {
  tools: (p) => (
    <Svg {...p}><path d="M12 2.6 20.5 7v10L12 21.4 3.5 17V7Z" /><path d="M12 12.2 20.5 7M12 12.2 3.5 7m8.5 5.2v9.2" /></Svg>
  ),
  project: (p) => (
    <Svg {...p}><path d="M6 3h9l4 4v14H6Z" /><path d="M9 11h7M9 15h7M9 7h3" /></Svg>
  ),
  finance: (p) => (
    <Svg {...p}><path d="M6 3h9l4 4v14H6Z" /><path d="M12 9.5v7M13.8 11.3a1.8 1.8 0 0 0-3.6.4c0 2 3.6 1 3.6 3a1.8 1.8 0 0 1-3.6.4" /></Svg>
  ),
  people: (p) => (
    <Svg {...p}><circle cx="9" cy="8" r="3.1" /><path d="M3.5 20a5.5 5.5 0 0 1 11 0" /><path d="M16 5.6a3.1 3.1 0 0 1 0 5.9M17.5 14.6A5.5 5.5 0 0 1 20.5 20" /></Svg>
  ),
  clock: (p) => (
    <Svg {...p}><circle cx="12" cy="12" r="8.6" /><path d="M12 7v5.3l3.4 2" /></Svg>
  ),
  card: (p) => (
    <Svg {...p}><rect x="2.6" y="5.4" width="18.8" height="13.2" rx="2.4" /><path d="M2.6 10h18.8" /><path d="M6.6 14.6h3.2" /></Svg>
  ),
  calendar: (p) => (
    <Svg {...p}><rect x="3.4" y="5" width="17.2" height="15.6" rx="2.4" /><path d="M3.4 10h17.2M8.4 3v4M15.6 3v4" /><path d="M8 14h.01M12 14h.01M16 14h.01" /></Svg>
  ),
  kpa: (p) => (
    <Svg {...p}><path d="M12 2.7 20 6v6.2c0 4.4-3.3 7.6-8 9.1-4.7-1.5-8-4.7-8-9.1V6Z" /><path d="m12 8.4 1.3 2.7 2.9.4-2.1 2.1.5 2.9-2.6-1.4-2.6 1.4.5-2.9-2.1-2.1 2.9-.4Z" /></Svg>
  ),
  shieldCheck: (p) => (
    <Svg {...p}><path d="M12 2.7 20 6v6.2c0 4.4-3.3 7.6-8 9.1-4.7-1.5-8-4.7-8-9.1V6Z" /><path d="m8.8 12 2.2 2.2 4.2-4.4" /></Svg>
  ),
  bolt: (p) => (
    <Svg {...p}><path d="M13.4 2.4 5.2 13.2h5.6l-1.4 8.4 8.4-11.1h-5.8Z" /></Svg>
  ),
  target: (p) => (
    <Svg {...p}><circle cx="12" cy="12" r="8.6" /><circle cx="12" cy="12" r="3.4" /><path d="M12 1.8v3.4M12 18.8v3.4M1.8 12h3.4M18.8 12h3.4" /></Svg>
  ),
  cloud: (p) => (
    <Svg {...p}><path d="M7.2 18.6a4.3 4.3 0 0 1-.5-8.6 5.6 5.6 0 0 1 10.8-1.2 3.9 3.9 0 0 1 .3 7.7Z" /></Svg>
  ),
  mail: (p) => (
    <Svg {...p}><rect x="2.8" y="5" width="18.4" height="14" rx="2.4" /><path d="m3.4 7.3 8.6 6 8.6-6" /></Svg>
  ),
  lock: (p) => (
    <Svg {...p}><rect x="4.4" y="10.4" width="15.2" height="10.4" rx="2.4" /><path d="M8.2 10.4V7.6a3.8 3.8 0 0 1 7.6 0v2.8" /></Svg>
  ),
  badge: (p) => (
    <Svg {...p}><path d="M12 2.7 20 6v6.2c0 4.4-3.3 7.6-8 9.1-4.7-1.5-8-4.7-8-9.1V6Z" /><circle cx="12" cy="11.6" r="2.6" /><path d="M10 14v4l2-1.2 2 1.2v-4" /></Svg>
  ),
}

function Eye({ off }) {
  return (
    <Svg width="18" height="18">
      <path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12Z" />
      <circle cx="12" cy="12" r="2.8" />
      {off && <line x1="3.5" y1="20.5" x2="20.5" y2="3.5" />}
    </Svg>
  )
}

// ------------------------------------------------------- static content
// The other MAEC One products. Presentational until they are built.
const MODULES = [
  { icon: 'tools', tone: 'blue', title: 'Engineering Tools', body: 'HAPExt, AirSizer Pro, HAPAudit & more' },
  { icon: 'project', tone: 'green', title: 'Project Management', body: 'Plan, track and deliver projects efficiently' },
  { icon: 'finance', tone: 'orange', title: 'Finance & Billing', body: 'Expenses, monitoring and invoice generation' },
  { icon: 'people', tone: 'violet', title: 'People & HR', body: 'Attendance, leave, timesheet & more' },
  { icon: 'clock', tone: 'teal', title: 'Timesheet', body: 'Submit and manage your timesheets' },
  { icon: 'card', tone: 'amber', title: 'Expense Control', body: 'Track, approve and monitor expenses' },
  { icon: 'calendar', tone: 'rose', title: 'Attendance', body: 'Daily attendance and team overview' },
  { icon: 'kpa', tone: 'blue', title: 'KPA', body: 'Manage KPAs and performance goals' },
]

const CAPABILITIES = [
  ['shieldCheck', 'Secure Access'],
  ['bolt', 'Smart Automation'],
  ['target', 'Accurate Results'],
  ['cloud', 'Seamless Integration'],
]

const BADGES = [
  ['ISO 27001', 'Compliant'],
  ['SOC 2', 'Type II'],
  ['Enterprise Grade', 'Security'],
]

// ------------------------------------------------------------- the page
export default function Login({ onSignedIn }) {
  const remembered = readRemembered()
  const [email, setEmail] = useState(remembered)
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(!!remembered)
  const [reveal, setReveal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [hint, setHint] = useState(false)

  // the address field starts filled when it was remembered, so send focus
  // to the password instead of making the user tab past it
  useEffect(() => {
    const target = remembered ? 'maec-password' : 'maec-email'
    document.getElementById(target)?.focus()
  }, [remembered])

  const submit = async (event) => {
    event.preventDefault()
    if (!email.trim() || !password || busy) return
    setBusy(true)
    setError('')
    try {
      await auth.login(email, password)
      writeRemembered(remember ? email.trim() : '')
      onSignedIn()
    } catch (err) {
      setError(err.message)
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="signin">
      <div className="signin-body">
        {/* ------------------------------------------------ left: pitch */}
        <section className="signin-pitch">
          <div className="maec-lockup">
            <img src="/maec-logo.png" alt="MAEC" />
            <div className="maec-one"><span>ONE</span></div>
          </div>

          <h1 className="signin-headline">
            One Platform.<br />
            Everything <span>Connected.</span>
          </h1>
          <p className="signin-standfirst">
            Engineering, Projects, People &amp; Business —<br />
            all in one secure platform.
          </p>

          <ul className="module-grid">
            {MODULES.map(({ icon, tone, title, body }) => {
              const Icon = ICONS[icon]
              return (
                <li key={title} className="module-tile">
                  <span className={`module-icon tone-${tone}`}><Icon width="27" height="27" /></span>
                  <h2>{title}</h2>
                  <p>{body}</p>
                </li>
              )
            })}
          </ul>

          <ul className="capability-strip">
            {CAPABILITIES.map(([icon, label]) => {
              const Icon = ICONS[icon]
              return (
                <li key={label}><Icon width="17" height="17" />{label}</li>
              )
            })}
          </ul>
        </section>

        {/* ------------------------------------------------ right: form */}
        <section className="signin-panel">
          <form className="signin-card" onSubmit={submit}>
            <div className="signin-mark">
              <img src="/maec-logo.png" alt="" />
            </div>

            <h2 className="signin-welcome">Welcome Back</h2>
            <p className="signin-sub">Sign in to your account</p>

            <label className="signin-label" htmlFor="maec-email">Email address</label>
            <div className="signin-field">
              <span className="signin-adornment"><ICONS.mail width="18" height="18" /></span>
              <input
                id="maec-email"
                type="email"
                value={email}
                autoComplete="username"
                placeholder="youremail@maec.com"
                onChange={(e) => { setEmail(e.target.value); setError('') }}
              />
            </div>

            <label className="signin-label" htmlFor="maec-password">Password</label>
            <div className="signin-field">
              <span className="signin-adornment"><ICONS.lock width="18" height="18" /></span>
              <input
                id="maec-password"
                type={reveal ? 'text' : 'password'}
                value={password}
                autoComplete="current-password"
                placeholder="••••••••••"
                onChange={(e) => { setPassword(e.target.value); setError('') }}
              />
              <button
                type="button"
                className="signin-reveal"
                aria-label={reveal ? 'Hide password' : 'Show password'}
                title={reveal ? 'Hide password' : 'Show password'}
                onClick={() => setReveal((r) => !r)}
              >
                <Eye off={reveal} />
              </button>
            </div>

            <div className="signin-row">
              <label className="signin-remember">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                />
                <span>Remember me</span>
              </label>
              <button type="button" className="signin-forgot" onClick={() => setHint((h) => !h)}>
                Forgot your password?
              </button>
            </div>

            {error && <p className="signin-error">{error}</p>}
            {hint && (
              <p className="signin-hint">
                This is a shared team account — ask your project lead for the
                current password.
              </p>
            )}

            <button
              type="submit"
              className="signin-submit"
              disabled={!email.trim() || !password || busy}
            >
              {busy ? 'Signing in…' : 'Sign in'}
            </button>

            <ul className="signin-badges">
              {BADGES.map(([name, sub]) => (
                <li key={name}>
                  <ICONS.badge width="18" height="18" />
                  <span><strong>{name}</strong>{sub}</span>
                </li>
              ))}
            </ul>
          </form>
        </section>
      </div>

      <footer className="signin-footer">
        <span>© {new Date().getFullYear()} MAEC. All rights reserved.</span>
        <span className="signin-footer-mid">Privacy Policy<i /> Terms of Use</span>
        <span>Need help? <a href="mailto:support@mirageaec.com">support@mirageaec.com</a></span>
      </footer>
    </div>
  )
}
