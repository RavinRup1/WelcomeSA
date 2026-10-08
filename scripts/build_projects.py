#!/usr/bin/env python3
"""WelcomeSA robot 4 - Development projects (SA). Two-weekly.
Seed list (data/projects_seed.json) + Wikipedia grounding + AI deep-dive.
Seeds curated by Ravin.R & Kimi; Ravin can extend the seed file anytime."""

import json, os, re, sys, time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

SAST = ZoneInfo("Africa/Johannesburg")
NOW = datetime.now(SAST)
H = {"User-Agent": "WelcomeSA-robot/1.0 (ravin.rup1@gmail.com)"}
API = "https://en.wikipedia.org/w/api.php"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUT = os.path.join(DATA, "projects.json")
SEED = os.path.join(DATA, "projects_seed.json")

DEFAULT_SEED = [
    {"name": "Lesotho Highlands Water Project (Phase II)", "match": ["Lesotho Highlands Water Project"],
     "province": "Free State / Lesotho", "sector": "Water"},
    {"name": "Msikaba Bridge", "match": ["Msikaba Bridge"],
     "province": "Eastern Cape", "sector": "Transport"},
    {"name": "Mtentu Bridge", "match": ["Mtentu Bridge"],
     "province": "Eastern Cape", "sector": "Transport"},
    {"name": "Umzimvubu Dam", "match": ["Umzimvubu Dam"],
     "province": "Eastern Cape", "sector": "Water"},
    {"name": "Durban Dig-Out Port", "match": ["Port of Durban"],
     "province": "KwaZulu-Natal", "sector": "Ports"},
    {"name": "Gautrain Network Expansion", "match": ["Gautrain"],
     "province": "Gauteng", "sector": "Rail"},
    {"name": "N2 Wild Coast Toll Road", "match": ["N2 (South Africa)"],
     "province": "Eastern Cape / KZN", "sector": "Roads"},
]


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


def wiki_pages(titles):
    out = {}
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        try:
            r = requests.get(API, params={
                "action": "query", "prop": "extracts|coordinates|pageimages",
                "exintro": 1, "explaintext": 1, "exchars": "1200",
                "colimit": "max", "pithumbsize": 600,
                "titles": "|".join(batch), "format": "json"},
                headers=H, timeout=40)
            for pg in r.json()["query"]["pages"].values():
                out[pg["title"]] = pg
        except Exception:
            pass
        time.sleep(1)
    return out


def _gemini_json(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent?key=" + key,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"responseMimeType": "application/json",
                                       "temperature": 0.3}},
            timeout=70)
        if r.status_code != 200:
            return None
        return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        return None


def main():
    os.makedirs(DATA, exist_ok=True)
    if fresh_out(OUT, 30):
        print("projects: fresh (<30 days), skipping")
        return
    seeds = DEFAULT_SEED
    if os.path.exists(SEED):
        try:
            seeds = json.load(open(SEED))
        except Exception:
            pass

    norm = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()
    pages = wiki_pages([m for s in seeds for m in s.get("match", [s["name"]])])

    projects = []
    for s in seeds:
        pg = None
        for m in s.get("match", [s["name"]]):
            for title, p in pages.items():
                if norm(title) == norm(m) or norm(m) in norm(title):
                    pg = p
                    break
            if pg:
                break
        material = (pg or {}).get("extract", "")[:1500]
        rec = {"name": s["name"], "province": s.get("province", ""),
               "sector": s.get("sector", ""),
               "image": ((pg or {}).get("thumbnail") or {}).get("source"),
               "source_url": "https://en.wikipedia.org/wiki/" +
                             (pg["title"].replace(" ", "_") if pg else s["name"].replace(" ", "_"))}
        if material:
            d = _gemini_json(
                "You write for Welcome SA's development-projects pillar. Using ONLY "
                "the material below, return JSON:\n"
                '- "what": one sentence - what the project is.\n'
                '- "why": one sentence - why it matters for South Africa.\n'
                '- "status": the construction/status phase stated in the material, '
                'or "status not stated in source".\n'
                "Plain English, no exclamation marks, never invent facts.\n\n"
                f"PROJECT: {s['name']}\nMATERIAL:\n{material}")
            if d:
                rec.update({k: str(d.get(k, "")).strip() for k in ("what", "why", "status")})
            coord = (pg.get("coordinates") or [{}])[0]
            rec["lat"], rec["lng"] = coord.get("lat"), coord.get("lon")
        projects.append(rec)
        time.sleep(2)

    doc = {"generated_at": NOW.isoformat(),
           "note": "Statuses as per latest available sources; Ravin can extend "
                   "data/projects_seed.json anytime.",
           "projects": projects,
           "ok": bool(projects)}
    with open(OUT, "w") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    print(f"projects: {len(projects)} written")


if __name__ == "__main__":
    main()
