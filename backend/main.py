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

# --- サービスロジック（ニュース取得） ---
# ... (変更なし) ...

# --- エンドポイント ---

@app.get("/news")
def get_news(category: str = None, q: str = None, country: str = "us", sources: str = None):
    """
    ニュースだけを爆速で取得して返す。
    """
    articles = fetch_news(category=category, q=q, country=country, sources=sources)
    if not articles:
        raise HTTPException(status_code=404, detail="ニュースがありません")

    results = []
    for article in articles:
        results.append({
            "title": article["title"],
            "source": article["source"]["name"],
            "url": article["url"],
            "publishedAt": article["publishedAt"],
            "description": article.get("description", ""),
            "imageUrl": article.get("urlToImage", "")
        })
    return results

@app.get("/poem")
def get_poem(title: str):
    """
    指定されたタイトルに対して、じっくり詩を書いて返す。
    """
    poem = interpret_with_gemini(title)
    return {"poem": poem}

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
