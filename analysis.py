import sqlite3
import pandas as pd
import json
import re
import os
from janome.tokenizer import Tokenizer
from datetime import datetime

# --- 設定 ---
DB_PATH = os.path.join("backend", "news_cache.db")
LIBAI_JSON_PATH = os.path.join("..", "moon-news-api", "data", "libai.json")

def get_libai_kanji():
    """libai.jsonから李白の詩に使われている漢字を抽出する"""
    if not os.path.exists(LIBAI_JSON_PATH):
        return set()
    with open(LIBAI_JSON_PATH, 'r', encoding='utf-8') as f:
        raw_text = f.read()
    return set(re.findall(r'[一-龠々]', raw_text))

# 二十四節気リスト
SOLAR_TERMS = [
    '立春', '雨水', '啓蟄', '春分', '清明', '穀雨',
    '立夏', '小満', '芒種', '夏至', '小暑', '大暑',
    '立秋', '処暑', '白露', '秋分', '寒露', '霜降',
    '立冬', '小雪', '大雪', '冬至', '小寒', '大寒'
]

# --- 分析用エンジン ---
t = Tokenizer()
libai_kanji_set = get_libai_kanji()

def analyze_row(text):
    """1記事のタイトルを詳細分析（品詞、漢字、節気）"""
    pos_counts = {"名詞": 0, "動詞": 0, "形容詞": 0}
    for token in t.tokenize(text):
        pos = token.part_of_speech.split(',')[0]
        if pos in pos_counts:
            pos_counts[pos] += 1
    
    found_kanji = [c for c in text if c in libai_kanji_set]
    found_terms = [term for term in SOLAR_TERMS if term in text]
    
    return pd.Series([
        pos_counts["名詞"], 
        pos_counts["動詞"], 
        pos_counts["形容詞"], 
        len(found_kanji),
        len(found_terms)
    ])

def run_all_analysis():
    if not os.path.exists(DB_PATH):
        print(f"Error: DBが見つかりません ({DB_PATH})")
        return

    # 1. 【読み込み】
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM news", conn)
    conn.close()

    if df.empty:
        print("分析するデータがまだありません。")
        return

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🚀 pandas 基礎分析：データの形を知る")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📄 データの形 (行, 列): {df.shape}")
    print(f"📋 列の名前一覧: {df.columns.tolist()}")
    print("\n--- [head] 最初から3件を表示 ---")
    print(df[['title', 'source']].head(3))

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🛠 pandas 加工分析：新しい列を作る")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    # 文字数の計算
    df['title_len'] = df['title'].apply(len)
    # 李白流の高度な分析を一気に実行
    cols = ['名詞数', '動詞数', '形容詞数', '李白漢字数', '節気数']
    df[cols] = df['title'].apply(analyze_row)

    print("新しい列 [title_len, 名詞数, ..., 節気数] を追加しました。")
    print(df[['title', 'title_len', '李白漢字数']].head(3))

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📊 pandas 集計分析：グループ化とランキング")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    print("\n--- [value_counts] 出典ごとの記事数 ---")
    print(df['source'].value_counts())

    print("\n--- [groupby] 出典ごとの平均素材数 ---")
    avg_stats = df.groupby('source')[['title_len', '名詞数', '動詞数', '形容詞数', '李白漢字数']].mean()
    print(avg_stats)

    print("\n--- [sort_values] 李白漢字が多い記事 Top 3 ---")
    print(df.sort_values(by='李白漢字数', ascending=False)[['title', '李白漢字数']].head(3))

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🏮 DB全体の情緒総計")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    totals = df[['名詞数', '動詞数', '形容詞数', '李白漢字数', '節気数']].sum()
    for label, val in totals.items():
        print(f"  - 総{label}: {int(val)}")

if __name__ == "__main__":
    run_all_analysis()
