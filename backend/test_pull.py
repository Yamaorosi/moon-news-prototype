import os
os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/db"
import main
import json

def pull_raw():
    import feedparser
    rss_url = "https://www3.nhk.or.jp/rss/news/cat0.xml"
    feed = feedparser.parse(rss_url)
    items = []
    for entry in feed.entries[:10]:
        items.append({
            "title": entry.title,
            "raw_summary": getattr(entry, 'summary', ""),
            "fixed_body": main.fix(getattr(entry, 'summary', ""), entry.title)
        })
    return items

if __name__ == "__main__":
    items = pull_raw()
    print(json.dumps(items, indent=2, ensure_ascii=False))
