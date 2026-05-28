# 🌙 月下読酌 制作ログ (DEV_LOG)

## 2026-05-28: デプロイ成功と構成の確立（激闘の記録）

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

### 3. 【追加】PostgreSQLへの移行とデータ完全同期
- **DB永続化の実現**: 
    - Railway上で PostgreSQL サービスを起動。
    - バックエンドサービスに `DATABASE_URL` を環境変数として紐付け。
    - `psycopg2-binary` を導入し、`main.py` を PostgreSQL/SQLite 両対応のハイブリッド仕様にアップグレード。
- **ローカル・本番のデータ同期**:
    - ローカルの `.env` に Railway の `DATABASE_PUBLIC_URL` を設定。
    - これにより、手元でニュースを取得・ポエム生成した結果が、そのまま本番サイトにも反映される最強の構成が完成。
- **CORSエラーの修正**:
    - ブラウザで通信がブロックされないよう、FastAPIの `CORSMiddleware` 設定を調整（`allow_credentials=False`）。

### 4. クリーンアップ
- `test_db.py` などのデバッグ用ファイルを削除。
- `main.py` のデバッグログを削除し、本番仕様に。

### 5. 今後の課題・メモ
- **Pandasによるデータ分析**: 溜まってきたポエムやニュースのデータを分析し、傾向を可視化したい。
- **APIの最適化**: 現在Gemini 1.5 Flashを使用中。コストや速度を見て適宜調整。
- **UIのブラッシュアップ**: 制作が安定したので、次はデザイン面（李白の世界観）をより深めていきたい。
