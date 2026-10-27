// ask() gọi engine thật (backend/app/main.py). Không gọi được API → dùng mock respond() để demo vẫn chạy.
// Shape trả về: { steps, text, movies?: [{ id, reason, sim? }], compare?, verdict?, chips?,
//                 filters?: [{ field, value, label, relaxed? }], clarify?: { question, options, inputs }, query? }
// sim = { score: 0–100, parts: { 'Nội dung', 'Chủ đề', 'Đội ngũ': 0–1 } }
import { movies, byId, registerMovies, setTrending } from '../data/movies'

export const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function ask(input) {
  try {
    const r = await fetch(`${API}/api/ask`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
    if (!r.ok) throw new Error(`API ${r.status}`)
    const res = await r.json()
    registerMovies(res.catalog)
    delete res.catalog
    return res
  } catch (e) {
    console.warn('Engine không phản hồi, dùng mock:', e)
    return respond(input.type === 'refilter' ? { text: input.query?.text || '' } : input)
  }
}

// Stream NDJSON: onEvent({type:'steps'|'preview'}), trả về kết quả cuối (hoặc null nếu không stream được)
export async function askStream(input, onEvent) {
  try {
    const r = await fetch(`${API}/api/ask/stream`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
    if (!r.ok || !r.body) return null
    const reader = r.body.getReader(), dec = new TextDecoder()
    let buf = '', final = null
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      let i
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i).trim()
        buf = buf.slice(i + 1)
        if (!line) continue
        const ev = JSON.parse(line)
        if (ev.catalog) { registerMovies(ev.catalog); delete ev.catalog }
        if (ev.type === 'final') { delete ev.type; final = ev } else if (ev.type === 'error') return null
        else onEvent(ev)
      }
    }
    return final
  } catch (e) {
    console.warn('Không stream được, dùng gọi thường:', e)
    return null
  }
}

export async function loadSimilar(id, n = 4) {
  try {
    const r = await fetch(`${API}/api/similar?id=${id}&n=${n}`)
    if (!r.ok) return null
    const d = await r.json()
    registerMovies(d.catalog)
    return d.items
  } catch { return null }
}

export async function loadPair(a, b) {
  try {
    const r = await fetch(`${API}/api/pair?a=${a}&b=${b}`)
    if (!r.ok) return null
    const d = await r.json()
    registerMovies(d.catalog)
    return d.sim
  } catch { return null }
}

export async function loadMovies(ids) {
  try {
    const r = await fetch(`${API}/api/movies?ids=${ids.slice(0, 100).join(',')}`)
    if (!r.ok) return false
    registerMovies(await r.json())
    return true
  } catch { return false }
}

export async function loadTrending() {
  try {
    const r = await fetch(`${API}/api/trending`)
    if (!r.ok) return false
    const t = await r.json()
    registerMovies(t.catalog)
    setTrending(t)
    return true
  } catch { return false }
}

const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[đĐ]/g, 'd').toLowerCase()

const jaccard = (a, b) => {
  const A = new Set(a), B = new Set(b)
  const n = [...A].filter((x) => B.has(x)).length
  return n / (A.size + B.size - n || 1)
}

// Mô phỏng: dense (nội dung) + jaccard (chủ đề) + metadata (đội ngũ, thời kỳ)
export function similarity(a, b) {
  const topic = jaccard([...a.genres, ...a.keywords], [...b.genres, ...b.keywords])
  const content = Math.min(1, 0.35 + jaccard(a.genres, b.genres) * 0.5 + topic * 0.6 + (a.mood.split(',')[0] === b.mood.split(',')[0] ? 0.15 : 0))
  const team = Math.min(1, (a.director === b.director ? 0.7 : 0) + (a.cast.some((c) => b.cast.includes(c)) ? 0.3 : 0) + Math.max(0, 0.3 - Math.abs(a.year - b.year) / 40))
  const t = Math.min(1, topic * 2.2)
  return { score: Math.round((0.55 * content + 0.25 * t + 0.2 * team) * 100), parts: { 'Nội dung': content, 'Chủ đề': t, 'Đội ngũ': team } }
}

export function similarTo(ids, n = 4) {
  return movies
    .filter((m) => !ids.includes(m.id))
    .map((m) => ({ id: m.id, sim: ids.map((id) => similarity(byId[id], m)).reduce((x, y) => (y.score > x.score ? y : x)) }))
    .sort((x, y) => y.sim.score - x.sim.score)
    .slice(0, n)
}

const INTENTS = [
  { k: ['nolan', 'xoan nao', 'hack nao', 'twist', 'khoa hoc vien tuong', 'sci-fi', 'scifi', 'vu tru'],
    text: 'Bạn thích kiểu phim bắt não chạy hết công suất. Mình lọc ra những phim có cấu trúc nhiều tầng, ý tưởng khoa học lớn và cái kết khiến bạn muốn xem lại:',
    picks: [[27205, 'Cấu trúc giấc mơ lồng nhau, đỉnh cao của thể loại xoắn não.'], [329865, 'Cú twist về thời gian tinh tế, cảm xúc sâu hơn phim Nolan.'], [157336, 'Khoa học nghiêm túc đi cùng câu chuyện cha con.'], [545611, 'Đa vũ trụ điên rồ nhưng lõi là tình mẹ con rất đời.']],
    chips: ['Ngắn hơn 2 tiếng thôi', 'So sánh Inception và Arrival', 'Phim giống Interstellar'] },
  { k: ['nhe nhang', 'lang man', 'tinh cam', 'hen ho', 'nguoi yeu', 'chill', 'thu gian', 'buon', 'ngan hon'],
    text: 'Một buổi tối nhẹ nhàng cần phim đẹp, nhịp chậm và để lại dư vị. Đây là những lựa chọn mình thấy hợp nhất:',
    picks: [[666277, 'Nhẹ như một tiếng thở dài, xem xong sẽ nghĩ về nó cả tuần.'], [313369, 'Âm nhạc, màu sắc và một cái kết đẹp đến day dứt.'], [372058, 'Hình ảnh tuyệt đẹp, lãng mạn mà không sến.'], [120467, 'Duyên dáng, hài hước kiểu Wes Anderson, chỉ 99 phút.']],
    chips: ['Có phim nào vui hơn không?', 'Chỉ phim Hàn thôi', 'So sánh La La Land và Past Lives'] },
  { k: ['han quoc', 'phim han', 'korea', 'kdrama'],
    text: 'Điện ảnh Hàn đang ở phong độ rất cao. Mình chọn 3 phim ở 3 gu khác nhau để bạn dễ chọn:',
    picks: [[496243, 'Oscar Phim hay nhất, châm biếm giai cấp với cú twist khó đoán.'], [396535, 'Phim zombie trên tàu nhưng thực chất là phim về tình cha con.'], [666277, 'Nếu muốn nhẹ nhàng: chuyện duyên phận của người Hàn xa xứ.']],
    chips: ['So sánh Parasite và Get Out', 'Phim giống Parasite'] },
  { k: ['hoat hinh', 'anime', 'gia dinh', 'tre con', 'con nho', 'ghibli', 'ca nha'],
    text: 'Phim hoạt hình hay thì người lớn xem còn khóc nhiều hơn trẻ con. Đây là những phim cả nhà đều mê:',
    picks: [[129, 'Kinh điển của Ghibli, thế giới tưởng tượng phong phú bậc nhất.'], [354912, 'Về gia đình và ký ức. Nhớ chuẩn bị khăn giấy.'], [569094, 'Phong cách hình ảnh đột phá, hành động mãn nhãn.'], [372058, 'Lãng mạn tuổi học trò, hợp với teen trở lên.']],
    chips: ['Phim giống Spirited Away', 'So sánh Coco và Your Name'] },
  { k: ['kinh di', 'hoi hop', 'giat gan', 'rung ron', 'trinh tham', 'bi an'],
    text: 'Muốn tim đập nhanh mà vẫn có chiều sâu? Đây là những phim hồi hộp có kịch bản thông minh, không chỉ hù dọa:',
    picks: [[419430, 'Kinh dị tâm lý xuất sắc, càng nghĩ càng rợn.'], [396535, 'Nhịp phim không cho bạn thở, nhưng cái kết rất cảm động.'], [546554, 'Hồi hộp kiểu trinh thám, vui và lắt léo.'], [496243, 'Nửa sau leo thang căng thẳng đến khó tin.']],
    chips: ['Ít máu me hơn', 'So sánh Get Out và Knives Out'] },
  { k: ['hanh dong', 'action', 'bom tan', 'chay no', 'sieu anh hung'],
    text: 'Đây là những bom tấn hành động có chất lượng điện ảnh thật sự, không chỉ cháy nổ:',
    picks: [[76341, 'Rượt đuổi 2 tiếng không nghỉ, hành động quay bằng xe thật.'], [155, 'Phim siêu anh hùng hay nhất mọi thời, nhờ Joker của Heath Ledger.'], [693134, 'Quy mô sử thi, đáng xem nhất ở rạp IMAX.'], [569094, 'Hành động hoạt hình sáng tạo nhất thập kỷ.']],
    chips: ['So sánh Dune 2 và Mad Max', 'Phim giống The Dark Knight'] },
]

const FALLBACK = {
  text: 'Mình chưa rõ bạn đang tìm kiểu phim nào. Bạn có thể kể thêm thể loại, tâm trạng tối nay, hay một phim bạn từng rất thích. Trong lúc đó, đây là những phim được đánh giá cao nhất tuần này:',
  picks: [[693134, 'Đang dẫn đầu thịnh hành tuần, bom tấn sử thi.'], [666277, 'Phim nhỏ nhưng được giới phê bình khen hết lời.'], [496243, 'Ai cũng nên xem ít nhất một lần.']],
  chips: ['Phim giống Inception', 'Phim nhẹ nhàng tối nay', 'Phim Hàn Quốc hay', 'Phim hoạt hình cho cả nhà'],
}
export const STARTER_CHIPS = FALLBACK.chips

const findTitle = (s) => {
  const w = norm(s).trim().replace(/^phim\s+/, '')
  return movies.find((m) => norm(m.title).startsWith(w.split(' ')[0]) || norm(m.title).includes(w))
}

export function labelOf(input) {
  if (input.label) return input.label
  if (input.text) return input.text
  if (input.type === 'refilter') return `Lọc lại: ${input.query?.text || ''}`
  if (input.type === 'compare') return `So sánh ${input.ids.map((id) => byId[id].title).join(' và ')}`
  if (input.type === 'similar') return `Tìm phim giống ${input.ids.map((id) => byId[id].title).join(', ')}`
  return `Kể mình nghe về ${byId[input.id].title}`
}

export function respond(input) {
  if (input.type === 'compare') return compareReply(input.ids)
  if (input.type === 'similar') return similarReply(input.ids)
  if (input.type === 'about') return aboutReply(input.id)
  const q = norm(input.text)
  const cmp = q.match(/so sanh (.+?) (?:va|voi|vs) (.+)/)
  if (cmp) {
    const a = findTitle(cmp[1]), b = findTitle(cmp[2])
    if (a && b && a.id !== b.id) return compareReply([a.id, b.id])
  }
  const like = q.match(/giong (.+)/)
  if (like) {
    const m = findTitle(like[1].replace(/nhung.*$/, ''))
    if (m) return similarReply([m.id])
  }
  const it = INTENTS.find((i) => i.k.some((k) => q.includes(k))) || FALLBACK
  return {
    steps: ['Phân tích yêu cầu & gu của bạn', `Truy xuất ${(1240 + q.length * 37).toLocaleString('vi-VN')} phim từ kho dữ liệu`, 'Lọc & xếp hạng theo độ phù hợp', 'Viết giải thích cho từng gợi ý'],
    text: it.text,
    movies: it.picks.map(([id, reason]) => ({ id, reason })),
    chips: it.chips,
  }
}

function similarReply(ids) {
  return {
    steps: ['Đọc hồ sơ phim gốc', 'Tính tương đồng: dense + keyword + metadata', 'Lọc trùng & xếp hạng', 'Giải thích điểm giống nhau'],
    text: `Đây là những phim gần nhất với ${ids.map((id) => `**${byId[id].title}**`).join(', ')}. Điểm % tổng hợp từ độ giống về nội dung, chủ đề và đội ngũ sản xuất:`,
    movies: similarTo(ids).map(({ id, sim }) => {
      const top = Object.entries(sim.parts).sort((a, b) => b[1] - a[1])[0][0]
      return { id, sim, reason: `Giống nhất ở ${top.toLowerCase()}. Không khí phim ${byId[id].mood.toLowerCase()}.` }
    }),
    chips: ['Phim nhẹ nhàng hơn', 'Phim hành động bom tấn'],
  }
}

function compareReply(ids) {
  const ms = ids.map((id) => byId[id])
  const best = [...ms].sort((a, b) => b.rating - a.rating)[0]
  const short = [...ms].sort((a, b) => a.runtime - b.runtime)[0]
  return {
    steps: ['Tải hồ sơ các phim', 'Đối chiếu nội dung, nhịp phim, đội ngũ', 'Tính độ tương đồng từng cặp', 'Viết kết luận'],
    text: `So sánh nhanh ${ms.map((m) => `**${m.title}**`).join(' và ')}:`,
    compare: ids,
    verdict: best === short
      ? `**${best.title}** thắng cả hai mặt: điểm cao nhất (${best.rating}) và ngắn nhất (${best.runtime} phút). Tối nay xem phim này là hợp lý.`
      : `Nếu chỉ chọn một, **${best.title}** có điểm cao nhất (${best.rating}). Nếu tối nay ít thời gian, **${short.title}** chỉ ${short.runtime} phút, không khí ${short.mood.toLowerCase()}.`,
    chips: ['Tìm phim giống cả hai', 'Phim nhẹ nhàng tối nay'],
  }
}

function aboutReply(id) {
  const m = byId[id]
  return {
    steps: ['Truy xuất thông tin phim', 'Tổng hợp review từ nhiều nguồn', 'Viết tóm tắt'],
    text: `**${m.title}** (${m.year}) của ${m.director}. ${m.overview} Khán giả nhận xét phim ${m.mood.toLowerCase()}, điểm trung bình ${m.rating}/10. Bạn sẽ thích nếu từng mê những phim về ${m.keywords.slice(0, 2).join(' và ')}.`,
    movies: [{ id, reason: `Đang nằm trong top thịnh hành. Không khí ${m.mood.toLowerCase()}.` }],
    chips: [`Phim giống ${m.title}`, 'Phim nhẹ nhàng tối nay'],
  }
}
