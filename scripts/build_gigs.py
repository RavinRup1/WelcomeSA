#!/usr/bin/env python3
"""WelcomeSA robot 2 - KZN Gig Guide: music + cultural events.
Reads event pages and extracts schema.org Event JSON-LD (embedded structured
data many venues publish). Sources are configurable in data/gig_sources.json
so we can tune without code changes. Writes data/gigs.json."""

import json, os, re, sys, time
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo

import requests

SAST = ZoneInfo("Africa/Johannesburg")
NOW = datetime.now(SAST)
H = {"User-Agent": "WelcomeSA-robot/1.0 (ravin.rup1@gmail.com)"}

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUT = os.path.join(DATA, "gigs.json")
SRC = os.path.join(DATA, "gig_sources.json")

# initial source candidates - tune freely in the repo
DEFAULT_SOURCES = [
    {"name": "Durban ICC", "url": "https://www.durbanicc.co.za/events/"},
    {"name": "Computicket Durban", "url": "https://www.computicket.com/events/durban"},
    {"name": "Suncoast Events", "url": "https://www.suncoastcasino.co.za/events"},
    {"name": "uShaka Events", "url": "https://www.ushakamarineworld.co.za/events"},
]


def extract_jsonld_events(html):
    """All schema.org Events in JSON-LD blocks - handles ItemList and @graph."""
    events = []

    def walk(node):
        if isinstance(node, dict):
            t = node.get("@type")
            if t == "Event":
                events.append(node)
            if t == "ItemList":
                for el in node.get("itemListElement", []):
                    walk(el.get("item", el))
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    for block in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                            html, re.S | re.I):
        try:
            walk(json.loads(unescape(block.strip())))
        except Exception:
            continue
    return events


def sitemap_urls(url, pattern, cap=25):
    """Fetch a sitemap (or sitemap index). Returns (matches, raw sample)."""
    try:
        r = requests.get(url, headers=H, timeout=40)
        if r.status_code != 200:
            return [], []
        locs = re.findall(r"<loc>(.*?)</loc>", r.text)
        sample = locs[:12]
        urls = []
        for loc in locs:
            if "sitemap" in loc.lower() and not re.search(pattern, loc, re.I):
                try:
                    rr = requests.get(loc, headers=H, timeout=30)
                    urls += [u for u in re.findall(r"<loc>(.*?)</loc>", rr.text)
                             if re.search(pattern, u, re.I)]
                except Exception:
                    pass
                time.sleep(1)
            elif re.search(pattern, loc, re.I):
                urls.append(loc)
            if len(urls) >= cap:
                break
        return urls[:cap], sample
    except Exception:
        return [], []


def norm(ev, source):
    loc = ev.get("location") or {}
    if isinstance(loc, dict):
        loc = loc.get("name") or ""
    img = ev.get("image") or ""
    if isinstance(img, list):
        img = img[0] if img else ""
    if isinstance(img, dict):
        img = img.get("url", "")
    return {
        "name": (ev.get("name") or "").strip(),
        "start": ev.get("startDate") or "",
        "end": ev.get("endDate") or "",
        "venue": str(loc).strip(),
        "city": "Durban",
        "source": source,
        "url": ev.get("url") or "",
        "image": img,
    }


def strip_html(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


KZN_CITIES = ["durban", "umhlanga", "ballito", "umdloti", "pietermaritzburg",
              "st lucia", "stanger", "kwadukuza", "richards bay", "empangeni",
              "newcastle", "ladysmith", "port shepstone", "margate", "southbroom",
              "umkomaas", "scottburgh", "amanzimtoti", "tongaat", "verulam",
              "hillcrest", "kloof", "westville", "pinetown", "glenwood",
              "bluff", "inanda", "botha\u2019s hill", "durban north", "isipingo"]
OUT_PROVINCE = ["johannesburg", "pretoria", "loftus", "gauteng", "cape town",
                "western cape", "gqeberha", "port elizabeth", "bloemfontein",
                "east london", "nelspruit", "mbombela", "polokwane", "kimberley",
                "stellenbosch", "soweto", "sandton", "midrand"]


def gate0_kzn(ev, material):
    """Deterministic location gate: event must be provably in KwaZulu-Natal."""
    text = ((material or "") + " " + (ev.get("venue") or "")).lower()
    in_kzn = any(c in text for c in KZN_CITIES)
    out = any(c in text for c in OUT_PROVINCE)
    if out and not in_kzn:
        return False
    return in_kzn


def _gemini_json(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    # discover live models, prefer flash variants, then fallbacks
    models = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
    try:
        lr = requests.get("https://generativelanguage.googleapis.com/v1beta/models?key=" + key,
                          timeout=40)
        if lr.status_code == 200:
            ids = [m["name"].split("/")[-1] for m in lr.json().get("models", [])]
            flash = [i for i in ids if "flash" in i.lower() and "vision" not in i.lower()]
            models = list(dict.fromkeys((flash or ids)[:3] + models))
    except Exception:
        pass
    for model in models:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json",
                                           "temperature": 0.3}},
                timeout=70)
            if r.status_code == 200:
                print("gemini ok via", model)
                return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            print("gemini http", r.status_code, "model", model)
        except Exception as e:
            print("gemini failed:", type(e).__name__)
    return None


def ai_writer(ev, material):
    d = _gemini_json(
        "You write for Welcome SA, a KwaZulu-Natal events guide. Using ONLY the "
        "material below (never invent facts), return JSON with:\n"
        '- "deepdive": 2-3 warm, plain sentences about the event and its appeal.\n'
        '- "why_go": one short sentence - who will love this.\n'
        '- "good_to_know": one practical sentence from the material.\n'
        "Plain English, no exclamation marks.\n\n"
        f"EVENT: {ev.get('name')} | venue: {ev.get('venue')} | start: {ev.get('start')}\n"
        f"MATERIAL:\n{material[:4500]}")
    if not d:
        return None
    return {k: str(d.get(k, "")).strip() for k in ("deepdive", "why_go", "good_to_know")}


def ai_critic(ev, material, draft):
    return _gemini_json(
        "You are a strict fact-checker for a KZN events guide. Check:\n"
        "1. Is the venue/city genuinely in KwaZulu-Natal?\n"
        "2. Is the event date in the future?\n"
        "3. Does the DRAFT claim anything not supported by the MATERIAL?\n"
        'Return JSON: {"in_kzn": true/false, "date_future": true/false, '
        '"invented": "none or the claim", "verdict": "PASS" or "FAIL", '
        '"issues": "one short sentence"}\n\n'
        f"EVENT: {ev.get('name')} | venue: {ev.get('venue')} | start: {ev.get('start')}\n"
        f"MATERIAL:\n{material[:3000]}\n\nDRAFT:\n"
        + json.dumps(draft)[:1500])


def ai_judge(ev, draft, critic):
    critic = critic or {}
    return _gemini_json(
        "You are the final editor. Decide SERVE or DROP. Rules: DROP if in_kzn is "
        "false, or date_future is false, or invented claims are serious. If only "
        'minor issues, SERVE. Return JSON: {"decision": "SERVE" or "DROP", '
        '"reason": "short sentence", "fixed_venue": "or empty", '
        '"fixed_city": "or empty"}.\n\n'
        f"EVENT: {ev.get('name')} at {ev.get('venue')}\n"
        f"CRITIC: {json.dumps(critic)[:800]}")


def jury(ev, material):
    """Gate 0 -> Writer -> Critic -> Judge. Returns (event_or_None, drop_reason)."""
    if not gate0_kzn(ev, material):
        return None, "gate0: not confirmed KZN"
    draft = ai_writer(ev, material)
    if not draft:
        return None, "writer unavailable (no AI key?)"
    critic = ai_critic(ev, material, draft) or {}
    judge = ai_judge(ev, draft, critic) or {}
    if str(judge.get("decision", "")).upper() == "SERVE":
        ev.update(draft)
        if judge.get("fixed_venue"):
            ev["venue"] = judge["fixed_venue"]
        return ev, None
    reason = judge.get("reason") or critic.get("issues") or "rejected by jury"
    return None, "jury: " + str(reason)[:120]


def main():
    os.makedirs(DATA, exist_ok=True)
    sources = DEFAULT_SOURCES
    if os.path.exists(SRC):
        try:
            sources = json.load(open(SRC))
        except Exception:
            pass

    all_events, report = [], []
    page_texts = {}
    for s in sources:
        entry = {"name": s["name"], "url": s["url"], "ok": False, "events_found": 0,
                 "note": ""}
        try:
            from urllib.parse import urljoin, urlparse
            if s.get("sitemap"):
                pattern = s.get("url_filter", "event|show|concert|festival")
                urls, sample = sitemap_urls(s["url"], pattern)
                if not urls and s.get("discover"):
                    root = urlparse(s["url"]).scheme + "://" + urlparse(s["url"]).netloc
                    try:
                        rb = requests.get(root + "/robots.txt", headers=H, timeout=30)
                        smaps = re.findall(r"(?im)^sitemap:\s*(\S+)", rb.text)
                        entry["debug_robots_sitemaps"] = smaps[:6]
                        for sm in smaps[:4]:
                            u2, s2 = sitemap_urls(sm, pattern)
                            urls += u2
                            if not sample:
                                sample = s2
                            time.sleep(1)
                            if len(urls) >= 25:
                                break
                    except Exception:
                        pass
                urls = urls[:25]
                entry["debug_links"] = urls[:8]
                entry["debug_sitemap_sample"] = sample
                evs = []
                for u in urls:
                    try:
                        rr = requests.get(u, headers=H, timeout=30)
                        if rr.status_code == 200:
                            evs += extract_jsonld_events(rr.text)
                            page_texts[u] = strip_html(rr.text)
                    except Exception:
                        pass
                    time.sleep(1)
                entry["ok"] = True
                entry["events_found"] = len(evs)
                all_events += [norm(e, s["name"]) for e in evs]
                report.append(entry)
                time.sleep(2)
                continue
            r = requests.get(s["url"], headers=H, timeout=40)
            entry["http"] = r.status_code
            if r.status_code == 200:
                evs = extract_jsonld_events(r.text)
                # follow event detail links incl. subdomains (listings often lack JSON-LD)
                root = urlparse(s["url"]).netloc.split(":")[0]
                root = ".".join(root.split(".")[-2:])
                seen_links, all_hrefs = [], []
                for h in re.findall(r'href="([^"]+)"', r.text, re.I):
                    all_hrefs.append(h)
                    if not re.search(r"event|whats-on|show|book|tickets?", h, re.I):
                        continue
                    u = urljoin(s["url"], h)
                    n = urlparse(u).netloc.split(":")[0]
                    if (n == root or n.endswith("." + root)) and u not in seen_links:
                        seen_links.append(u)
                entry["debug_links"] = seen_links[:8]
                entry["debug_href_sample"] = all_hrefs[:8]
                for u in seen_links[:20]:
                    try:
                        rr = requests.get(u, headers=H, timeout=30)
                        if rr.status_code == 200:
                            evs += extract_jsonld_events(rr.text)
                            page_texts[u] = strip_html(rr.text)
                    except Exception:
                        pass
                    time.sleep(1)
                entry["ok"], entry["events_found"] = True, len(evs)
                all_events += [norm(e, s["name"]) for e in evs]
            else:
                entry["note"] = "unexpected status"
        except Exception as e:
            entry["note"] = type(e).__name__
        report.append(entry)
        time.sleep(2)  # polite between sources

    _k = os.environ.get("GEMINI_API_KEY")
    print(f"AI key diagnostic: present={'GEMINI_API_KEY' in os.environ} length={len(_k) if _k else 0}")
    if os.environ.get("GEMINI_API_KEY"):
        st = _gemini_json('Reply with JSON: {"ok": true}')
        print("gemini self-test:", bool(st and st.get("ok")))
    # --- Gate 0 + three-agent jury (max 15 served per run; when in doubt, drop) ---
    served, dropped = [], []
    for e in all_events:
        if len(served) >= 15:
            break
        material = page_texts.get(e.get("url") or "", "")
        ok, why = jury(e, material)
        time.sleep(2)
        if ok:
            served.append(e)
        else:
            dropped.append({"name": e.get("name"), "source": e.get("source"),
                            "reason": why})
    print(f"jury: {len(served)} served, {len(dropped)} dropped")
    all_events = served

    seen = set()
    uniq = []
    for e in all_events:
        if e["name"]:
            k = (e["name"], e["start"], e["venue"])
            if k not in seen:
                seen.add(k)
                uniq.append(e)
    all_events = uniq
    all_events.sort(key=lambda e: e["start"])

    prev = {}
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT))
        except Exception:
            pass

    working = [r for r in report if r["ok"] and r["events_found"] > 0]
    doc = {
        "generated_at": NOW.isoformat(),
        # carry forward only when NO source worked; an empty jury result is truth
        "events": all_events if all_events else (
            prev.get("events", []) if not any(s.get("ok") for s in report) else []),
        "dropped": dropped[-20:],
        "sources": report,
        "ok": bool(working),
        "note": ("" if working else
                 "No source yielded events yet - tune data/gig_sources.json"),
    }
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)

    print(f"gigs: {len(all_events)} events from {len(working)} working source(s)")
    for r in report:
        print(f"  [{ 'OK ' if r['ok'] else '---'}] {r['name']}: {r.get('events_found', 0)}"
              f" ({r.get('http', '?')}) {r['note']}")
    print("RESULT:", "GIG SOURCE FOUND" if working else "SOURCES NEED TUNING")
    sys.exit(0)


if __name__ == "__main__":
    main()
