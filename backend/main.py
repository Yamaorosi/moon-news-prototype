from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import requests
import os
import feedparser
import urllib.parse
import sqlite3
import re
import html
from datetime import datetime
from dotenv import load_dotenv

import analysis

load_dotenv()
app = FastAPI(title="Moon News")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 設定 ---
DB = "news.db"
# 1〜4番のキー、および旧名のキーをすべて集める
KEYS = [k for k in [
    os.getenv("GEMINI_API_KEY1"), 
    os.getenv("GEMINI_API_KEY2"),
    os.getenv("GEMINI_API_KEY3"),
    os.getenv("GEMINI_API_KEY4"),
    os.getenv("GEMINI_API_KEY")
] if k]

# --- スキーマ ---

class Item(BaseModel):
    title: str
    body: str
    url: str
    poem: Optional[str] = None

class Poem(BaseModel):
    poem: str

class Stat(BaseModel):
    done: int
    rate: float

class Kanji(BaseModel):
    avg: float
    ratio: float

class Report(BaseModel):
    total: int
    poem_stats: Stat
    len_stats: dict
    kanji_stats: Kanji
    top: List[dict]
    at: str

# --- DB操作 ---

def init():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
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
    conn.close()

def save(items):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    for i in items:
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO news (url, title, body)
                VALUES (?, ?, ?)
            """, (i['url'], i['title'], i['body']))
        except Exception as e:
            print(f"DB Error: {e}")
    conn.commit()
    conn.close()

def load(limit=None):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if limit:
        cursor.execute("SELECT * FROM news ORDER BY at DESC LIMIT ?", (limit,))
    else:
        cursor.execute("SELECT * FROM news ORDER BY at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def note(title, poem):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("UPDATE news SET poem = ? WHERE title = ?", (poem, title))
    conn.commit()
    conn.close()

# --- 外部API / 整形 ---

def fix(raw, title=""):
    if not raw: return ""
    raw = raw.replace('<li>', '\n').replace('</li>', '')
    text = re.sub(r'<[^>]+>', '', raw)
    text = html.unescape(text)
    text = re.sub(r'\s{2,}', '\n', text)
    
    words = ['ニュース', '新聞', 'NEWS', '通信', 'オンライン', 'ドットコム', 'DIG', 'TIMES']
    domain = r'^[a-z0-9.-]+\.[a-z]{2,}$'

    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        if title and (line == title or title in line or line in title):
            if len(line) > 10: continue
        
        bad = False
        if len(line) < 30:
            if any(w in line for w in words) or re.match(domain, line, re.I):
                bad = True
        if any(s in line for s in ['NHK', 'Yahoo', '朝日', '読売', '産経', '共同']):
            if len(line) < 20: bad = True
        if bad: continue
        
        for w in words:
            line = re.sub(rf'\s+\S*?{w}$', '', line).strip()
        if line:
            lines.append(f"・{line}")
    return '\n'.join(lines)

def pull(q: str = None):
    # NHKニュースの主要ニュースRSS
    url = "https://www3.nhk.or.jp/rss/news/cat0.xml"
    
    # 検索(q)がある場合はGoogle Newsに戻るか、現状はNHK固定にする
    # NHKのRSSは静的なので検索クエリは効かないが、世界観を重視してNHK固定とする
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries[:10]:
        t = entry.title
        # NHKのRSSはsummaryに要約が入っている
        raw_body = getattr(entry, 'summary', "")
        items.append({
            "title": t,
            "url": entry.link,
            "body": fix(raw_body, t)
        })
    return items

def sing(title, body):
    if not KEYS: return "KEYなし。"
    
    # 登録されているキーを順番に試す
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
            # このキーがダメなら次へ
            continue
            
    # すべてのキーが全滅した場合
    return "杯を挙げんとして天を見れば、\n今宵、月は雲海の彼方なり。（API制限）"

# --- エンドポイント --

@app.on_event("startup")
def startup():
    init()

@app.get("/news", response_model=List[Item])
def get_news(q: str = None):
    save(pull(q=q))
    return load(limit=3)

@app.get("/poem", response_model=Poem)
def get_poem(title: str):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    # 1. まず既存の詩（キャッシュ）がないか確認
    cursor.execute("SELECT body, poem FROM news WHERE title = ?", (title,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(404, "ニュースなし")
    
    body, existing_poem = row
    if existing_poem:
        conn.close()
        return {"poem": existing_poem}
    
    # 2. なければ生成
    p = sing(title, body)
    cursor.execute("UPDATE news SET poem = ? WHERE title = ?", (p, title))
    conn.commit()
    conn.close()
    return {"poem": p}

@app.get("/analysis", response_model=Report)
def get_analysis():
    res = analysis.run(DB)
    if not res: raise HTTPException(404, "データなし")
    return res

@app.get("/history")
def get_history():
    return load()

# --- 静的ファイル ---
dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(dist):
    app.mount("/", StaticFiles(directory=dist, html=True), name="static")
    @app.exception_handler(404)
    async def custom_404(request, __):
        if not any(request.url.path.startswith(p) for p in ["/news", "/poem", "/analysis", "/history"]):
            return FileResponse(os.path.join(dist, "index.html"))
        raise HTTPException(404, "Not Found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
