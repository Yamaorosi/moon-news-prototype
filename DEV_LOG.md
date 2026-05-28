# 🌙 月下読酌 制作ログ (DEV_LOG)

## 2026-05-28: デプロイ成功と構成の確立

### 1. フロントエンドのデプロイ (GitHub Pages)
- **構成**: Vite + React
- **変更点**: 
    - `vite.config.ts` に `base: '/moon-news-prototype/'` を追加。
    - API接続先を Railway の本番URL (`https://moon-news-prototype-production.up.railway.app`) に向けるよう `App.tsx` を修正。
- **デプロイ**: GitHub Actions (`.github/workflows/deploy.yml`) を構築。`vibe-coding` ブランチへの push で自動デプロイされる仕組み。

### 2. バックエンドのデプロイ (Railway)
- **構成**: FastAPI + Uvicorn + SQLite
- **変更点**:
    - Railway の **Root Directory** を `backend` に設定。
    - **Start Command** を `uvicorn main:app --host 0.0.0.0 --port 8000` に設定。
    - **Target Port** を 8000 に設定。
- **トラブルシューティング**:
    - Gemini API のモデル名が `gemini-2.5-flash` (存在しない) になっていたため、`gemini-1.5-flash` に修正して解決。
    - Railway の Variables に `GEMINI_API_KEY1` などの環境変数をセット。

### 3. 今後の課題・メモ
- **DBの永続化**: 現在は SQLite のため、Railway へのデプロイごとにデータがリセットされる。
- **共有DBへの移行**: ポエムを溜めておく（事前生成する）ために、Railway の PostgreSQL への移行を検討中。
- **API負荷軽減**: 事前にポエムを生成してDBに保存しておき、リクエスト時はDBから返す仕組みを強化したい。
