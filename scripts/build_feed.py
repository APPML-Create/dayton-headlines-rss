import hashlib
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import re
import requests
import feedparser
from dateutil import parser as dtparser
from html import unescape

# --- Config ---
FEED_TITLE = "Dayton Headlines Feed"
FEED_LINK = "https://yourusername.github.io/dayton-headlines-rss/feed.xml"
FEED_DESCRIPTION = "Daily top 6 headlines from Dayton, OH media"
OUTPUT = "feed.xml"
MAX_ITEMS = 6
TZ = ZoneInfo("America/New_York")

# Google News RSS per source (reliable endpoints)
SOURCES = {
    "WHIO": "https://news.google.com/rss/search?q=site:whio.com&hl=en-US&gl=US&ceid=US:en",
    "WDTN": "https://news.google.com/rss/search?q=site:wdtn.com&hl=en-US&gl=US&ceid=US:en",
    "ABC22/FOX45 (Dayton24/7Now)": "https://news.google.com/rss/search?q=site:dayton247now.com%20OR%20site:abc22now.com%20OR%20site:fox45now.com&hl=en-US&gl=US&ceid=US:en",
    "Dayton Daily News": "https://news.google.com/rss/search?q=site:daytondailynews.com&hl=en-US&gl=US&ceid=US:en",
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "DaytonFeedBot/1.0 (+github actions)"})


def fetch_entries():
    items = []
    for source, url in SOURCES.items():
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for e in feed.entries[:8]:  # take top few per source
            title = clean(e.title)
            link = getattr(e, "link", "").strip()
            summary = clean(getattr(e, "summary", "") or getattr(e, "description", ""))
            pub = parse_date(getattr(e, "published", "") or getattr(e, "updated", "") or "")
            if not link or not title:
                continue
            items.append({
                "title": title,
                "link": link,
                "summary": summarize(summary) or title,
                "source": source,
                "pub": pub or now_et(),
            })
    # De-dupe by normalized title
    seen = set()
    deduped = []
    for it in sorted(items, key=lambda x: x["pub"], reverse=True):
        key = re.sub(r"\s+", " ", it["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    return deduped[:MAX_ITEMS]


def clean(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def summarize(text: str, max_chars: int = 320) -> str:
    if not text:
        return ""
    # take first 2 sentences or cap chars
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = " ".join(sentences[:2]).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rsplit(" ", 1)[0] + "…"
    return out


def parse_date(s: str):
    try:
        dt = dtparser.parse(s)
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


def build_rss(items):
    last_build = items[0]["pub"] if items else now_et()
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{xml(FEED_TITLE)}</title>",
        f"<link>{xml(FEED_LINK)}</link>",
        f"<description>{xml(FEED_DESCRIPTION)}</description>",
        f"<lastBuildDate>{rfc2822(last_build)}</lastBuildDate>",
        '<atom:link href="{0}" rel="self" type="application/rss+xml" />'.format(xml(FEED_LINK)),
    ]
    for it in items:
        title = it["title"]
        link = it["link"]
        desc = f'{xml(it["summary"])}  Source: {xml(it["source"])}'
        pub = it["pub"]
        guid = guid_for(link, pub)
        parts += [
            "<item>",
            f"<title>{xml(title)}</title>",
            f"<link>{xml(link)}</link>",
            f"<description><![CDATA[{desc}]]></description>",
            f'<guid isPermaLink="false">{guid}</guid>',
            f"<pubDate>{rfc2822(pub)}</pubDate>",
            "</item>",
        ]
    parts += ["</channel>", "</rss>"]
    return "\n".join(parts)


def xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


if __name__ == "__main__":
    entries = fetch_entries()
    rss = build_rss(entries)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(rss)

