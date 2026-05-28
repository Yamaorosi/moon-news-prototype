"""
1日1回実行するバッチ。
Railway: Settings → Cron Jobs → `python batch.py` を `0 0 * * *` (JST調整で15 or 21 UTC)
"""
import feedparser
import requests
import psycopg2
import os
import re
import html
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
KEYS = [k for k in [
    os.getenv("GEMINI_API_KEY1"),
    os.getenv("GEMINI_API_KEY2"),
    os.getenv("GEMINI_API_KEY3"),
    os.getenv("GEMINI_API_KEY4"),
    os.getenv("GEMINI_API_KEY"),
] if k]

def get_db_conn():
    return psycopg2.connect(DATABASE_URL)

def kanji_stats(text):
    if not text: return {"count": 0, "ratio": 0.0}
    kanji = len(re.findall(r'[一-龠々]', text))
    return {"count": kanji, "ratio": round(kanji / len(text), 3)}

def get_season(dt):
    m = dt.month
    if m in [3,4,5]: return '春'
    if m in [6,7,8]: return '夏'
    if m in [9,10,11]: return '秋'
    return '冬'

def get_jieqi(dt):
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

def pick_one():
    """RSSから先頭1件を取得して整形"""
    feed = feedparser.parse("https://www3.nhk.or.jp/rss/news/cat0.xml")
    entry = feed.entries[0]
    now = datetime.now()
    body = html.unescape(re.sub(r'<[^>]+>', '', getattr(entry, 'summary', ''))).strip()
    stats = kanji_stats(body)
    return {
        "url": entry.link,
        "title": entry.title,
        "body": body,
        "kanji_count": stats["count"],
        "kanji_ratio": stats["ratio"],
        "season": get_season(now),
        "jieqi": get_jieqi(now),
    }

def sing(title, body):
    if not KEYS: return None
    for key in KEYS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
        prompt = f"あなたは李白。4行の絶句を詠め。\n題: {title}\n録: {body}\n詩:"
        try:
            res = requests.post(url,
                headers={'Content-Type': 'application/json'},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=10)
            res.raise_for_status()
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception as e:
            print(f"Gemini error (key ...{key[-4:]}): {e}")
            continue
    return None

def run():
    item = pick_one()
    item["poem"] = sing(item["title"], item["body"])

    with get_db_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO news (url, title, body, poem, kanji_count, kanji_ratio, season, jieqi)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO UPDATE SET
                    poem = EXCLUDED.poem
            """, (
                item["url"], item["title"], item["body"], item["poem"],
                item["kanji_count"], item["kanji_ratio"], item["season"], item["jieqi"]
            ))
        conn.commit()
    print(f"[{datetime.now()}] 保存完了: {item['title']}")

if __name__ == "__main__":
    run()