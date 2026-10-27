import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { byId, movies } from '../data/movies'
import { loadPair, similarity } from '../lib/ai'
import { useStore } from '../store'
import { MovieCard } from '../components/movies'
import { useLoginNav } from '../components/layout'
import { Icon, Logo, Poster, SimBlock } from '../components/ui'

const EXAMPLES = ['Phim nhẹ nhàng tối nay', 'Phim Hàn Quốc hay', 'Phim hoạt hình cho cả nhà', 'So sánh Dune 2 và Mad Max']
const FEATURES = [
  ['chat', 'Hỏi bằng lời thường', 'Không cần bộ lọc. Chat được ngay, không cần tài khoản.'],
  ['spark', 'Gợi ý kèm lý do', 'Mỗi phim có một dòng giải thích vì sao hợp với bạn.'],
  ['compare', 'So sánh 2–3 phim', 'Bảng so sánh thời lượng, điểm, không khí phim và kết luận nên xem phim nào.'],
  ['similar', 'Tìm phim tương tự', 'Từ một phim bạn thích, ra danh sách phim gần nhất kèm % tương đồng.'],
]

export default function Landing() {
  const { user, send, newChat } = useStore()
  const navigate = useNavigate()
  const toLogin = useLoginNav()
  const [q, setQ] = useState('')
  const a = byId[27205], b = byId[157336]
  const [pair, setPair] = useState(null)
  useEffect(() => { loadPair(27205, 157336).then(setPair) }, [])

  const start = (text) => {
    newChat()
    navigate('/chat')
    if (text) send({ text })
  }

  return (
    <main className="view" id="v-landing">
      <header className="topbar">
        <Logo />
        <div className="spacer" />
        {user ? <Link className="btn btn-ghost btn-sm" to="/list">My List</Link> : <button className="btn btn-ghost btn-sm" onClick={toLogin}>Đăng nhập</button>}
        <Link className="btn btn-primary btn-sm" to="/chat">Mở CineMind</Link>
      </header>

      <section className="hero">
        <div className="hero-in">
          <div>
            <h1>Tìm phim để xem tối nay bằng <em>một câu hỏi</em>.</h1>
            <p className="lead">Nói thể loại, tâm trạng hoặc một phim bạn từng thích. CineMind gợi ý vài phim phù hợp, kèm lý do ngắn cho từng phim.</p>
            <form className="ask" onSubmit={(e) => { e.preventDefault(); start(q.trim()) }}>
              <input id="hero-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ví dụ: phim giống Inception nhưng nhẹ hơn" aria-label="Bạn muốn xem gì?" autoComplete="off" />
              <button className="btn btn-primary" type="submit">Hỏi AI <Icon name="send" /></button>
            </form>
            <div className="chips">{EXAMPLES.map((t) => <button key={t} className="chip" onClick={() => start(t)}>{t}</button>)}</div>
          </div>
          <div className="preview" aria-hidden="true">
            <div className="bubble-u">Tối nay mệt, muốn xem phim nhẹ nhàng</div>
            <div className="ai"><i className="ai-av" /><div className="ai-body">
              <details className="think"><summary><Icon name="spark" /> Đã suy luận qua 4 bước · 1,6 giây</summary></details>
              <p className="ai-text">Phim hợp nhất với bạn tối nay:</p>
              <MovieCard id={666277} reason="Nhịp chậm, nhẹ nhàng, chỉ 106 phút." still />
            </div></div>
          </div>
        </div>
        <div className="strip" aria-hidden="true">{[...movies, ...movies].map((m, i) => <Poster key={i} m={m} />)}</div>
      </section>

      <section className="section">
        <h2>Bạn làm được gì với CineMind</h2>
        <div className="steps-row feats">
          {FEATURES.map(([i, h, p]) => (
            <div className="step-card" key={h}><span className="ic-sq"><Icon name={i} /></span><h3>{h}</h3><p>{p}</p></div>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="duo">
          <div>
            <h2>Biết hai phim giống nhau ở điểm nào</h2>
            <p>Điểm tương đồng được tách theo nội dung, chủ đề và đội ngũ làm phim.</p>
          </div>
          <div className="sim-card">
            <div className="pair"><Poster m={a} /><span className="vs">VS</span><Poster m={b} /></div>
            <SimBlock sim={pair || similarity(a, b)} label={`${a.title} ↔ ${b.title}`} />
          </div>
        </div>
      </section>

      <section className="cta">
        <div className="cta-in">
          <h2>Bắt đầu tìm phim</h2>
          <p>Không cần tài khoản để chat.</p>
          <Link className="btn btn-primary" to="/chat">Mở CineMind <Icon name="send" /></Link>
        </div>
      </section>
      <footer>CineMind · Bản demo giao diện · Dữ liệu phim minh hoạ</footer>
    </main>
  )
}
