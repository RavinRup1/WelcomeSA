#!/usr/bin/env python3
"""WelcomeSA robot 3 - News: South African positive/progress news, daily.
Fetches RSS feeds, jury-curates (writer->critic->judge, ties DROP).
Serves headline + our two-line summary + source link only (fair use).
Writes data/news.json + drop audit."""

import json, os, re, sys, time
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo

import requests

SAST = ZoneInfo("Africa/Johannesburg")
NOW = datetime.now(SAST)
H = {"User-Agent": "WelcomeSA-robot/1.0 (ravin.rup1@gmail.com)"}
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUT = os.path.join(DATA, "news.json")
SRC = os.path.join(DATA, "news_sources.json")

DEFAULT_FEEDS = [
    {"name": "Good Things Guy", "url": "https://www.goodthingsguy.com/feed/"},
    {"name": "EWN", "url": "https://ewn.co.za/rss"},
    {"name": "Daily Maverick", "url": "https://www.dailymaverick.co.za/feed/"},
    {"name": "IOL", "url": "https://www.iol.co.za/rss"},
    {"name": "SABC News", "url": "https://www.sabcnews.com/sabcnews/feed/"},
]


def strip(s):
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=re.S)
    s = re.sub(r"<[^>]+>", " ", unescape(s))
    return re.sub(r"\s+", " ", s).strip()


def parse_feed(xml):
    items = []
    blocks = re.findall(r"<item>(.*?)</item>", xml, re.S | re.I) or \
             re.findall(r"<entry>(.*?)</entry>", xml, re.S | re.I)
    for b in blocks:
        def g(tag):
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", b, re.S | re.I)
            return strip(m.group(1)) if m else ""
        link = g("link")
        if not link:
            m = re.search(r'<link[^>]*href="([^"]+)"', b)
            link = m.group(1) if m else ""
        items.append({"title": g("title"), "link": link,
                      "published": g("pubDate") or g("published") or g("updated"),
                      "raw": strip(b)[:1200]})
    return items


def fresh_out(path, days):
    if os.environ.get("FORCE") == "1":
        return False
    if os.path.exists(path):
        try:
            d = json.load(open(path))
            ts = d.get("generated_at")
            if ts:
                return (NOW - datetime.fromisoformat(ts)).total_seconds() < days * 86400
        except Exception:
            pass
    return False


_WORKING_MODEL = [None]   # once a model answers, stick to it for the whole run


def _gemini_json(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    # discover live models, prefer flash variants (pattern proven across the
    # other robots - hardcoded model names rot when the free tier renames).
    # Free tier is per-minute rate limited: remember the first model that
    # works and stop hammering the rest (learned 10 Oct - the model loop
    # fired ~600 requests in 2 min and everything 429'd -> 0 stories).
    models = []
    if _WORKING_MODEL[0]:
        models = [_WORKING_MODEL[0]]
    else:
        models = ["gemini-2.5-flash", "gemini-flash-latest"]
        try:
            lr = requests.get("https://generativelanguage.googleapis.com/v1beta/models?key=" + key,
                              timeout=40)
            if lr.status_code == 200:
                ids = [m["name"].split("/")[-1] for m in lr.json().get("models", [])]
                flash = [i for i in ids if "flash" in i.lower() and "vision" not in i.lower()
                         and "tts" not in i.lower()]
                models = list(dict.fromkeys(models[:1] + (flash or ids)[:2]))
        except Exception:
            pass
    for model in models:
        try:
            r = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={key}",
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json",
                                           "temperature": 0.3}},
                timeout=70)
            if r.status_code == 200:
                print("gemini ok via", model)
                _WORKING_MODEL[0] = model
                return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            print("gemini http", r.status_code, "model", model)
        except Exception as e:
            print("gemini failed:", type(e).__name__)
    return None


def ai_writer(it):
    d = _gemini_json(
        "You are a news editor for Welcome SA, a proudly South African guide that "
        "covers GOOD NEWS and national PROGRESS. Using ONLY the material below, "
        "return JSON:\n"
        '- "summary": exactly 2 plain, warm sentences summarising the story.\n'
        '- "angle": one short sentence on why it is good news or progress.\n'
        "No exclamation marks.\n\n"
        f"HEADLINE: {it.get('title')}\nMATERIAL:\n{it.get('raw', '')[:1500]}")
    if not d:
        return None
    return {"summary": str(d.get("summary", "")).strip(),
            "angle": str(d.get("angle", "")).strip()}


def ai_critic(it, draft):
    return _gemini_json(
        "You are a strict news standards editor. Check:\n"
        "1. Is this genuinely a POSITIVE story or national PROGRESS (not crime, "
        "tragedy, political drama, or bad news framed positively)?\n"
        "2. Is it about South Africa?\n"
        "3. Does the SUMMARY stick to the material without invention?\n"
        'Return JSON: {"positive": true/false, "about_sa": true/false, '
        '"accurate": true/false, "verdict": "PASS" or "FAIL", '
        '"issues": "one short sentence"}\n\n'
        f"HEADLINE: {it.get('title')}\nMATERIAL:\n{it.get('raw', '')[:1200]}"
        f"\n\nSUMMARY:\n{json.dumps(draft)[:800]}")


def ai_judge(it, draft, critic):
    critic = critic or {}
    return _gemini_json(
        "Final editor. SERVE or DROP. DROP unless positive AND about_sa AND "
        'accurate are all true. Return JSON: {"decision": "SERVE" or "DROP", '
        '"reason": "short"}.\n\n'
        f"HEADLINE: {it.get('title')}\nCRITIC: {json.dumps(critic)[:700]}")


def main():
    os.makedirs(DATA, exist_ok=True)
    if fresh_out(OUT, 1):
        print("news: fresh (<1 day), skipping")
        return
    feeds = DEFAULT_FEEDS
    if os.path.exists(SRC):
        try:
            feeds = json.load(open(SRC))
        except Exception:
            pass

    cand, report = [], []
    for f in feeds:
        entry = {"name": f["name"], "url": f["url"], "ok": False, "stories": 0}
        try:
            r = requests.get(f["url"], headers=H, timeout=40)
            entry["http"] = r.status_code
            if r.status_code == 200 and ("<item" in r.text or "<entry" in r.text):
                its = parse_feed(r.text)
                entry["ok"], entry["stories"] = True, len(its)
                for it in its[:10]:
                    it["source"] = f["name"]
                    cand.append(it)
        except Exception as e:
            entry["note"] = type(e).__name__
        report.append(entry)
        time.sleep(4)  # stay kind to the free tier (429 flood lesson, 10 Oct)

    served, dropped = [], []
    seen = set()
    for it in cand:
        if len(served) >= 10:
            break
        if not it.get("title") or not it.get("link"):
            continue
        k = it["link"].split("?")[0]
        if k in seen:
            continue
        seen.add(k)
        draft = ai_writer(it)
        if not draft:
            continue
        critic = ai_critic(it, draft) or {}
        judge = ai_judge(it, draft, critic) or {}
        time.sleep(2)
        if str(judge.get("decision", "")).upper() == "SERVE":
            served.append({"title": it["title"], "summary": draft["summary"],
                           "angle": draft["angle"], "source": it["source"],
                           "url": it["link"], "published": it.get("published", "")})
        else:
            dropped.append({"title": it["title"][:60], "source": it["source"],
                            "reason": str(judge.get("reason") or
                                          (critic or {}).get("issues") or "rejected")[:120]})
    print(f"news jury: {len(served)} served, {len(dropped)} dropped")

    doc = {"generated_at": NOW.isoformat(),
           "stories": served,
           "dropped": dropped[-20:],
           "feeds": report,
           "ok": any(f["ok"] for f in report)}
    with open(OUT, "w") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
