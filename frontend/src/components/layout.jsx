import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { byId } from '../data/movies'
import { loadSimilar, similarTo } from '../lib/ai'
import { useStore } from '../store'
import { Icon, Logo, Meta, Poster } from './ui'

export function TopBar() {
  const { user, list, logout } = useStore()
  const toLogin = useLoginNav()
  return (
    <header className="topbar">
      <Logo />
      <nav className="nav">
        <NavLink to="/chat" className={({ isActive }) => (isActive ? 'on' : '')}>Chat</NavLink>
        <NavLink to="/list" className={({ isActive }) => (isActive ? 'on' : '')}>
          My List{user && list.length > 0 && <span className="count">{list.length}</span>}
        </NavLink>
      </nav>
      <div className="spacer" />
      {user ? (
        <div className="user-chip">
          <span className="nm">{user.name}</span>
          <span className="avatar">{user.name[0].toUpperCase()}</span>
          <button className="icon-btn" onClick={logout} title="Đăng xuất" aria-label="Đăng xuất"><Icon name="logout" /></button>
        </div>
      ) : (
        <button className="btn btn-ghost btn-sm" onClick={toLogin}>Đăng nhập</button>
      )}
    </header>
  )
}

// Sang trang login, nhớ trang hiện tại để quay lại
export function useLoginNav() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  return () => navigate('/login', { state: { from: pathname === '/login' || pathname === '/' ? '/chat' : pathname } })
}

// Đóng có animation: thêm class .leave, chờ animationend rồi mới unmount
function useClosable(onClose) {
  const [leaving, setLeaving] = useState(false)
  const close = () => setLeaving(true)
  const onAnimationEnd = (e) => { if (leaving && e.target === e.currentTarget) onClose() }
  return { leaving, close, onAnimationEnd }
}

function GateModal() {
  const { gateLabel, closeGate } = useStore()
  const toLogin = useLoginNav()
  const { leaving, close, onAnimationEnd } = useClosable(closeGate)
  useEscape(close)
  const cls = leaving ? 'leave' : 'enter'
  return (
    <>
      <div className={`scrim ${cls}`} onClick={close} />
      <div className={`modal ${cls}`} role="dialog" aria-modal="true" aria-labelledby="gate-title" onAnimationEnd={onAnimationEnd}>
        <span className="ic"><Icon name="lock" /></span>
        <h2 id="gate-title">Đăng nhập để {gateLabel}</h2>
        <p>Chat thì không cần tài khoản. Lưu phim, xem chi tiết, so sánh và tìm phim tương tự cần đăng nhập để AI nhớ gu của bạn.</p>
        <div className="row">
          <button className="btn btn-ghost" onClick={close}>Để sau</button>
          <button className="btn btn-primary" onClick={() => { closeGate(true); toLogin() }}>Đăng nhập</button>
        </div>
      </div>
    </>
  )
}

function Drawer({ id }) {
  const { list, toggleList, closeDrawer, openDrawer, send } = useStore()
  const navigate = useNavigate()
  const { leaving, close, onAnimationEnd } = useClosable(closeDrawer)
  useEscape(close)
  const m = byId[id]
  const saved = list.includes(id)
  // Phim tương tự: engine thật (vector + đội ngũ, không gọi LLM); API tắt thì dùng mock
  const [sims, setSims] = useState(null)
  useEffect(() => {
    let alive = true
    setSims(null)
    loadSimilar(id, 4).then((items) => alive && setSims(items || similarTo([id], 4)))
    return () => { alive = false }
  }, [id])
  const cls = leaving ? 'leave' : 'enter'
  const askAbout = () => { closeDrawer(); navigate('/chat'); send({ type: 'about', id }) }
  return (
    <>
      <div className={`scrim ${cls}`} onClick={close} />
      <aside className={`drawer ${cls}`} role="dialog" aria-modal="true" aria-label={`Chi tiết ${m.title}`} onAnimationEnd={onAnimationEnd}>
        <button className="icon-btn d-close" onClick={close} aria-label="Đóng"><Icon name="close" /></button>
        <div className="d-hero" style={{ '--h': m.hue }}>
          <Poster m={m} />
          <div style={{ display: 'grid', gap: 8, minWidth: 0 }}>
            <span className="eyebrow">{m.genres[0]}</span>
            <h2>{m.title}</h2>
            <div className="meta"><Meta m={m} /></div>
          </div>
        </div>
        <div className="d-body">
          <div className="d-acts">
            <button className={`btn ${saved ? 'btn-ghost' : 'btn-primary'} btn-sm`} onClick={() => toggleList(id, m.title)}>
              <Icon name={saved ? 'check' : 'plus'} /> {saved ? 'Đã lưu vào My List' : 'Thêm vào My List'}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={askAbout}><Icon name="chat" /> Hỏi AI về phim này</button>
            <a className="btn btn-ghost btn-sm" href={`https://www.youtube.com/results?search_query=${encodeURIComponent(m.title + ' trailer')}`} target="_blank" rel="noopener noreferrer"><Icon name="play" /> Trailer</a>
          </div>
          <div className="facts">
            <div><b className="mono">★ {m.rating}</b><span>Điểm khán giả</span></div>
            <div><b className="mono">{m.runtime > 0 ? `${m.runtime}′` : '—'}</b><span>{m.kind === 'tv' ? 'Mỗi tập' : 'Thời lượng'}</span></div>
            <div><b className="mono">{m.year}</b><span>Phát hành</span></div>
          </div>
          <div className="d-sec"><h4>Nội dung</h4><p>{m.overview}</p></div>
          <div className="d-sec"><h4>AI cảm nhận về phim</h4>
            {m.profile?.length
              ? <dl className="d-prof">{m.profile.filter(([k]) => k !== 'Hay được tìm').map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
              : <p>Khán giả đánh giá phim {(m.mood || '').toLowerCase()}. Chủ đề nổi bật: {m.keywords.slice(0, 2).join(' và ')}.</p>}
          </div>
          <div className="d-sec"><h4>Đạo diễn & diễn viên</h4>
            <div className="tags">{m.director && <span className="tag" style={{ color: 'var(--fg)' }}>{m.director}</span>}{m.cast.map((c) => <span className="tag" key={c}>{c}</span>)}</div>
          </div>
          <div className="d-sec"><h4>Thể loại & từ khoá</h4>
            <div className="tags">{[...m.genres, ...m.keywords].map((t) => <span className="tag" key={t}>{t}</span>)}</div>
          </div>
          <div className="d-sec"><h4>Phim tương tự</h4>
            <div className="simlist">
              {!sims && <p className="meta">Đang tìm phim tương tự…</p>}
              {sims?.filter(({ id: sid }) => byId[sid]).map(({ id: sid, sim }) => (
                <button className="simitem" key={sid} onClick={(e) => { openDrawer(sid); e.currentTarget.closest('.drawer').scrollTo({ top: 0, behavior: 'smooth' }) }}>
                  <Poster m={byId[sid]} />
                  <span style={{ minWidth: 0 }}><div style={{ fontWeight: 600, fontSize: 14 }}>{byId[sid].title}</div><div className="meta">{[byId[sid].year, byId[sid].director].filter(Boolean).join(' · ')}</div></span>
                  <b>{sim.score}%</b>
                </button>
              ))}
            </div>
          </div>
        </div>
      </aside>
    </>
  )
}

function useEscape(fn) {
  useEffect(() => {
    const h = (e) => e.key === 'Escape' && fn()
    addEventListener('keydown', h)
    return () => removeEventListener('keydown', h)
  })
}

// Lớp phủ dùng chung: popup đăng nhập, drawer chi tiết phim, toast
export function Overlays() {
  const { gateLabel, drawer, toastMsg } = useStore()
  useEffect(() => {
    document.body.style.overflow = gateLabel || drawer ? 'hidden' : ''
  }, [gateLabel, drawer])
  return (
    <>
      {gateLabel && <GateModal />}
      {drawer && <Drawer key="drawer" id={drawer} />}
      {toastMsg && <div className="toast" role="status">{toastMsg}</div>}
    </>
  )
}
