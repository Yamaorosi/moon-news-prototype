from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import requests
import os
import feedparser
import psycopg2
from psycopg2.extras import RealDictCursor
import re
import html
from datetime import datetime, timedelta
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

# --- データベース設定 ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. PostgreSQL connection is required.")

# --- APIキー設定 ---
KEYS = [k for k in [
    os.getenv("GEMINI_API_KEY1"), 
    os.getenv("GEMINI_API_KEY2"),
    os.getenv("GEMINI_API_KEY3"),
    os.getenv("GEMINI_API_KEY4"),
    os.getenv("GEMINI_API_KEY")
] if k]

# --- 簡易キャッシュ設定 ---
# 注: シングルワーカー環境（Railway Trialなど）でのみ有効。スケール時はRedis等を検討。
news_cache = {"data": None, "last_updated": datetime.min}
CACHE_TTL = timedelta(minutes=5)

# --- データベース操作 ---

def get_db_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """初期テーブル作成"""
    with get_db_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    body TEXT,
                    poem TEXT,
                    at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()

def save_news(items):
    """ニュースをDBに一括保存 (UPSERT)"""
    with get_db_conn() as conn:
        with conn.cursor() as cursor:
            data = [(i['url'], i['title'], i['body']) for i in items]
            cursor.executemany("""
                INSERT INTO news (url, title, body)
                VALUES (%s, %s, %s)
                ON CONFLICT (url) DO UPDATE SET
                title = EXCLUDED.title,
                body = EXCLUDED.body
            """, data)
        conn.commit()

def load_news(limit: int = 3):
    """DBからニュースを取得"""
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = "SELECT * FROM news ORDER BY at DESC LIMIT %s"
            cursor.execute(query, (limit,))
            return [dict(row) for row in cursor.fetchall()]

# --- 外部API / 整形 ---

def clean_text(text: str) -> str:
    """HTMLタグの除去と基本的なクリーンアップ"""
    if not text: return ""
    text = text.replace('<li>', '\n').replace('</li>', '')
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    return re.sub(r'\s{2,}', '\n', text)

def filter_noise(text: str, title: str) -> str:
    """ニュース本文からノイズを除去して箇条書きに整形"""
    words = ['ニュース', '新聞', 'NEWS', '通信', 'オンライン', 'ドットコム', 'DIG', 'TIMES']
    domain_pattern = r'^[a-z0-9.-]+\.[a-z]{2,}$'
    
    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        if title and (line == title or title in line or line in title):
            if len(line) > 10: continue
        
        is_noise = False
        if len(line) < 30:
            if any(w in line for w in words) or re.match(domain_pattern, line, re.I):
                is_noise = True
        if any(s in line for s in ['NHK', 'Yahoo', '朝日', '読売', '産経', '共同']):
            if len(line) < 20: is_noise = True
        
        if not is_noise:
            for w in words:
                line = re.sub(rf'\s+\S*?{w}$', '', line).strip()
            if line:
                lines.append(f"・{line}")
    return '\n'.join(lines)

def fix(raw: str, title: str = "") -> str:
    """RSSの生データをクリーンアップして整形"""
    text = clean_text(raw)
    return filter_noise(text, title)

def pull():
    """NHKニュースRSSから最新記事を取得"""
    rss_url = "https://www3.nhk.or.jp/rss/news/cat0.xml"
    feed = feedparser.parse(rss_url)
    items = []
    for entry in feed.entries[:10]:
        t = entry.title
        items.append({
            "title": t,
            "url": entry.link,
            "body": fix(getattr(entry, 'summary', ""), t)
        })
    return items

def sing(title, body):
    """Gemini APIを使用してポエムを生成"""
    if not KEYS: return "KEYなし。"
    for key in KEYS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
        prompt = f"あなたは李白。4行の絶句を詠め。\n題: {title}\n録: {body}\n詩:"
        try:
            res = requests.post(url, headers={'Content-Type': 'application/json'}, 
                                json={"contents": [{"parts": [{"text": prompt}]}]},
                                timeout=10)
            res.raise_for_status()
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception:
            continue
    return "杯を挙げんとして天を見れば、\n今宵、月は雲海の彼方なり。（API制限）"

# --- アプリケーション設定 ---

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

# --- スキーマ ---

class Item(BaseModel):
    title: str
    body: str
    url: str
    poem: Optional[str] = None

class PoemResponse(BaseModel):
    poem: str

# --- エンドポイント ---

@app.get("/news", response_model=List[Item])
def get_news():
    global news_cache
    if news_cache["data"] and (datetime.now() - news_cache["last_updated"] < CACHE_TTL):
        return news_cache["data"]

    items = pull()
    save_news(items)
    
    res = load_news(limit=3)
    news_cache = {"data": res, "last_updated": datetime.now()}
    return res

@app.get("/poem", response_model=PoemResponse)
def get_poem(title: str):
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT body, poem FROM news WHERE title = %s", (title,))
            row = cursor.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="ニュースが見つかりません")
            
            body = row['body']
            existing_poem = row['poem']
            
            if existing_poem and "API制限" not in existing_poem:
                return {"poem": existing_poem}
            
            p_text = sing(title, body)
            if "API制限" not in p_text:
                cursor.execute("UPDATE news SET poem = %s WHERE title = %s", (p_text, title))
                conn.commit()
            
            return {"poem": p_text}

@app.get("/history")
def get_history():
    return load_news(limit=50)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
