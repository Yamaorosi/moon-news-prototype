from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import analysis

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set.")

def get_db_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    with get_db_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    body TEXT,
                    poem TEXT,
                    kanji_count INTEGER,
                    kanji_ratio REAL,
                    season TEXT,
                    jieqi TEXT,
                    at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Moon News", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TodayResponse(BaseModel):
    title: str
    body: str
    url: str
    poem: Optional[str] = None
    season: Optional[str] = None
    jieqi: Optional[str] = None

@app.get("/today", response_model=TodayResponse)
def get_today():
    """今日の1件を返す。バッチ未実行なら404。"""
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT * FROM news
                WHERE at::date = CURRENT_DATE
                ORDER BY at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="今日の記事はまだありません")
    return dict(row)

@app.get("/history")
def get_history():
    """過去の記録を返す。"""
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM news ORDER BY at DESC LIMIT 100")
            return [dict(r) for r in cursor.fetchall()]

@app.get("/news")
def get_news():
    """フロントエンド互換用。最新1件のみを返す。"""
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM news ORDER BY at DESC LIMIT 1")
            return [dict(r) for r in cursor.fetchall()]

@app.get("/poem")
def get_poem(title: str):
    """特定の記事のポエムを返す。"""
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT poem FROM news WHERE title = %s", (title,))
            row = cursor.fetchone()
            if row:
                return {"poem": row["poem"]}
    return {"poem": "月は雲に隠れてしまいました..."}

@app.get("/analysis")
def get_analysis():
    """データ分析結果を返す。"""
    res = analysis.run()
    if res is None:
        raise HTTPException(status_code=404, detail="分析データがありません")
    return res

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)