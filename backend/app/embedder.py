"""Embedding dùng chung cho ETL, eval và engine.

model = "bge-m3"                → chạy local (FlagEmbedding, CPU)
model = tên khác                → gọi /embeddings của provider OpenAI-compatible
Vector trả về đã chuẩn hoá L2 (cosine = tích vô hướng).
"""
import time

import httpx
import numpy as np

from app import config

_bge = None


def _bge_model():
    global _bge
    if _bge is None:
        from FlagEmbedding import BGEM3FlagModel
        _bge = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False, devices="cpu")
    return _bge


def _normalize(m):
    m = np.asarray(m, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True).clip(1e-12)


def _api(texts, model, batch=64):
    out = []
    headers = {"Authorization": f"Bearer {config.AUX_API_KEY}"}
    with httpx.Client(base_url=config.LLM_BASE_URL, headers=headers, timeout=120) as c:
        for i in range(0, len(texts), batch):
            chunk = texts[i:i + batch]
            for attempt in range(7):
                try:
                    r = c.post("/embeddings", json={"model": model, "input": chunk})
                    r.raise_for_status()
                    data = sorted(r.json()["data"], key=lambda d: d["index"])
                    out.extend(d["embedding"] for d in data)
                    break
                except httpx.HTTPError:
                    if attempt == 6:
                        raise
                    time.sleep(min(30, 2 * 2 ** attempt))  # 429 của provider thường hết sau vài chục giây
    return _normalize(out)


def embed(texts, model=None):
    model = model or config.EMBED_MODEL
    if model == "bge-m3":
        return _normalize(_bge_model().encode(texts, batch_size=16, max_length=512)["dense_vecs"])
    return _api(texts, model)


def movie_text(m):
    """Đoạn văn đại diện cho 1 phim — cùng 1 công thức cho mọi model."""
    head = f"{m['title']} ({m['year']})" + (f" — {m['title_vi']}" if m.get("title_vi") else "")
    parts = [
        head,
        f"Thể loại: {', '.join(m['genres'])}" if m.get("genres") else "",
        f"Hồ sơ: {m['profile']}" if m.get("profile") else "",
        f"Tóm tắt: {m['overview']}" if m.get("overview") else "",
        f"Từ khoá: {', '.join(m['keywords'][:20])}" if m.get("keywords") else "",
        f"Đạo diễn: {', '.join(m['director'])}" if m.get("director") else "",
    ]
    return "\n".join(p for p in parts if p)
