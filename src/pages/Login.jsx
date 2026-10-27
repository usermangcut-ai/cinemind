import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { movies } from '../data/movies'
import { useStore } from '../store'
import { Logo, Poster } from '../components/ui'

// Đăng nhập giả lập: email hợp lệ + mật khẩu ≥ 6 ký tự là vào
export default function Login() {
  const { login } = useStore()
  const navigate = useNavigate()
  const from = useLocation().state?.from || '/chat'
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')

  const enter = (name, mail) => {
    const pending = login(name, mail)
    navigate(from, { replace: true })
    if (pending) setTimeout(pending, 0) // chạy tiếp thao tác đang dở (lưu phim, xem chi tiết…)
  }
  const submit = (e) => {
    e.preventDefault()
    if (!/^\S+@\S+\.\S+$/.test(email)) return setErr('Email chưa đúng định dạng, ví dụ ban@email.com.')
    if (pw.length < 6) return setErr('Mật khẩu cần tối thiểu 6 ký tự.')
    enter(email.split('@')[0], email)
  }

  return (
    <main className="view" id="v-login">
      <div className="login-art">
        <div className="mosaic" aria-hidden="true">{[...movies, ...movies.slice(0, 9)].map((m, i) => <Poster key={i} m={m} />)}</div>
        <blockquote>Lưu phim, so sánh và tìm phim tương tự trong một tài khoản.</blockquote>
      </div>
      <div className="login-form">
        <form onSubmit={submit} noValidate>
          <Logo />
          <h1>Đăng nhập</h1>
          <p className="sub">Để lưu phim, xem chi tiết và dùng công cụ so sánh.</p>
          <label className="field" htmlFor="em">Email
            <input id="em" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ban@email.com" autoComplete="email" />
          </label>
          <label className="field" htmlFor="pw">Mật khẩu
            <input id="pw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="Tối thiểu 6 ký tự" autoComplete="current-password" />
          </label>
          {err && <p className="err" role="alert">{err}</p>}
          <button className="btn btn-primary" type="submit">Đăng nhập</button>
          <div className="or">hoặc</div>
          <button className="btn btn-ghost" type="button" onClick={() => enter('Minh Anh', 'demo@cinemind.vn')}>Dùng tài khoản demo</button>
          <Link className="linkish" to="/chat" style={{ justifySelf: 'center' }}>Tiếp tục chat không cần đăng nhập</Link>
        </form>
      </div>
    </main>
  )
}
