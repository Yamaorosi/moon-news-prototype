import sqlite3
import pandas as pd
import re
from datetime import datetime

def count(text):
    if pd.isna(text): return 0
    return len(re.findall(r"[一-龠]", text))

def run(db):
    conn = sqlite3.connect(db)
    df = pd.read_sql_query("SELECT * FROM news", conn)
    conn.close()

    if df.empty: return None

    total = len(df)
    done = int(df['poem'].notnull().sum())
    rate = round((done / total) * 100, 1) if total > 0 else 0

    df["len"] = df["body"].fillna("").apply(len)
    len_stats = df["len"].describe().to_dict()

    df["kanji"] = df["body"].apply(count)
    df["ratio"] = df["kanji"] / df["len"]
    
    avg_kanji = float(df["kanji"].mean())
    avg_ratio = float(df["ratio"].mean())

    top_df = df.sort_values(by="kanji", ascending=False).head(5)
    top = top_df[["title", "kanji", "ratio"]].to_dict(orient="records")

    return {
        "total": total,
        "poem_stats": {
            "done": done,
            "rate": rate
        },
        "len_stats": len_stats,
        "kanji_stats": {
            "avg": avg_kanji,
            "ratio": avg_ratio
        },
        "top": top,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
