// The sign-in screen.
//
// Layout follows the reference the client supplied (logo, product name,
// then a card with email + password), rendered in MAEC's own palette —
// navy heading, green primary action — rather than the reference's orange.
//
// One shared account for now; RBAC comes later. When it does, this file
// stays as it is and only auth.verify() on the server changes.

import { useState } from 'react'
import { auth } from './api'

function EyeIcon({ off }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
      <path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12Z" />
      <circle cx="12" cy="12" r="2.8" />
      {off && <line x1="3.5" y1="20.5" x2="20.5" y2="3.5" />}
    </svg>
  )
}

export default function Login({ onSignedIn }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [reveal, setReveal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [hint, setHint] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    if (!email.trim() || !password || busy) return
    setBusy(true)
    setError('')
    try {
      await auth.login(email, password)
      onSignedIn()
    } catch (err) {
      setError(err.message)
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-inner">
        <img className="login-logo" src="/logo-with-name.jpg" alt="Mirage AEC"
             onError={(e) => { e.currentTarget.style.display = 'none' }} />
        <h1 className="login-product">HAPExt</h1>

        <form className="card login-card" onSubmit={submit}>
          <h2 className="login-welcome">Welcome Back</h2>
          <p className="login-sub">Sign in to your account</p>

          <label className="field" htmlFor="maec-email">Email address</label>
          <input
            id="maec-email"
            type="email"
            value={email}
            autoFocus
            autoComplete="username"
            placeholder="you@example.com"
            onChange={(e) => { setEmail(e.target.value); setError('') }}
          />

          <label className="field" htmlFor="maec-password" style={{ marginTop: 16 }}>
            Password
          </label>
          <div className="login-password">
            <input
              id="maec-password"
              type={reveal ? 'text' : 'password'}
              value={password}
              autoComplete="current-password"
              placeholder="••••••••"
              onChange={(e) => { setPassword(e.target.value); setError('') }}
            />
            <button
              type="button"
              className="reveal"
              aria-label={reveal ? 'Hide password' : 'Show password'}
              title={reveal ? 'Hide password' : 'Show password'}
              onClick={() => setReveal((r) => !r)}
            >
              <EyeIcon off={reveal} />
            </button>
          </div>

          {error && <div className="status-fail login-error">{error}</div>}

          <button
            type="submit"
            className="btn btn-primary login-submit"
            disabled={!email.trim() || !password || busy}
          >
            {busy ? 'Signing in…' : 'Sign in'}
          </button>

          <button type="button" className="login-forgot" onClick={() => setHint((h) => !h)}>
            Forgot your password?
          </button>
          {hint && (
            <p className="small login-hint">
              This is a shared team account — ask your project lead for the
              current password.
            </p>
          )}
        </form>
      </div>
    </div>
  )
}
