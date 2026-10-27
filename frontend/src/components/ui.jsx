import { useState } from 'react'
import { Link } from 'react-router-dom'

const PATHS = {
  send: <path d="M5 12h14M13 6l6 6-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  check: <path d="M5 12l5 5 9-10" />,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  spark: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />,
  similar: <><circle cx="9" cy="12" r="5" /><circle cx="15" cy="12" r="5" /></>,
  compare: <path d="M8 4v16M16 4v16M4 8h4M16 16h4" />,
  history: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 3" /></>,
  trend: <><path d="M3 17l6-6 4 4 8-8" /><path d="M15 7h6v6" /></>,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  lock: <><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>,
  chat: <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />,
  logout: <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />,
  play: <path d="M7 4l13 8-13 8z" />,
  pen: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="M13 7l4 4" /></>,
  trash: <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />,
}

export const Icon = ({ name }) => (
  <svg className="i" viewBox="0 0 24 24" aria-hidden="true">{PATHS[name]}</svg>
)

// Poster thật từ TMDB; lỗi ảnh thì rơi về poster vẽ bằng CSS
export function Poster({ m }) {
  const [failed, setFailed] = useState(false)
  const longest = Math.max(...m.title.split(/\s+/).map((w) => w.length))
  return (
    <div className="poster" style={{ '--h': m.hue }} role="img" aria-label={`Poster ${m.title}`}>
      {!failed && <img src={m.poster} alt="" loading="lazy" onError={() => setFailed(true)} />}
      <span className="p-year">{m.year}</span>
      <span className="p-cap">
        <span className="p-title" style={{ '--fs': `${Math.min(14, 112 / longest).toFixed(1)}cqi` }}>{m.title}</span>
        <span className="p-dir">{m.director}</span>
      </span>
    </div>
  )
}

// **đậm** → <b>
export const Md = ({ text }) =>
  text.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <b key={i}>{part}</b> : part))

export const Meta = ({ m }) => (
  <>{m.kind === 'tv' && <span className="tag-tv">Series</span>}{[m.year, m.director, m.runtime > 0 && `${m.runtime} phút${m.kind === 'tv' ? '/tập' : ''}`].filter(Boolean).join(' · ')} · <span className="star">★ {m.rating}</span></>
)

export const Logo = () => (
  <Link className="logo" to="/" aria-label="CineMind, về trang chủ"><i className="logo-mark" /><span>CineMind</span></Link>
)

export function SimBlock({ sim, label }) {
  return (
    <div className="sim">
      <div className="sim-head"><span className="meta">{label}</span><span className="sim-score mono">{sim.score}%</span></div>
      {Object.entries(sim.parts).map(([k, v]) => (
        <div className="sim-row" key={k}>
          <span>{k}</span><span className="bar"><i style={{ width: `${Math.round(v * 100)}%` }} /></span><b>{Math.round(v * 100)}</b>
        </div>
      ))}
    </div>
  )
}
