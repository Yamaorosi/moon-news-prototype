import pandas as pd
import re
import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# --- 設定 ---
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set.")
    return psycopg2.connect(DATABASE_URL)

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

def run():
    """APIエンドポイント用の結果を返す関数"""
    try:
        with get_db_conn() as conn:
            df = pd.read_sql_query("SELECT * FROM news", conn)
    except Exception as e:
        print(f"DB Connection Error: {e}")
        return None

    if df.empty:
        return None

    # 1. 【基本情報の計算】
    df['at'] = pd.to_datetime(df['at'])
    df['title_len'] = df['title'].str.len()
    df['body_len'] = df['body'].str.len().replace(0, 1) # 0除算防止
    
    # 統計情報の更新
    stats_list = df['body'].apply(kanji_stats).tolist()
    df['kanji_count'] = [s['count'] for s in stats_list]
    df['kanji_ratio'] = [s['ratio'] for s in stats_list]

    df['jieqi'] = df['at'].apply(get_jieqi)
    df['season'] = df['at'].apply(get_season)
    
    # 2. 【既存APIへの互換データ作成】
    total = len(df)
    # ポエム生成済み（API制限エラーを含まない）の数
    done = len(df[df['poem'].notna() & ~df['poem'].str.contains("API制限")])
    rate = round((done / total) * 100, 1) if total > 0 else 0

    top_kanji = df.sort_values(by='kanji_ratio', ascending=False).head(5)
    top_list = [{"title": row['title'], "kanji": row['kanji_count'], "ratio": row['kanji_ratio']} for _, row in top_kanji.iterrows()]

    return {
        "total": total,
        "poem_stats": {"done": done, "rate": rate},
        "len_stats": {
            "avg": df['body_len'].mean(), 
            "min": df['body_len'].min(), 
            "max": df['body_len'].max()
        },
        "kanji_stats": {
            "avg": df['kanji_count'].mean(), 
            "ratio": df['kanji_ratio'].mean()
        },
        # 新しく追加した時間情報もAPIに含める
        "time_stats": {
            "jieqi_counts": df['jieqi'].value_counts().to_dict(),
            "season_counts": df['season'].value_counts().to_dict()
        },
        "top": top_list,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

def run_cli():
    """コマンドライン実行時のリッチな出力用"""
    print("Connecting to PostgreSQL...")
    try:
        with get_db_conn() as conn:
            df = pd.read_sql_query("SELECT * FROM news", conn)
    except Exception as e:
        print(f"DB Connection Error: {e}")
        return

    if df.empty:
        print("データがありません。")
        return

    df['at'] = pd.to_datetime(df['at'])
    df['title_len'] = df['title'].str.len()
    df['body_len'] = df['body'].str.len().replace(0, 1)
    
    stats_list = df['body'].apply(kanji_stats).tolist()
    df['kanji_count'] = [s['count'] for s in stats_list]
    df['kanji_ratio'] = [s['ratio'] for s in stats_list]
    
    df['jieqi'] = df['at'].apply(get_jieqi)
    df['season'] = df['at'].apply(get_season)

    print("\n" + "="*50)
    print("📊 月下読酌：データ分析レポート (Pandas Engine)")
    print("="*50)
    
    print(f"\n✅ 総記事数: {len(df)} 件")
    
    print("\n--- 📝 記事構成の統計 (平均) ---")
    print(f"・タイトル平均文字数: {df['title_len'].mean():.1f}")
    print(f"・本文平均文字数    : {df['body_len'].mean():.1f}")
    print(f"・平均漢字含有率    : {df['kanji_ratio'].mean()*100:.1f} %")

    print("\n--- ☀️ 二十四節気ごとの記事数 ---")
    print(df['jieqi'].value_counts())

    print("\n--- 🌸 季節ごとの平均漢字含有率 ---")
    print(df.groupby('season')['kanji_ratio'].mean().sort_values(ascending=False))

    print("\n--- 🏮 漢字含有率が高い記事 Top 5 ---")
    top_kanji = df.sort_values(by='kanji_ratio', ascending=False).head(5)
    for _, row in top_kanji.iterrows():
        print(f"[{row['kanji_ratio']:.3f}] {row['title']}")

    print("\n" + "="*50)

if __name__ == "__main__":
    run_cli()
