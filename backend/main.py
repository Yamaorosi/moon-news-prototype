from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Union
import requests
import os
import feedparser
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
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
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 設定 ---
# .env や環境変数に DATABASE_URL があれば Postgres、なければ SQLite
DATABASE_URL = os.getenv("DATABASE_URL")
DB_FILE = "news.db"

KEYS = [k for k in [
    os.getenv("GEMINI_API_KEY1"), 
    os.getenv("GEMINI_API_KEY2"),
    os.getenv("GEMINI_API_KEY3"),
    os.getenv("GEMINI_API_KEY4"),
    os.getenv("GEMINI_API_KEY")
] if k]

# --- DB接続の共通化 ---

def get_db_conn():
    if DATABASE_URL:
        # PostgreSQL (Railway)
        return psycopg2.connect(DATABASE_URL)
    else:
        # SQLite (Local)
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn

def get_cursor(conn):
    if DATABASE_URL:
        # PostgreSQLで辞書形式で結果を取得するための設定
        return conn.cursor(cursor_factory=RealDictCursor)
    else:
        return conn.cursor()

def get_placeholder():
    # PostgreSQLは %s、SQLiteは ? を使う
    return "%s" if DATABASE_URL else "?"

# --- DB操作 ---

def init():
    conn = get_db_conn()
    cursor = conn.cursor()
    # テーブル作成
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
    conn = get_db_conn()
    cursor = conn.cursor()
    p = get_placeholder()
    
    for i in items:
        try:
            if DATABASE_URL:
                # PostgreSQL (UPSERT)
                cursor.execute("""
                    INSERT INTO news (url, title, body)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (url) DO UPDATE SET
                    title = EXCLUDED.title,
                    body = EXCLUDED.body
                """, (i['url'], i['title'], i['body']))
            else:
                # SQLite (UPSERT)
                cursor.execute(f"""
                    INSERT OR REPLACE INTO news (url, title, body)
                    VALUES ({p}, {p}, {p})
                """, (i['url'], i['title'], i['body']))
        except Exception as e:
            print(f"DB Error: {e}")
    conn.commit()
    conn.close()

def load(limit=None):
    conn = get_db_conn()
    cursor = get_cursor(conn)
    query = "SELECT * FROM news ORDER BY at DESC"
    
    if limit:
        if DATABASE_URL:
            cursor.execute(query + f" LIMIT {limit}")
        else:
            cursor.execute(query + " LIMIT ?", (limit,))
    else:
        cursor.execute(query)
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# --- 外部API / 整形 (変更なし) ---

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
    url = "https://www3.nhk.or.jp/rss/news/cat0.xml"
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries[:10]:
        t = entry.title
        raw_body = getattr(entry, 'summary', "")
        items.append({
            "title": t,
            "url": entry.link,
            "body": fix(raw_body, t)
        })
    return items

def sing(title, body):
    if not KEYS: return "KEYなし。"
    for key in KEYS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
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

# --- エンドポイント ---

class Item(BaseModel):
    title: str
    body: str
    url: str
    poem: Optional[str] = None

class Poem(BaseModel):
    poem: str

@app.on_event("startup")
def startup():
    init()

@app.get("/news", response_model=List[Item])
def get_news(q: str = None):
    save(pull(q=q))
    return load(limit=3)

@app.get("/poem", response_model=Poem)
def get_poem(title: str):
    conn = get_db_conn()
    cursor = get_cursor(conn)
    p = get_placeholder()
    
    cursor.execute(f"SELECT body, poem FROM news WHERE title = {p}", (title,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(404, "ニュースなし")
    
    body = row['body']
    existing_poem = row['poem']
    
    if existing_poem:
        conn.close()
        return {"poem": existing_poem}
    
    p_text = sing(title, body)
    
    # 保存用の接続
    write_conn = get_db_conn()
    write_cursor = write_conn.cursor()
    write_cursor.execute(f"UPDATE news SET poem = {p} WHERE title = {p}", (p_text, title))
    write_conn.commit()
    write_conn.close()
    conn.close()
    return {"poem": p_text}

@app.get("/history")
def get_history():
    return load()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
