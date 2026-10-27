import { byId } from '../data/movies'
import { similarity } from '../lib/ai'
import { useStore } from '../store'
import { Icon, Md, Meta, Poster, SimBlock } from './ui'

// Box phim trong khung chat. `still` = bản minh hoạ trên landing (không có nút)
export function MovieCard({ id, reason, sim, still }) {
  const { user, list, requireAuth, toggleList, openDrawer, send } = useStore()
  const m = byId[id]
  const saved = user && list.includes(id)
  return (
    <article className="mcard" style={still ? { animation: 'none' } : undefined}>
      <Poster m={m} />
      <div className="mcard-b">
        <h3>{m.title}</h3>
        <div className="meta"><Meta m={m} /></div>
        <p className="ov">{m.overview}</p>
        {sim && (
          <div className="mini-sim"><span>{sim.score}% tương đồng</span><span className="bar"><i style={{ width: `${sim.score}%` }} /></span></div>
        )}
        <div className="why"><strong>Hợp với bạn vì</strong> {reason || <span className="writing">đang viết lý do…</span>}</div>
        {!still && (
          <div className="acts">
            <button className={`act ${saved ? 'added' : ''}`} onClick={() => requireAuth('lưu phim vào My List', () => toggleList(id, m.title))}>
              <Icon name={saved ? 'check' : 'plus'} />{saved ? 'Đã lưu' : 'My List'}
            </button>
            <button className="act" onClick={() => requireAuth('xem chi tiết phim', () => openDrawer(id))}><Icon name="info" />Chi tiết</button>
            <button className="act" onClick={() => requireAuth('tìm phim tương tự', () => send({ type: 'similar', ids: [id] }))}><Icon name="similar" />Tương tự</button>
          </div>
        )}
      </div>
    </article>
  )
}

export function CompareBlock({ ids, pairs: real }) {
  const ms = ids.map((id) => byId[id])
  const maxR = Math.max(...ms.map((m) => m.rating))
  const known = ms.filter((m) => m.runtime > 0).map((m) => m.runtime)
  const minT = known.length > 1 ? Math.min(...known) : null  // thiếu dữ liệu thì không tô "ngắn nhất"
  const rows = [
    ['Loại', (m) => (m.kind === 'tv' ? 'Series' : 'Phim lẻ')],
    ['Năm', (m) => m.year],
    ['Đạo diễn', (m) => m.director || '—'],
    ['Thời lượng', (m) => (m.runtime > 0 ? `${m.runtime} phút${m.kind === 'tv' ? '/tập' : ''}` : 'Chưa có dữ liệu'), (m) => m.runtime === minT],
    ['Điểm', (m) => `★ ${m.rating}`, (m) => m.rating === maxR],
    ['Thể loại', (m) => m.genres.join(', ')],
    ['Không khí', (m) => m.mood],
    ['Chủ đề', (m) => m.keywords.slice(0, 3).join(', ')],
  ]
  const pairs = ms.flatMap((a, i) => ms.slice(i + 1).map((b) => [a, b]))
  return (
    <>
      <div className="cmp-wrap">
        <table className="cmp">
          <thead>
            <tr><th />{ms.map((m) => (
              <th key={m.id}><Poster m={m} /><div style={{ fontFamily: 'var(--display)', fontSize: 16 }}>{m.title}</div></th>
            ))}</tr>
          </thead>
          <tbody>
            {rows.map(([label, f, win]) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                {ms.map((m) => <td key={m.id} className={win?.(m) ? 'win' : ''}>{f(m)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pairs">
        {pairs.map(([a, b]) => (
          <div className="sim-card" key={a.id + '-' + b.id}>
            <SimBlock sim={real?.find((p) => (p.a === a.id && p.b === b.id) || (p.a === b.id && p.b === a.id))?.sim || similarity(a, b)} label={`${a.title} ↔ ${b.title}`} />
          </div>
        ))}
      </div>
    </>
  )
}

export function AiMessage({ msg, last }) {
  const { send } = useStore()
  const n = msg.done ? msg.steps.length : msg.step || 0
  return (
    <div className="ai">
      <i className="ai-av" />
      <div className="ai-body">
        <details className="think" open={!msg.done}>
          <summary><Icon name="spark" /> {msg.done ? `Đã suy luận qua ${msg.steps.length} bước` : 'Đang suy luận…'}</summary>
          <ol>
            {msg.steps.map((s, i) => (
              <li key={i} className={i < n ? 'done' : i === n ? 'now' : ''}><span className="dot" />{s}</li>
            ))}
          </ol>
        </details>
        {!msg.done && msg.movies && <div className="cards">{msg.movies.map((r) => <MovieCard key={r.id} {...r} />)}</div>}
        {msg.done && (
          <>
            {msg.filters?.length > 0 && (
              <div className="fchips">
                <span className="fchips-l">Đang lọc:</span>
                {msg.filters.map((f, i) => (
                  <span key={i} className={`fchip ${f.relaxed ? 'relaxed' : ''}`} title={f.relaxed ? 'Đã tự nới vì quá ít phim' : f.evidence ? `Từ câu: “${f.evidence}”` : ''}>
                    {f.label}{f.relaxed && ' (đã nới)'}
                    {last && !f.relaxed && msg.query && (
                      <button aria-label={`Bỏ lọc ${f.label}`} onClick={() => send({
                        type: 'refilter', query: msg.query, label: `Bỏ lọc: ${f.label}`,
                        filters: msg.filters.filter((x, j) => j !== i && !x.relaxed),
                      })}>✕</button>
                    )}
                  </span>
                ))}
                {last && <button className="fchip fchip-add" onClick={() => dispatchEvent(new CustomEvent('cm:prefill', { detail: 'Thêm điều kiện: ' }))}>+ Thêm</button>}
              </div>
            )}
            <p className="ai-text"><Md text={msg.text} /></p>
            {msg.clarify && (
              <div className="clarify">
                <div>{msg.clarify.question}</div>
                {last && (msg.clarify.options || []).length > 0 && (
                  <div className="chips">{msg.clarify.options.map((o, i) => (
                    <button key={o} className="chip" onClick={() => send({ ...(msg.clarify.inputs?.[i] || { text: o }), label: o })}>{o}</button>
                  ))}</div>
                )}
              </div>
            )}
            {msg.movies && <div className="cards">{msg.movies.map((r) => <MovieCard key={r.id} {...r} />)}</div>}
            {msg.compare && <CompareBlock ids={msg.compare} pairs={msg.pairs} />}
            {msg.verdict && <p className="verdict"><Md text={msg.verdict} /></p>}
            {last && msg.chips && (
              <div className="chips"><span className="fchips-l">Hỏi tiếp:</span>{msg.chips.map((c) => <button key={c} className="chip" onClick={() => send({ text: c })}>{c}</button>)}</div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
