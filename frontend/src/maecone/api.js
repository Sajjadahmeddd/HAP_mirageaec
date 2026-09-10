// The MAEC One Core client: who you are, what you may open, and the admin API.
//
// This file is Core's, not Engineering Tools'. The product client
// (../api.js) imports SESSION_EXPIRED from here; nothing here imports from
// there. When Core moves to its own repository this file goes with it.

export const SESSION_EXPIRED = 'maec:session-expired'

// A cross-site form post cannot set a custom header, which is what makes
// this a defence. The token is minted with the session and handed back by
// /api/auth/me and /api/auth/login; every admin mutation must carry it.
export const CSRF_HEADER = 'X-CSRF-Token'

let csrf = ''

export function setCsrf(token) {
  csrf = token || ''
}

export function csrfHeaders(extra = {}) {
  return csrf ? { ...extra, [CSRF_HEADER]: csrf } : { ...extra }
}

function sessionLapsed(response) {
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent(SESSION_EXPIRED))
    throw new Error('Your session has expired. Please sign in again.')
  }
}

async function asJson(response) {
  sessionLapsed(response)
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      detail = (await response.json()).detail || detail
    } catch { /* non-JSON error body */ }
    throw new Error(detail)
  }
  return response.json()
}

/** Remember the CSRF token whenever the server hands one over. */
function keepCsrf(body) {
  if (body && body.csrf_token) setCsrf(body.csrf_token)
  return body
}

export const auth = {
  me() {
    return fetch('/api/auth/me').then(asJson).then(keepCsrf)
  },

  login(email, password) {
    return fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    }).then(async (response) => {
      // 401 here is a wrong password, not a lapsed session — showing the
      // "signed out" banner over the sign-in form would make no sense.
      if (response.status === 401 || response.status === 429) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || 'Incorrect email address or password.')
      }
      return keepCsrf(await asJson(response))
    })
  },

  logout() {
    return fetch('/api/auth/logout', { method: 'POST', headers: csrfHeaders() })
      .then(asJson)
      .finally(() => setCsrf(''))
  },
}

export const admin = {
  whoami() {
    return fetch('/api/admin/whoami').then(asJson)
  },
}
