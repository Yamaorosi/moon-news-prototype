from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests
import os
import random
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

app = FastAPI(title="Moon News API (Minimal Prototype)")

# Reactからのアクセスを許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 設定 ---
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"

import feedparser
import urllib.parse
import sqlite3
import re
from datetime import datetime

# --- データベース設定 ---
DB_PATH = "news_cache.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news (
            url TEXT PRIMARY KEY,
            title TEXT,
            source TEXT,
            published_at TEXT,
            description TEXT,
            poem TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# 起動時にDBを初期化
init_db()

# --- ユーティリティ ---
def clean_html(raw_html):
    """HTMLタグを取り除き、綺麗なテキストにする"""
    if not raw_html: return ""
    cleaner = re.compile('<.*?>')
    return re.sub(cleaner, '', raw_html).strip()

# --- サービスロジック ---

def fetch_news_from_rss(q: str = None):
    """1. ニュースを取得する（RSS）"""
    base_url = "https://news.google.com/rss"
    if q:
        encoded_q = urllib.parse.quote(q)
        url = f"{base_url}/search?q={encoded_q}&hl=ja&gl=JP&ceid=JP:ja"
    else:
        url = f"{base_url}?hl=ja&gl=JP&ceid=JP:ja"

    print(f"Fetching from RSS: {url}")
    feed = feedparser.parse(url)
    
    articles = []
    for entry in feed.entries[:5]: # 少し多めに取っておく
        articles.append({
            "title": entry.title,
            "source": getattr(entry, 'source', {}).get('title', 'Google News'),
            "url": entry.link,
            "published_at": getattr(entry, 'published', ""),
            "description": clean_html(getattr(entry, 'summary', ""))
        })
    return articles

def insert_news_to_db(articles):
    """2. ニュースをDBに保存する（重複は無視）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    count = 0
    for a in articles:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO news (url, title, source, published_at, description)
                VALUES (?, ?, ?, ?, ?)
            """, (a['url'], a['title'], a['source'], a['published_at'], a['description']))
            if cursor.rowcount > 0:
                count += 1
        except Exception as e:
            print(f"DB Insert Error: {e}")
    conn.commit()
    conn.close()
    print(f"Stored {count} new articles to DB.")

def get_news_from_db(limit=3):
    """3. DBから最新のニュースを引っ張り出す"""
    conn = sqlite3.connect(DB_PATH)
    # 辞書形式で取得できるように設定
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM news ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        results.append(dict(row))
    return results

# --- エンドポイント ---

@app.get("/news")
def get_news_endpoint(q: str = None):
    """
    1. 取得 -> 2. 保存 -> 3. 出力 の流れで実行する
    """
    # 最新を拾いに行く
    new_articles = fetch_news_from_rss(q=q)
    # DBに保存（既にあるものはスキップされる）
    insert_news_to_db(new_articles)
    # フロントに渡す分をDBから最新順で取得
    display_news = get_news_from_db(limit=3)
    
    if not display_news:
        raise HTTPException(status_code=404, detail="ニュースがありません")

    # フロントエンドの期待するキー名に変換
    return [{
        "title": n["title"],
        "source": n["source"],
        "url": n["url"],
        "publishedAt": n["published_at"],
        "description": n["description"],
        "imageUrl": "" # RSSは画像なし
    } for n in display_news]

@app.get("/poem")
def get_poem(title: str):
    """
    詩を生成し、ついでにDBの該当記事に詩を保存（分析用）
    """
    poem = interpret_with_gemini(title)
    
    # DBの更新（タイトルで紐付け）
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE news SET poem = ? WHERE title = ?", (poem, title))
    conn.commit()
    conn.close()
    
    return {"poem": poem}


@app.get("/history")
def get_history():
    """
    DBに保存されている全ニュースの履歴を返す。
    分析や中身の確認用。
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM news ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/status")
def status():
    return {"status": "ok", "concept": "月下読酌"}

# --- Reactのビルド成果物（dist）を配信する設定 ---
# 本番環境（Renderなど）で、ビルドされたフロントエンドを配信する
# frontend/dist フォルダが存在する場合のみマウントする
frontend_dist_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.exists(frontend_dist_path):
    app.mount("/", StaticFiles(directory=frontend_dist_path, html=True), name="static")

    @app.exception_handler(404)
    async def custom_404_handler(request, __):
        # API以外のパスで404になったら、Reactのindex.htmlを返す（SPA対応）
        if not request.url.path.startswith("/news") and not request.url.path.startswith("/poem") and not request.url.path.startswith("/status"):
            return FileResponse(os.path.join(frontend_dist_path, "index.html"))
        raise HTTPException(status_code=404, detail="Not Found")
