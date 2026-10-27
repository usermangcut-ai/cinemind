# CineMind — frontend

React 18 + Vite. Gọi engine ở `../backend` (stream kết quả); API tắt thì tự dùng mock để demo vẫn chạy.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # build ra dist/
```

## Trang
| Route | Nội dung | Cần đăng nhập |
|---|---|---|
| `/` | Landing | Không |
| `/chat` | Chat 3 cột: lịch sử · chat · top 10 tuần/tháng | Không (lưu phim, chi tiết, tương tự thì cần) |
| `/list` | My List: tick 1 phim → tìm tương tự, 2–3 phim → so sánh | Có |
| `/login` | Đăng nhập giả lập (email hợp lệ + mật khẩu ≥ 6 ký tự, hoặc tài khoản demo) | — |

## Cấu trúc
```
src/
  data/movies.js      byId (phim mẫu + phim nạp từ API, cache localStorage) + top 10
  lib/ai.js           gọi engine: ask / askStream / loadSimilar / loadPair / loadMovies / loadTrending (+ mock dự phòng)
  store.jsx           state chung: user, My List, các cuộc chat, popup đăng nhập, drawer, toast
  components/         ui (Poster, Icon…), movies (box phim, bảng so sánh, tin nhắn AI), layout (TopBar, drawer, popup)
  pages/              Landing, Chat, MyList, Login
mockup/               bản HTML 1 file dùng để demo nhanh
```

## Engine thật (đã nối)
`ask()` trong `src/lib/ai.js` gọi backend (`../backend/`, xem `../backend/README.md`) tại `VITE_API_URL` (mặc định `http://localhost:8000`).
Không gọi được API → tự dùng mock để demo vẫn chạy.

```bash
cd ../backend && docker compose up -d && .venv/Scripts/python -m uvicorn app.main:app --port 8000
npm run dev     # trong frontend/ → http://localhost:5173/chat
```
Hợp đồng input/output: `../docs/engine-design.md` §5 (thêm `filters`, `clarify`, `query` so với bản mock).
Lưu trữ (user, My List, lịch sử chat) vẫn ở `localStorage`; phim lấy từ API được cache ở `localStorage['cm_catalog']`.
