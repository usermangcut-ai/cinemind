import { useEffect, useRef, useState } from 'react'
import { byId, trending } from '../data/movies'
import { STARTER_CHIPS, loadTrending } from '../lib/ai'
import { useStore } from '../store'
import { AiMessage } from '../components/movies'
import { TopBar, useLoginNav } from '../components/layout'
import { Icon, Poster } from '../components/ui'

const narrow = () => innerWidth <= 1080

export default function Chat() {
  const { user, conv, send } = useStore()
  const toLogin = useLoginNav()
  const [lOff, setLOff] = useState(narrow)
  const [rOff, setROff] = useState(narrow)
  const [editAt, setEditAt] = useState(null)
  const scroller = useRef(null)
  const busy = !!conv?.msgs.some((m) => m.role === 'ai' && !m.done)

  // Trên màn hẹp, sidebar là lớp phủ: mở bên này thì đóng bên kia
  const toggleL = () => { setLOff((v) => !v); if (narrow()) setROff(true) }
  const toggleR = () => { setROff((v) => !v); if (narrow()) setLOff(true) }
  const closeOnNarrow = () => narrow() && (setLOff(true), setROff(true))

  const last = conv?.msgs.at(-1)
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' })
  }, [conv?.id, conv?.msgs.length, last?.step, last?.done])
  useEffect(() => { setEditAt(null) }, [conv?.id])

  return (
    <div className="view" id="v-app">
      <TopBar />
      <div className={`app ${lOff ? 'l-off' : ''} ${rOff ? 'r-off' : ''}`}>
        <HistorySidebar onClose={toggleL} onPick={closeOnNarrow} />

        <section className="chat" aria-label="Chat với AI">
          <div className="chat-bar">
            <button className="icon-btn" onClick={toggleL} title="Lịch sử chat" aria-label="Bật/tắt lịch sử chat"><Icon name="history" /></button>
            <div className="ttl">{conv?.title ?? 'Cuộc trò chuyện mới'}</div>
            <NewChatButton icon />
            <button className="icon-btn" onClick={toggleR} title="Top 10 phim" aria-label="Bật/tắt top 10 phim"><Icon name="trend" /></button>
          </div>

          <div className="msgs" ref={scroller}>
            <div className="msgs-in">
              {conv?.msgs.length ? conv.msgs.map((m, i) =>
                m.role === 'ai' ? <AiMessage key={m.id} msg={m} last={m === last} />
                  : editAt === i ? <EditMessage key={m.id} text={m.text} onCancel={() => setEditAt(null)} onSubmit={(t) => { setEditAt(null); send({ text: t }, { truncateAt: i }) }} />
                  : (
                    <div className="u-row" key={m.id}>
                      {!busy && <button className="icon-btn" onClick={() => setEditAt(i)} title="Sửa tin nhắn" aria-label="Sửa tin nhắn"><Icon name="pen" /></button>}
                      <div className="bubble-u">{m.text}</div>
                    </div>
                  ),
              ) : (
                <div className="empty-chat">
                  <span className="eyebrow">CineMind</span>
                  <h2>Tối nay bạn muốn xem gì?</h2>
                  <p>Kể thể loại, tâm trạng, hay một bộ phim bạn từng thích. Mình sẽ gợi ý kèm lý do.</p>
                  <div className="chips" style={{ justifyContent: 'center' }}>
                    {STARTER_CHIPS.map((t) => <button key={t} className="chip" onClick={() => send({ text: t })}>{t}</button>)}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="composer">
            <div className="composer-in">
              <Composer disabled={busy} onSend={(t) => send({ text: t })} />
              {!user && <div className="guest">Bạn đang chat với tư cách khách. <button onClick={toLogin}>Đăng nhập</button> để lưu phim, xem chi tiết và so sánh.</div>}
            </div>
          </div>
        </section>

        <TrendingSidebar onClose={toggleR} onPick={closeOnNarrow} />
      </div>
    </div>
  )
}

function NewChatButton({ icon }) {
  const { newChat } = useStore()
  return icon
    ? <button className="icon-btn" onClick={newChat} title="Cuộc trò chuyện mới" aria-label="Cuộc trò chuyện mới"><Icon name="plus" /></button>
    : <button className="btn btn-ghost btn-sm" style={{ width: '100%' }} onClick={newChat}><Icon name="plus" /> Cuộc trò chuyện mới</button>
}

function Composer({ onSend, disabled }) {
  const [text, setText] = useState('')
  const ref = useRef(null)
  // nút "+ Thêm" ở chip lọc → điền sẵn ô nhập để user gõ thêm điều kiện
  useEffect(() => {
    const h = (e) => { setText(e.detail); requestAnimationFrame(() => { ref.current?.focus(); ref.current?.setSelectionRange(e.detail.length, e.detail.length) }) }
    addEventListener('cm:prefill', h)
    return () => removeEventListener('cm:prefill', h)
  }, [])
  const submit = (e) => {
    e.preventDefault()
    const t = text.trim()
    if (!t || disabled) return
    onSend(t)
    setText('')
    ref.current.style.height = 'auto'
  }
  return (
    <form className="box" onSubmit={submit}>
      <textarea
        ref={ref} id="chat-q" rows={1} value={text} placeholder="Hỏi CineMind bất cứ điều gì về phim…" aria-label="Tin nhắn"
        onChange={(e) => { setText(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px' }}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e) }}
      />
      <button className="send" type="submit" aria-label="Gửi" disabled={disabled}><Icon name="send" /></button>
    </form>
  )
}

function EditMessage({ text, onSubmit, onCancel }) {
  const [v, setV] = useState(text)
  const submit = (e) => { e.preventDefault(); if (v.trim()) onSubmit(v.trim()) }
  return (
    <form className="u-edit" onSubmit={submit}>
      <textarea autoFocus value={v} onChange={(e) => setV(e.target.value)} aria-label="Sửa tin nhắn"
        onFocus={(e) => e.target.select()}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e); if (e.key === 'Escape') onCancel() }} />
      <div className="row">
        <button className="btn btn-ghost btn-sm" type="button" onClick={onCancel}>Huỷ</button>
        <button className="btn btn-primary btn-sm" type="submit">Gửi lại</button>
      </div>
    </form>
  )
}

function HistorySidebar({ onClose, onPick }) {
  const { convs, cur, setCur, renameConv, deleteConv } = useStore()
  const [renaming, setRenaming] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const groups = [['Hôm nay', convs.filter((c) => !c.old)], ['Trước đó', convs.filter((c) => c.old)]]

  const item = (c) => {
    if (renaming === c.id) return <RenameForm key={c.id} title={c.title} onDone={(t) => { if (t) renameConv(c.id, t); setRenaming(null) }} />
    if (deleting === c.id) return (
      <div className="conv-confirm" role="alert" key={c.id}>
        Xoá “{c.title.slice(0, 40)}”?
        <div className="row">
          <button className="btn btn-danger btn-sm" onClick={() => { deleteConv(c.id); setDeleting(null) }}>Xoá</button>
          <button className="btn btn-ghost btn-sm" onClick={() => setDeleting(null)}>Huỷ</button>
        </div>
      </div>
    )
    return (
      <div className={`conv-row ${c.id === cur ? 'on' : ''}`} key={c.id}>
        <button className="conv" onClick={() => { setCur(c.id); onPick() }}><Icon name="chat" /><span>{c.title}</span></button>
        <span className="conv-acts">
          <button className="icon-btn" onClick={() => { setRenaming(c.id); setDeleting(null) }} title="Đổi tên" aria-label={`Đổi tên ${c.title}`}><Icon name="pen" /></button>
          <button className="icon-btn del" onClick={() => { setDeleting(c.id); setRenaming(null) }} title="Xoá" aria-label={`Xoá ${c.title}`}><Icon name="trash" /></button>
        </span>
      </div>
    )
  }

  return (
    <aside className="side side-l" aria-label="Lịch sử chat">
      <div className="side-in">
        <div className="side-head"><span className="side-title">Lịch sử</span><button className="icon-btn" onClick={onClose} aria-label="Thu gọn"><Icon name="close" /></button></div>
        <div style={{ padding: '0 14px 6px' }}><NewChatButton /></div>
        <div className="side-scroll">
          {groups.map(([label, items]) => items.length > 0 && (
            <div key={label}><div className="group-label">{label}</div>{items.map(item)}</div>
          ))}
        </div>
      </div>
    </aside>
  )
}

function RenameForm({ title, onDone }) {
  const [v, setV] = useState(title)
  return (
    <form className="conv-edit" onSubmit={(e) => { e.preventDefault(); onDone(v.trim()) }}>
      <input autoFocus value={v} maxLength={80} aria-label="Tên cuộc trò chuyện" onChange={(e) => setV(e.target.value)}
        onFocus={(e) => e.target.select()} onKeyDown={(e) => e.key === 'Escape' && onDone(null)} />
      <button className="icon-btn" type="submit" aria-label="Lưu tên"><Icon name="check" /></button>
    </form>
  )
}

function TrendingSidebar({ onClose, onPick }) {
  const { send } = useStore()
  const [tab, setTab] = useState('week')
  const [, setLoaded] = useState(false)
  useEffect(() => { loadTrending().then(setLoaded) }, [])
  return (
    <aside className="side side-r" aria-label="Top 10 phim">
      <div className="side-in">
        <div className="side-head"><span className="side-title">Top 10 thịnh hành</span><button className="icon-btn" onClick={onClose} aria-label="Thu gọn"><Icon name="close" /></button></div>
        <div className="tabs" role="tablist">
          {[['week', 'Tuần này'], ['month', 'Tháng này']].map(([k, l]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>
          ))}
        </div>
        <div className="side-scroll">
          {trending[tab].map((id, i) => {
            const m = byId[id]
            return (
              <button className="rank" key={id} onClick={() => { onPick(); send({ type: 'about', id }) }}>
                <span className="no">{i + 1}</span><Poster m={m} />
                <span style={{ minWidth: 0 }}><div className="t">{m.title}</div><div className="m">{m.year} · ★ {m.rating}</div></span>
              </button>
            )
          })}
        </div>
        <div className="side-note">Bấm vào phim để AI giới thiệu trong khung chat.</div>
      </div>
    </aside>
  )
}
