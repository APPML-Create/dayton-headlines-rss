import hashlib, re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests, feedparser
from dateutil import parser as dtparse
from html import unescape

# ----- Config -----
FEED_TITLE = "Dayton Headlines Feed"
# Set this to your GitHub Pages feed URL:
FEED_LINK = "https://YOUR-USER.github.io/dayton-headlines-rss/feed.xml"
FEED_DESCRIPTION = "Daily top 6 headlines from Dayton, OH media"
OUTPUT = "feed.xml"
MAX_ITEMS = 6
TZ = ZoneInfo("America/New_York")

# Use stable sources via Google News RSS
SOURCES = {
    "WHIO": "https://news.google.com/rss/search?q=site:whio.com&hl=en-US&gl=US&ceid=US:en",
    "WDTN": "https://news.google.com/rss/search?q=site:wdtn.com&hl=en-US&gl=US&ceid=US:en",
    "ABC22/FOX45 (Dayton24/7Now)": "https://news.google.com/rss/search?q=(site:dayton247now.com%20OR%20site:abc22now.com%20OR%20site:fox45now.com)&hl=en-US&gl=US&ceid=US:en",
    "Dayton Daily News": "https://news.google.com/rss/search?q=site:daytondailynews.com&hl=en-US&gl=US&ceid=US:en",
}

UA = {"User-Agent": "DaytonFeedBot/1.0 (+github actions)"}

def fetch_entries():
    all_items = []
    for source, url in SOURCES.items():
        r = requests.get(url, headers=UA, timeout=25)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        for e in feed.entries[:10]:
            title = clean_text(getattr(e, "title", ""))
            link = (getattr(e, "link", "") or "").strip()
            summary = clean_html(getattr(e, "summary", "") or getattr(e, "description", ""))
            pub = parse_date(getattr(e, "published", "") or getattr(e, "updated", ""))
            if not title or not link:
                continue
            all_items.append({
                "title": title,
                "link": link,
                "summary": summarize(summary),
                "source": source,
                "pub": pub or now_et(),
            })

    # sort recent → oldest, dedupe by normalized title
    all_items.sort(key=lambda x: x["pub"], reverse=True)
    seen = set()
    deduped = []
    for it in all_items:
        key = re.sub(r"\s+", " ", it["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
        if len(deduped) >= MAX_ITEMS:
            break
    return deduped

def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(s)).strip()

def clean_html(s: str) -> str:
    s = unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def summarize(text: str, max_chars: int = 320) -> str:
    if not text:
        return ""
    # take first two sentences; cap length
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = " ".join(parts[:2]).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rsplit(" ", 1)[0] + "…"
    return out

def parse_date(s: str):
    if not s:
        return None
    try:
        dt = dtparse.parse(s)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ)
    except Exception:
        return None

def now_et():
    return datetime.now(TZ)

def rfc2822(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")

def guid_for(link: str, pub: datetime) -> str:
    h = hashlib.sha256((link + pub.isoformat()).encode("utf-8")).hexdigest()
    return h[:32]

def xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&apos;")
    )

def build_rss(items):
    last_build = items[0]["pub"] if items else now_et()
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{xml_escape(FEED_TITLE)}</title>",
        f"<link>{xml_escape(FEED_LINK)}</link>",
        f"<description>{xml_escape(FEED_DESCRIPTION)}</description>",
        f"<lastBuildDate>{rfc2822(last_build)}</lastBuildDate>",
        f'<atom:link href="{xml_escape(FEED_LINK)}" rel="self" type="application/rss+xml" />',
    ]
    for it in items:
        desc = f'{it["summary"]}  Source: {it["source"]}'.strip()
        parts += [
            "<item>",
            f"<title>{xml_escape(it['title'])}</title>",
            f"<link>{xml_escape(it['link'])}</link>",
            f"<description><![CDATA[{desc}]]></description>",
            f'<guid isPermaLink="false">{guid_for(it["link"], it["pub"])}</guid>',
            f"<pubDate>{rfc2822(it['pub'])}</pubDate>",
            "</item>",
        ]
    parts += ["</channel>", "</rss>"]
    return "\n".join(parts)

if __name__ == "__main__":
    items = fetch_entries()
    rss = build_rss(items)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(rss)
