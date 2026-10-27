import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { byId } from '../data/movies'
import { useStore } from '../store'
import { TopBar, useLoginNav } from '../components/layout'
import { Icon, Poster } from '../components/ui'

export default function MyList() {
  const { user, list, removeFromList, openDrawer, newChat, send } = useStore()
  const navigate = useNavigate()
  const toLogin = useLoginNav()
  const [sel, setSel] = useState([])
  const n = sel.length

  const toggle = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  // So sánh / tìm tương tự mở một cuộc chat mới với kết quả
  const runInChat = (input) => { setSel([]); newChat(); navigate('/chat'); send(input) }

  const hint = n === 1 ? 'Chọn thêm phim để so sánh' : n > 3 ? 'So sánh tối đa 3 phim' : n > 1 ? 'Tìm phim tương tự chỉ áp dụng cho 1 phim' : 'Bấm vào poster để chọn'

  let body
  if (!user) body = (
    <div className="state">
      <span style={{ color: 'var(--accent)' }}><Icon name="lock" /></span>
      <h2>Đăng nhập để xem My List</h2>
      <p>Lưu phim từ khung chat, rồi so sánh hoặc tìm phim tương tự bằng AI.</p>
      <button className="btn btn-primary" onClick={toLogin}>Đăng nhập</button>
    </div>
  )
  else if (!list.length) body = (
    <div className="state">
      <h2>Danh sách đang trống</h2>
      <p>Bấm "My List" trên bất kỳ phim nào AI gợi ý để lưu lại đây.</p>
      <Link className="btn btn-primary" to="/chat">Mở chat tìm phim</Link>
    </div>
  )
  else body = (
    <div className="grid">
      {list.map((id) => {
        const m = byId[id], on = sel.includes(id)
        return (
          <div className={`tile ${on ? 'sel' : ''}`} key={id}>
            <button className="tile-pick" onClick={() => toggle(id)} aria-pressed={on} aria-label={`Chọn ${m.title}`}>
              <span className="tick" /><Poster m={m} />
            </button>
            <h3>{m.title}</h3>
            <div className="tile-row">
              <span className="meta">{m.year} · <span className="star">★ {m.rating}</span></span>
              <button className="linkish" onClick={() => openDrawer(id)}>Chi tiết</button>
            </div>
          </div>
        )
      })}
    </div>
  )

  return (
    <div className="view" id="v-list">
      <TopBar />
      <main className="page">
        <div className="page-head">
          <div>
            <span className="eyebrow">My List{user && ` · ${list.length} phim`}</span>
            <h1>Danh sách của tôi</h1>
            <p>Chọn 1 phim để tìm phim tương tự, hoặc chọn 2–3 phim để AI so sánh.</p>
          </div>
          {user && list.length > 0 && <span className="hint">{hint}</span>}
        </div>
        {body}
      </main>

      {n > 0 && (
        <div className="actionbar" role="toolbar" aria-label="Thao tác với phim đã chọn">
          <span className="n">Đã chọn <b>{n}</b></span>
          <button className="btn btn-primary btn-sm" disabled={n < 2 || n > 3} title="Chọn 2–3 phim" onClick={() => runInChat({ type: 'compare', ids: sel })}>
            <Icon name="compare" /> So sánh
          </button>
          <button className="btn btn-ghost btn-sm" disabled={n !== 1} title="Chọn đúng 1 phim" onClick={() => runInChat({ type: 'similar', ids: sel })}>
            <Icon name="similar" /> Tìm phim tương tự
          </button>
          <button className="icon-btn" onClick={() => { removeFromList(sel); setSel([]) }} title="Bỏ khỏi list" aria-label="Bỏ khỏi list"><Icon name="trash" /></button>
          <button className="icon-btn" onClick={() => setSel([])} title="Huỷ chọn" aria-label="Huỷ chọn"><Icon name="close" /></button>
        </div>
      )}
    </div>
  )
}
