# 月下読酌 (Moon News Local)

ニュースをただの「情報」として消費するのではなく、詩的な「解釈」を通して味わうためのWebアプリケーション。

## 🌗 コンセプト
> 「ニュースを“解釈させる装置”」

現代の喧騒（ニュース）を、月明かりの下で詩（AI）として詠み直し、酒の肴にする。和漢の美学を取り入れた静謐なインターフェースで、情報の受け取り方を更新します。

## 🛠 技術スタック
- **Frontend**: React (TypeScript) + Vite
  - 2段階ローディング（ニュース先行、詩は遅延生成）
  - 「和・漢」を基調としたセリフ体・墨色デザイン
- **Backend**: FastAPI (Python)
  - NewsAPI: 最新ニュースの取得
  - Gemini API (1.5-flash / 2.5-flash): 詩的解釈の生成
- **Design**: Vanilla CSS (Custom Properties, Grayscale Filters)

## 📂 構成
```
backend/
├── main.py          # FastAPIエンドポイント（/news, /poem）
├── .env             # APIキー管理
└── requirements.txt
frontend/
├── src/
│   ├── App.tsx      # メインロジック（非同期詩生成コンポーネント）
│   ├── App.css      # 墨色・和風デザイン
│   └── main.tsx
└── index.html
```

## 🚀 開発・起動方法

### 準備
1. `.env` ファイルを `backend/` に作成し、以下のキーを設定：
   - `NEWS_API_KEY`
   - `GEMINI_API_KEY`

### Backend
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## 🌐 デプロイ (Render.com)
- **Backend**: Web Serviceとしてデプロイ。
  - Build Command: `pip install -r requirements.txt`
  - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
  - Env Vars: `NEWS_API_KEY`, `GEMINI_API_KEY` を設定。
- **Frontend**: Static Siteとしてデプロイ。
  - Build Command: `npm run build`
  - Publish directory: `dist`
  - Env Var: `VITE_API_URL`（バックエンドのURL）をApp.tsxで参照するように調整が必要。

---
*Created with the help of Gemini CLI*
