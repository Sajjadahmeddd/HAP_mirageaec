// The Recent Projects panel, shared by both home screens.
// Ported from the desktop's RecentProjectsPanel (hap_converter/ui/widgets.py)
// and the AirSizer equivalent — same row shape, same ⋮ menu.

import { useEffect, useRef, useState } from 'react'
import { formatWhen, isAvailable, list, remove } from './recents'

function RecentRow({ entry, onOpen, onRemove }) {
  const [menu, setMenu] = useState(false)
  const box = useRef(null)

  useEffect(() => {
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setMenu(false) }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  return (
    <div className="recent-item" onClick={() => onOpen(entry)}>
      <div className="grow">
        <div className="recent-name">{entry.name}</div>
        <div className="small">{entry.summary} • {formatWhen(entry.saved)}</div>
      </div>
      <div className="picker" ref={box} onClick={(e) => e.stopPropagation()}>
        <button title="More" onClick={() => setMenu((m) => !m)}>⋮</button>
        {menu && (
          <div className="picker-menu" style={{ minWidth: 170 }}>
            <label onClick={() => { setMenu(false); onOpen(entry) }}>Open</label>
            <label onClick={() => { setMenu(false); onRemove(entry) }}>Remove from list</label>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * `module` is one of the keys from recents.js. `refreshKey` lets a parent
 * force a re-read after it saves a new session.
 */
export default function RecentPanel({ module, onOpen, emptyText, refreshKey }) {
  const [entries, setEntries] = useState([])
  const available = isAvailable()

  useEffect(() => { setEntries(list(module)) }, [module, refreshKey])

  const drop = (entry) => {
    remove(module, entry.id)
    setEntries(list(module))
  }

  return (
    <div className="panel-card col" style={{ padding: '14px 16px', gap: 2 }}>
      {!available ? (
        <div className="muted" style={{ textAlign: 'center', padding: '24px 8px' }}>
          This browser is blocking local storage, so history cannot be kept.
        </div>
      ) : entries.length === 0 ? (
        <div className="muted" style={{ textAlign: 'center', padding: '24px 8px' }}>
          {emptyText}
        </div>
      ) : (
        <>
          {entries.map((entry) => (
            <RecentRow key={entry.id} entry={entry} onOpen={onOpen} onRemove={drop} />
          ))}
          <div className="small" style={{ marginTop: 8, textAlign: 'center' }}>
            Kept in this browser only — not on the server
          </div>
        </>
      )}
    </div>
  )
}
