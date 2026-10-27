import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
LLM_BASE_URL = os.environ["LLM_BASE_URL"]
LLM_API_KEY = os.environ["LLM_API_KEY"]
AUX_API_KEY = os.getenv("AUX_API_KEY") or LLM_API_KEY  # embedding + Jev (có thể khác nhóm kênh với key LLM)
LLM_MODEL_ONLINE = os.getenv("LLM_MODEL_ONLINE", "gpt-4.1-mini")
LLM_MODEL_OFFLINE = os.getenv("LLM_MODEL_OFFLINE", "gpt-4.1-mini")
LLM_MODEL_PARSE = os.getenv("LLM_MODEL_PARSE", "gpt-4.1-mini")  # ①: ổn định hơn gpt-5.4-mini khi trích filter
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")  # trống → gọi Jev qua provider LLM ({LLM_BASE_URL}/systemone)
RERANK = os.getenv("RERANK", "jev")                     # jev | qwen | llm
JEV_CONCURRENCY = int(os.getenv("JEV_CONCURRENCY", "20"))
JEV_TOP = int(os.getenv("JEV_TOP", "40"))                 # số phim đưa vào bước ⑥ chấm (Jev hoặc qwen)
POOL_N = int(os.getenv("POOL_N", "40"))                   # ⑤ giữ bao nhiêu phim sau MMR                 # số phim đưa vào Jev chấm (giá ~0,03 cent/phim)
