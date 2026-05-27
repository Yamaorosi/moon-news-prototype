from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import requests
import os
import random
import feedparser
import urllib.parse
import sqlite3
import re
import pandas as pd
import json
import html
from datetime import datetime
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

app = FastAPI(title="Moon News API (Consolidated Prototype)")

# Reactからのアクセスを許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 設定 ---
DB_PATH = "news_cache.db"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# --- スキーマ (Pydanticモデル) ---

class NewsArticle(BaseModel):
    title: str
    description: str
    url: str
    poem: Optional[str] = None

class PoemResponse(BaseModel):
    poem: str

class PoemStats(BaseModel):
    generated_count: int
    generation_rate_percent: float

class KanjiStats(BaseModel):
    avg_count: float
    avg_ratio: float

class AnalysisResponse(BaseModel):
    total_articles: int
    poem_stats: PoemStats
    body_len_stats: dict
    kanji_stats: KanjiStats
    top_kanji_articles: List[dict]
    last_updated: str

# --- データベース関連 ---

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

def save_news(articles):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    count = 0
    for a in articles:
        try:
            # 常に最新の（クリーンな）内容で上書きするために REPLACE を使用
            cursor.execute("""
                INSERT OR REPLACE INTO news (url, title, source, published_at, description)
                VALUES (?, ?, ?, ?, ?)
            """, (a['url'], a['title'], a['source'], a['published_at'], a['description']))
            if cursor.rowcount > 0:
                count += 1
        except Exception as e:
            print(f"DB Error: {e}")
    conn.commit()
    conn.close()

def load_news(limit=3):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM news ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def set_poem(title, poem):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE news SET poem = ? WHERE title = ?", (poem, title))
    conn.commit()
    conn.close()

# --- サービスロジック (外部API/ユーティリティ) ---

def clean(raw, title=""):
    """HTMLタグを取り除き、実体参照を戻し、汎用的なパターンで出典名やタイトルとの重複を削る"""
    if not raw: return ""
    raw = raw.replace('<li>', '\n').replace('</li>', '')
    text = re.sub(r'<[^>]+>', '', raw)
    text = html.unescape(text)
    text = re.sub(r'\s{2,}', '\n', text)
    
    # 出典とみなすキーワード
    source_keywords = [
        'ニュース', '新聞', 'NEWS', '通信', 'オンライン', 'ドットコム', 'DIG', 'TIMES', 'Online'
    ]
    domain_pattern = r'^[a-z0-9.-]+\.[a-z]{2,}$'

    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        
        # 0. タイトルと重複している場合は削除
        if title and (line == title or title in line or line in title):
            if len(line) > 10: # ある程度の長さの一致があればスキップ
                continue

        # 出典判定フラグ
        is_source = False
        
        # 1. 非常に短い行で、出典キーワードを含む、またはドメインっぽい
        if len(line) < 30:
            if any(k in line for k in source_keywords) or re.match(domain_pattern, line, re.I):
                is_source = True
        
        # 2. 李白の詩情を削がないための特定メディア名
        if any(s in line for s in ['NHK', 'Yahoo', '朝日', '読売', '産経', '共同']):
            if len(line) < 20: is_source = True

        if is_source: continue
        
        # 3. 行の末尾に出典名がくっついている場合の掃除（汎用）
        for k in source_keywords:
            line = re.sub(rf'\s+\S*?{k}$', '', line).strip()

        if line:
            lines.append(f"・{line}")
        
    return '\n'.join(lines)

def fetch(q: str = None):
    """Google News RSSからニュースを取得する"""
    base_url = "https://news.google.com/rss"
    if q:
        encoded_q = urllib.parse.quote(q)
        url = f"{base_url}/search?q={encoded_q}&hl=ja&gl=JP&ceid=JP:ja"
    else:
        url = f"{base_url}?hl=ja&gl=JP&ceid=JP:ja"

    feed = feedparser.parse(url)
    
    articles = []
    for entry in feed.entries[:10]:
        # タイトル自体を先に取得しておく
        title = entry.title
        articles.append({
            "title": title,
            "source": getattr(entry, 'source', {}).get('title', 'Google News'),
            "url": entry.link,
            "published_at": getattr(entry, 'published', ""),
            "description": clean(getattr(entry, 'summary', ""), title)
        })
    return articles

def poetize(title: str, body: str):
    """Gemini APIを使用してニュースを詩的に解釈する（4行の絶句形式）"""
    if not GEMINI_API_KEY:
        return "詩を生成するにはAPIキーが必要です。"

    model = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"

    prompt = f"""
あなたは唐代の詩人、李白（太白）です。
以下のニュースを読み、それに対するあなたの詩的な解釈を、
李白らしい自由闊達で幻想的な雰囲気の【4行の短い詩（日本語の絶句形式）】として詠んでください。

ニュースのタイトル：
{title}

ニュースの本文（概要）：
{body}

詩（必ず4行で）：
"""

    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()
        poem = result['candidates'][0]['content']['parts'][0]['text']
        return poem.strip()
    except Exception as e:
        # エラー詳細はログに出力し、フロントには安全なメッセージのみ返す
        print(f"Gemini Error: {e}")
        return "月夜の静寂が詩を遮りました。李白は今、酒を酌み交わしているようです。"

# --- 起動時処理 ---

@app.on_event("startup")
def startup_event():
    init_db()

# --- エンドポイント ---

@app.get("/news", response_model=List[NewsArticle])
def get_news(q: str = None):
    """取得 -> 保存 -> 出力の流れで実行する（詩は非同期で後から取得）"""
    new_articles = fetch(q=q)
    save_news(new_articles)
    
    # 最新の3件を取得
    display_news = load_news(limit=3)
    
    if not display_news:
        raise HTTPException(status_code=404, detail="ニュースがありません")

    return [{
        "title": n["title"],
        "description": n["description"],
        "url": n["url"],
        "poem": n.get("poem") # 既存のものがあれば返す
    } for n in display_news]

@app.get("/poem", response_model=PoemResponse)
def get_poem(title: str):
    """詩を生成し、DBに保存する"""
    # DBから本文を取得する
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT description FROM news WHERE title = ?", (title,))
    row = cursor.fetchone()
    conn.close()
    
    body = row[0] if row else ""
    poem = poetize(title, body)
    set_poem(title, poem)
    return {"poem": poem}

def count_kanji(text):
    if pd.isna(text):
        return 0
    return len(re.findall(r"[一-龠]", text))

@app.get("/analysis", response_model=AnalysisResponse)
def get_analysis():
    """DBの中身（特に本文）を分析し、統計情報を返す"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM news", conn)
    conn.close()

    if df.empty:
        raise HTTPException(status_code=404, detail="データがまだありません")

    # 1. 基本統計
    total = len(df)
    
    # 2. 詩の生成統計
    has_poem = int(df['poem'].notnull().sum())
    poem_rate = round((has_poem / total) * 100, 1) if total > 0 else 0

    # 3. 本文（description）文字数の計算
    df["body_len"] = df["description"].fillna("").apply(len)
    body_len_stats = df["body_len"].describe().to_dict()

    # 4. 本文の漢字の分析
    df["body_kanji_count"] = df["description"].apply(count_kanji)
    df["body_kanji_ratio"] = df["body_kanji_count"] / df["body_len"]
    
    avg_kanji_count = float(df["body_kanji_count"].mean())
    avg_kanji_ratio = float(df["body_kanji_ratio"].mean())

    # 5. 漢字が多い記事（本文） Top5
    top_kanji_df = df.sort_values(by="body_kanji_count", ascending=False).head(5)
    top_kanji_articles = top_kanji_df[["title", "body_kanji_count", "body_kanji_ratio"]].to_dict(orient="records")

    return {
        "total_articles": total,
        "poem_stats": {
            "generated_count": has_poem,
            "generation_rate_percent": poem_rate
        },
        "body_len_stats": body_len_stats,
        "kanji_stats": {
            "avg_count": avg_kanji_count,
            "avg_ratio": avg_kanji_ratio
        },
        "top_kanji_articles": top_kanji_articles,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.get("/history")
def get_history():
    """DBに保存されている全ニュースの履歴を返す"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM news ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/status")
def status():
    return {"status": "ok", "concept": "月下読酌", "version": "consolidated-v1"}

# --- Reactのビルド成果物（dist）を配信する設定 ---
frontend_dist_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.exists(frontend_dist_path):
    app.mount("/", StaticFiles(directory=frontend_dist_path, html=True), name="static")

    @app.exception_handler(404)
    async def custom_404_handler(request, __):
        path = request.url.path
        if not path.startswith("/news") and not path.startswith("/poem") and not path.startswith("/status") and not path.startswith("/analysis") and not path.startswith("/history"):
            return FileResponse(os.path.join(frontend_dist_path, "index.html"))
        raise HTTPException(status_code=404, detail="Not Found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
