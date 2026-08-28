// The hero artwork behind each module's welcome text — SVG stand-ins for the
// QPainter drawings in home_page.py (HeroArt) and airsizer/home_page.py
// (DuctArt).

export function BuildingArt() {
  return (
    <svg viewBox="0 0 420 180" style={{ width: '100%', maxHeight: 200 }} aria-hidden="true">
      <polygon points="0,153 412,27 412,153" fill="#DCE8F8" />
      <g stroke="#9DB8DE" strokeWidth="1" fill="none">
        <rect x="50" y="81" width="303" height="72" />
        {[1, 2, 3, 4, 5, 6, 7].map((i) => (
          <line key={i} x1={50 + (303 * i) / 8} y1="81" x2={50 + (303 * i) / 8} y2="153" />
        ))}
        <line x1="50" y1="117" x2="353" y2="117" />
      </g>
      <circle cx="25" cy="167" r="7" fill="#7FA86B" />
    </svg>
  )
}

export function DuctArt() {
  return (
    <svg viewBox="0 0 420 190" style={{ width: '100%', maxHeight: 200 }} aria-hidden="true">
      <polygon
        points="25,105 176,23 395,80 218,167"
        fill="#F1F6E6" stroke="#B7C79A" strokeWidth="1"
      />
      <g stroke="#B7C79A" strokeWidth="1">
        {[1, 2, 3, 4, 5].map((i) => {
          const t = i / 6
          return (
            <line
              key={i}
              x1={25 + (176 - 25) * t} y1={105 - (105 - 23) * t}
              x2={218 + (395 - 218) * t} y2={167 - (167 - 80) * t}
            />
          )
        })}
      </g>
      {/* the diffuser, throwing air both ways */}
      <g stroke="#6E8B23" strokeWidth="2" fill="#fff">
        <rect x="176" y="87" width="67" height="27" />
        <line x1="210" y1="114" x2="155" y2="156" />
        <line x1="210" y1="114" x2="265" y2="156" />
      </g>
    </svg>
  )
}
