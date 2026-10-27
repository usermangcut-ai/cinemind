import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { ask, askStream, labelOf, loadMovies } from './lib/ai'

const Ctx = createContext(null)
export const useStore = () => useContext(Ctx)

const uid = () => Math.random().toString(36).slice(2, 9)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const STEP_MS = 480

const load = (k, d) => { try { const v = localStorage.getItem('cm_' + k); return v ? JSON.parse(v) : d } catch { return d } }
const persist = (k, v) => { try { localStorage.setItem('cm_' + k, JSON.stringify(v)) } catch { /* storage bị chặn: bỏ qua */ } }

// Tin nhắn AI đang dở khi reload thì bỏ đi
const loadConvs = () => {
  const c = load('convs', null)
  // bỏ 3 cuộc chat mẫu của bản demo (id s0/s1/s2) nếu còn trong localStorage
  return c ? c.filter((x) => !/^s\d$/.test(x.id)).map((x) => ({ ...x, msgs: x.msgs.filter((m) => m.role === 'user' || m.done) })) : []
}

export function StoreProvider({ children }) {
  const [user, setUser] = useState(() => load('user', null))
  const [list, setList] = useState(() => load('list', []))
  const [convs, setConvs] = useState(loadConvs)
  const [cur, setCurState] = useState(null)
  const [, setCatalogTick] = useState(0)
  const [toastMsg, setToastMsg] = useState(null)
  const [gateLabel, setGateLabel] = useState(null)
  const [drawer, setDrawer] = useState(null)

  const curRef = useRef(cur)
  const convsRef = useRef(convs)
  const pendingRef = useRef(null)
  const toastT = useRef()
  convsRef.current = convs

  useEffect(() => { persist('user', user) }, [user])
  useEffect(() => { persist('list', list) }, [list])
  // Phim trong My List / lịch sử chat → lấy dữ liệu thật từ engine (thay dữ liệu mock của bản demo)
  useEffect(() => {
    const ids = [...new Set([...list, ...convs.flatMap((c) => c.msgs.flatMap((m) => [...(m.movies || []).map((x) => x.id), ...(m.compare || [])]))])]
    if (ids.length) loadMovies(ids).then((ok) => ok && setCatalogTick((t) => t + 1))
  }, [list]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { persist('convs', convs) }, [convs])

  const setCur = useCallback((id) => { curRef.current = id; setCurState(id) }, [])

  const toast = useCallback((t) => {
    setToastMsg(t)
    clearTimeout(toastT.current)
    toastT.current = setTimeout(() => setToastMsg(null), 2200)
  }, [])

  // Hành động cần đăng nhập: chạy ngay, hoặc mở popup và chạy sau khi login
  const requireAuth = useCallback((label, fn) => {
    if (user) return fn()
    pendingRef.current = fn
    setGateLabel(label)
  }, [user])
  // keepPending: ẩn popup để sang trang login nhưng vẫn giữ thao tác đang chờ
  const closeGate = useCallback((keepPending) => { setGateLabel(null); if (keepPending !== true) pendingRef.current = null }, [])

  const login = useCallback((name, email) => {
    setUser({ name, email })
    setList((l) => (l.length ? l : [27205, 666277, 496243, 329865, 313369]))
    setGateLabel(null)
    toast(`Xin chào ${name}! My List đã có sẵn vài phim mẫu.`)
    const p = pendingRef.current
    pendingRef.current = null
    return p
  }, [toast])
  const logout = useCallback(() => { setUser(null); toast('Đã đăng xuất') }, [toast])

  const toggleList = useCallback((id, title) => {
    setList((l) => (l.includes(id) ? l.filter((x) => x !== id) : [id, ...l]))
    toast(list.includes(id) ? `Đã bỏ ${title} khỏi My List` : `Đã thêm ${title} vào My List`)
  }, [list, toast])
  const removeFromList = useCallback((ids) => {
    setList((l) => l.filter((x) => !ids.includes(x)))
    toast(`Đã bỏ ${ids.length} phim khỏi My List`)
  }, [toast])

  const patchMsg = (cid, mid, data) =>
    setConvs((cs) => cs.map((c) => (c.id !== cid ? c : { ...c, msgs: c.msgs.map((m) => (m.id === mid ? { ...m, ...data } : m)) })))

  // Gửi một câu hỏi (text) hoặc thao tác (compare / similar / about) vào cuộc chat hiện tại
  const send = useCallback(async (input, { truncateAt } = {}) => {
    const label = labelOf(input)
    let cid = curRef.current
    const open = convsRef.current.find((c) => c.id === cid)
    if (open?.msgs.some((m) => m.role === 'ai' && !m.done)) return // AI đang trả lời dở
    if (!cid || !convsRef.current.some((c) => c.id === cid)) {
      cid = uid()
      setConvs((cs) => [{ id: cid, title: label.slice(0, 60), msgs: [] }, ...cs])
      setCur(cid)
    }
    const aiId = uid()
    // Chip lọc được giữ theo cuộc chat: câu hỏi mới mang theo filter của câu trả lời gần nhất
    if (input.text && !input.filters) {
      const lastAi = [...(open?.msgs || [])].reverse().find((m) => m.role === 'ai' && m.done)
      const keep = (lastAi?.filters || []).filter((f) => !f.relaxed)
      if (keep.length) input = { ...input, filters: keep }
    }
    // Hiện câu hỏi + khung "Đang suy luận" ngay, rồi cập nhật dần theo stream của engine
    setConvs((cs) => {
      const c = cs.find((x) => x.id === cid)
      if (!c) return cs
      const base = truncateAt != null ? c.msgs.slice(0, truncateAt) : c.msgs
      const next = { ...c, old: false, title: base.length ? c.title : label.slice(0, 60),
        msgs: [...base, { id: uid(), role: 'user', text: label }, { id: aiId, role: 'ai', done: false, step: 0, steps: ['Đang gửi câu hỏi…'] }] }
      return [next, ...cs.filter((x) => x.id !== cid)]
    })
    const streamed = await askStream(input, (ev) => {
      if (ev.type === 'steps') patchMsg(cid, aiId, { steps: ev.steps, step: ev.steps.length - 1 })
      if (ev.type === 'preview') patchMsg(cid, aiId, { movies: ev.movies })
    })
    if (streamed) { patchMsg(cid, aiId, { ...streamed, done: true }); return }
    // Không stream được (API tắt / lỗi) → gọi thường, rồi chạy hiệu ứng từng bước như bản demo
    const reply = await ask(input)
    patchMsg(cid, aiId, { steps: reply.steps, step: 0 })
    for (let i = 1; i < reply.steps.length; i++) { await sleep(STEP_MS); patchMsg(cid, aiId, { step: i }) }
    await sleep(STEP_MS)
    patchMsg(cid, aiId, { ...reply, done: true })
  }, [setCur])

  const newChat = useCallback(() => setCur(null), [setCur])
  const renameConv = useCallback((id, title) => setConvs((cs) => cs.map((c) => (c.id === id ? { ...c, title } : c))), [])
  const deleteConv = useCallback((id) => {
    const rest = convsRef.current.filter((c) => c.id !== id)
    setConvs(rest)
    if (curRef.current === id) setCur(rest[0]?.id ?? null)
    toast('Đã xoá cuộc trò chuyện')
  }, [setCur, toast])

  const value = useMemo(() => ({
    user, list, convs, cur, conv: convs.find((c) => c.id === cur) || null,
    toastMsg, gateLabel, drawer,
    setCur, toast, requireAuth, closeGate, login, logout, toggleList, removeFromList,
    send, newChat, renameConv, deleteConv, openDrawer: setDrawer, closeDrawer: () => setDrawer(null),
  }), [user, list, convs, cur, toastMsg, gateLabel, drawer, setCur, toast, requireAuth, closeGate, login, logout, toggleList, removeFromList, send, newChat, renameConv, deleteConv])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
