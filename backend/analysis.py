# analysis.py
import re
import os
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def count_kanji(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"[一-龠]", text))

def run():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT title, body, poem FROM news")
            rows = cursor.fetchall()

    if not rows:
        return None

    total = len(rows)
    done = sum(1 for r in rows if r["poem"] and "API制限" not in r["poem"])
    rate = round((done / total) * 100, 1) if total > 0 else 0

    lengths = [len(r["body"] or "") for r in rows]
    avg_len = sum(lengths) / total

    kanji_counts = [count_kanji(r["body"]) for r in rows]
    ratios = [k / l if l > 0 else 0 for k, l in zip(kanji_counts, lengths)]

    avg_kanji = sum(kanji_counts) / total
    avg_ratio = sum(ratios) / total

    top = sorted(
        [{"title": r["title"], "kanji": count_kanji(r["body"]), "ratio": round(k / l if l > 0 else 0, 3)}
         for r, k, l in zip(rows, kanji_counts, lengths)],
        key=lambda x: x["kanji"],
        reverse=True
    )[:5]

    return {
        "total": total,
        "poem_stats": {"done": done, "rate": rate},
        "len_stats": {"avg": avg_len, "min": min(lengths), "max": max(lengths)},
        "kanji_stats": {"avg": avg_kanji, "ratio": avg_ratio},
        "top": top,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }