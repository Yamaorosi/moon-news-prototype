#!/usr/bin/env bash
# exit on error
set -o errexit

# Frontendのビルド
cd frontend
npm install
npm run build
cd ..

# Backendの依存関係インストール
cd backend
pip install -r requirements.txt
cd ..
