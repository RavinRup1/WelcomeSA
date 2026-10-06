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
    events = []
    for block in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                            html, re.S | re.I):
        try:
            data = json.loads(unescape(block.strip()))
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Event":
                events.append(item)
            if isinstance(item, dict) and "@graph" in item:
                events += [x for x in item["@graph"]
                           if isinstance(x, dict) and x.get("@type") == "Event"]
    return events


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


def main():
    os.makedirs(DATA, exist_ok=True)
    sources = DEFAULT_SOURCES
    if os.path.exists(SRC):
        try:
            sources = json.load(open(SRC))
        except Exception:
            pass

    all_events, report = [], []
    for s in sources:
        entry = {"name": s["name"], "url": s["url"], "ok": False, "events_found": 0,
                 "note": ""}
        try:
            r = requests.get(s["url"], headers=H, timeout=40)
            entry["http"] = r.status_code
            if r.status_code == 200:
                evs = extract_jsonld_events(r.text)
                entry["ok"], entry["events_found"] = True, len(evs)
                all_events += [norm(e, s["name"]) for e in evs]
            else:
                entry["note"] = "unexpected status"
        except Exception as e:
            entry["note"] = type(e).__name__
        report.append(entry)
        time.sleep(2)  # polite between sources

    all_events = [e for e in all_events if e["name"]]
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
        "events": all_events or prev.get("events", []),
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
