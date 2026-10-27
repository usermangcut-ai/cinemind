// Gộp dữ liệu phim vào template → cinemind.html (1 file duy nhất)
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { movies, trending } from '../src/data/movies.js'
const hue = { 27205: 212, 157336: 32, 155: 225, 872585: 14, 329865: 190, 335984: 24, 693134: 36, 496243: 140, 396535: 2, 666277: 335, 313369: 265, 244786: 45, 129: 168, 372058: 245, 354912: 300, 569094: 318, 76341: 22, 419430: 95, 546554: 8, 120467: 342, 545611: 285, 278: 200, 475557: 120 }
// Poster thật nhúng base64 (artifact chặn ảnh từ host ngoài)
const img = (id) => { const f = new URL(`./posters/${id}.jpg`, import.meta.url); return existsSync(f) ? 'data:image/jpeg;base64,' + readFileSync(f).toString('base64') : null }
const data = movies.map(({ poster, ...m }) => ({ ...m, hue: hue[m.id], img: img(m.id) }))
const tpl = readFileSync(new URL('./template.html', import.meta.url), 'utf8')
writeFileSync(new URL('./cinemind.html', import.meta.url), tpl.replace('/*__DATA__*/[]', JSON.stringify(data)).replace('/*__TREND__*/{}', JSON.stringify(trending)))
console.log('built', data.length, 'movies')
