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
    """初期テーブル作成とカラム追加"""
    with get_db_conn() as conn:
        with conn.cursor() as cursor:
            # 基本テーブル作成
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    body TEXT,
                    poem TEXT,
                    at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 分析用カラムの追加 (存在しない場合のみ)
            cursor.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS kanji_count INTEGER")
            cursor.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS kanji_ratio REAL")
            cursor.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS season TEXT")
            cursor.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS jieqi TEXT")
        conn.commit()

def save_news(items):
    """ニュースをDBに一括保存 (UPSERT)"""
    with get_db_conn() as conn:
        with conn.cursor() as cursor:
            data = [(i['url'], i['title'], i['body'], i['kanji_count'], i['kanji_ratio'], i['season'], i['jieqi']) for i in items]
            cursor.executemany("""
                INSERT INTO news (url, title, body, kanji_count, kanji_ratio, season, jieqi)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO UPDATE SET
                title = EXCLUDED.title,
                body = EXCLUDED.body,
                kanji_count = EXCLUDED.kanji_count,
                kanji_ratio = EXCLUDED.kanji_ratio,
                season = EXCLUDED.season,
                jieqi = EXCLUDED.jieqi
            """, data)
        conn.commit()

def load_news(limit: int = 3):
    """DBからニュースを取得"""
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = "SELECT * FROM news ORDER BY at DESC LIMIT %s"
            cursor.execute(query, (limit,))
            return [dict(row) for row in cursor.fetchall()]

# --- 分析用ヘルパー ---

def get_jieqi(dt):
    """日付から二十四節気を判定する"""
    md = dt.month * 100 + dt.day
    if md < 120: return '小寒'
    if md < 205: return '大寒'
    if md < 219: return '立春'
    if md < 306: return '雨水'
    if md < 321: return '啓蟄'
    if md < 405: return '春分'
    if md < 420: return '清明'
    if md < 506: return '穀雨'
    if md < 521: return '立夏'
    if md < 606: return '小満'
    if md < 621: return '芒種'
    if md < 707: return '夏至'
    if md < 723: return '小暑'
    if md < 808: return '大暑'
    if md < 823: return '立秋'
    if md < 908: return '処暑'
    if md < 923: return '白露'
    if md < 1008: return '秋分'
    if md < 1024: return '寒露'
    if md < 1107: return '霜降'
    if md < 1122: return '立冬'
    if md < 1207: return '小雪'
    if md < 1222: return '大雪'
    return '冬至'

def get_season(dt):
    """月から季節を判定する"""
    month = dt.month
    if month in [3, 4, 5]: return '春'
    if month in [6, 7, 8]: return '夏'
    if month in [9, 10, 11]: return '秋'
    return '冬'

def kanji_stats(text):
    """テキスト内の漢字の数と含有率を計算"""
    if not text: return {"count": 0, "ratio": 0.0}
    kanji = len(re.findall(r'[一-龠々]', text))
    return {"count": kanji, "ratio": round(kanji / len(text), 3)}

def pull():
    """NHKニュースRSSから最新記事を取得"""
    rss_url = "https://www3.nhk.or.jp/rss/news/cat0.xml"
    feed = feedparser.parse(rss_url)
    items = []
    now = datetime.now()
    for entry in feed.entries[:10]:
        t = entry.title
        summary = getattr(entry, 'summary', "")
        #  HTMLタグ除去と空白調整
        body = re.sub(r'<[^>]+>', '', summary)
        body = html.unescape(body).strip()
        
        stats = kanji_stats(body)
        items.append({
            "title": t,
            "url": entry.link,
            "body": body,
            "kanji_count": stats["count"],
            "kanji_ratio": stats["ratio"],
            "season": get_season(now),
            "jieqi": get_jieqi(now)
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
