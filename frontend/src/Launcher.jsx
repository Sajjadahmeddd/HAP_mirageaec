// The MAEC One launcher — where you land once signed in.
//
// Same frame as the sign-in screen, so the page you just filled in does not
// jump around underneath you: the tiles stay exactly where they were and
// only the right-hand panel changes. What does change is that the tiles are
// now controls, and the one product that exists can be opened.
//
// Each product other than this one is its own Render service, so picking it
// is a navigation, not a route change. MODULES in MaecOne.jsx holds the URLs
// and is the release gate; the sign-in screen reads the same list, so both
// screens always describe the same eight things.

import MaecOne, { BADGES, ICONS, MODULES, READY, isReady } from './MaecOne.jsx'

export default function Launcher({ name, email, onOpen, onSignOut }) {
  const live = MODULES.filter(isReady)
  const soon = MODULES.length - live.length

  // The app we are opens in place; a separately hosted one is a full
  // navigation to wherever it lives.
  const pick = (module) => {
    if (module.internal) onOpen(module.key)
    else if (module.href) window.location.assign(module.href)
  }

  const panel = (
    <div className="signin-card launch-card">
      <div className="signin-mark"><img src="/maec-logo.png" alt="" /></div>

      <p className="launch-status">
        <ICONS.shieldCheck width="15" height="15" />
        Signed in
      </p>

      <h2 className="signin-welcome">Welcome back</h2>
      <p className="launch-name">{name || 'MAEC'}</p>
      {email && <p className="signin-sub">{email}</p>}

      <p className="launch-lede">
        Your MAEC One workspace is ready. Choose an application on the left
        to get started.
      </p>

      <ul className="launch-list">
        {live.map(({ key, icon, tone, title, body }) => {
          const Icon = ICONS[icon]
          return (
            <li key={key}>
              <button
                type="button"
                className="launch-open"
                onClick={() => pick(MODULES.find((m) => m.key === key))}
              >
                <span className={`module-icon tone-${tone}`}><Icon width="22" height="22" /></span>
                <span className="launch-open-text">
                  <strong>{title}</strong>
                  {body}
                </span>
                <ICONS.arrow width="16" height="16" />
              </button>
            </li>
          )
        })}
      </ul>

      <p className="launch-soon">
        {soon} more {soon === 1 ? 'application is' : 'applications are'} on the
        way. You will see them light up here as they land.
      </p>

      <button type="button" className="launch-signout" onClick={onSignOut}>
        Sign out
      </button>

      <ul className="signin-badges">
        {BADGES.map(([label, sub]) => (
          <li key={label}>
            <ICONS.badge width="18" height="18" />
            <span><strong>{label}</strong>{sub}</span>
          </li>
        ))}
      </ul>
    </div>
  )

  return <MaecOne panel={panel} onPick={pick} ready={READY} />
}
