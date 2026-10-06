#!/usr/bin/env python3
"""WelcomeSA robot 1 - Explore SA: KZN attractions from Wikipedia (CC BY-SA,
attributed). Category walk for breadth + must-include verification (the M1 gate).
Writes data/attractions.json and data/ATTRIBUTION.md. Never a blank app:
on failure keeps previous data and stamps the error."""

import json, os, re, sys, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

SAST = ZoneInfo("Africa/Johannesburg")
NOW = datetime.now(SAST)
H = {"User-Agent": "WelcomeSA-robot/1.0 (ravin.rup1@gmail.com)"}
API = "https://en.wikipedia.org/w/api.php"

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUT = os.path.join(DATA, "attractions.json")
ATTR = os.path.join(DATA, "ATTRIBUTION.md")

# Ravin's must-include list (the M1 quality gate)
MUST_INCLUDE = [
    "uShaka Marine World", "Moses Mabhida Stadium",
    "Suncoast Casino, Hotels & Entertainment",
    "Durban Natural Science Museum", "Umgeni River Bird Park",
    "Golden Mile, Durban", "Durban Botanic Gardens",
    "uMhlanga Rocks", "Beachwood Mangroves Nature Reserve",
    "Kenneth Stainbank Nature Reserve",
]

CATEGORIES = {
    "Category:Tourist attractions in KwaZulu-Natal": None,
    "Category:Tourist attractions in Durban": None,
    "Category:Beaches of KwaZulu-Natal": "beach",
    "Category:Nature reserves in KwaZulu-Natal": "natural",
    "Category:Museums in KwaZulu-Natal": "cultural",
    "Category:Sports venues in KwaZulu-Natal": "activity",
    "Category:Parks in KwaZulu-Natal": "natural",
    "Category:Botanical gardens in South Africa": "natural",
    "Category:Aquaria in South Africa": "wildlife",
    "Category:Zoos in South Africa": "wildlife",
    "Category:Casinos in South Africa": "cultural",
    "Category:Amusement parks in South Africa": "activity",
}


def wiki(params, retries=3):
    params = dict(params, format="json")
    for a in range(retries):
        try:
            r = requests.get(API, params=params, headers=H, timeout=40)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            if a == retries - 1:
                raise
        time.sleep(3)


def category_members(cat):
    out, cmcontinue = [], None
    while True:
        p = {"action": "query", "list": "categorymembers", "cmtitle": cat,
             "cmlimit": "500", "cmtype": "page"}
        if cmcontinue:
            p["cmcontinue"] = cmcontinue
        d = wiki(p)
        out += [m["title"] for m in d["query"]["categorymembers"]]
        cmcontinue = d.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            return out


def search_title(name):
    d = wiki({"action": "opensearch", "search": name, "limit": 1, "namespace": 0})
    return d[1][0] if d and len(d) == 4 and d[1] else None


def fetch_pages(titles):
    """Batch-fetch intro extract, coordinates, thumbnail for <=20 titles."""
    pages = {}
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        d = wiki({"action": "query", "prop": "extracts|coordinates|pageimages",
                  "exintro": 1, "explaintext": 1, "exchars": "600",
                  "colimit": "max", "pithumbsize": 500,
                  "titles": "|".join(batch)})
        for pid, pg in d["query"]["pages"].items():
            pages[pg["title"]] = pg
        time.sleep(1)  # polite
    return pages


def categorize(title, in_cats):
    for cat, forced in in_cats.items():
        if forced and title in cat:
            return forced
    t = title.lower()
    for k, v in [("beach", "beach"), ("museum", "cultural"), ("gallery", "cultural"),
                 ("reserve", "natural"), ("garden", "natural"), ("park", "natural"),
                 ("mountain", "natural"), ("falls", "natural"), ("dam", "natural"),
                 ("stadium", "activity"), ("casino", "cultural"), (" Aquarium", "wildlife"),
                 ("bird", "wildlife"), ("snorkel", "wildlife"), ("reef", "wildlife"),
                 ("battlefield", "historical"), ("monument", "historical"),
                 ("fort", "historical"), ("mission", "historical")]:
        if k in t:
            return v
    return "cultural"


def main():
    os.makedirs(DATA, exist_ok=True)
    # 1. breadth: category walk
    titles, in_cats = set(), {}
    cat_errors = {}
    for cat, forced in CATEGORIES.items():
        try:
            for t in category_members(cat):
                titles.add(t)
                if forced:
                    in_cats.setdefault(cat, set()).add(t)
        except Exception as e:
            cat_errors[cat] = str(e)
        time.sleep(1)

    # 2. must-include gate: make sure each is present (search if missing)
    check = {}
    for want in MUST_INCLUDE:
        hit = want if want in titles else search_title(want)
        check[want] = hit
        if hit:
            titles.add(hit)
    missing = [w for w, h in check.items() if not h]

    # 3. fetch page data
    pages = fetch_pages(sorted(titles))

    # 4. build records
    attractions = []
    for title in sorted(pages):
        pg = pages[title]
        extract = (pg.get("extract") or "").strip()
        if not extract:
            continue
        summary = extract.split("\n")[0][:400]
        coord = (pg.get("coordinates") or [{}])[0]
        attractions.append({
            "id": re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"),
            "name": title,
            "summary": summary,
            "province": "KwaZulu-Natal",
            "category": categorize(title, in_cats),
            "lat": coord.get("lat"), "lng": coord.get("lon"),
            "image": (pg.get("thumbnail") or {}).get("source"),
            "source_url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
            "license": "Text+image: Wikipedia contributors, CC BY-SA 4.0",
            "added": NOW.date().isoformat(),
        })

    prev = {}
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT))
        except Exception:
            pass

    doc = {
        "generated_at": NOW.isoformat(),
        "province": "KwaZulu-Natal",
        "count": len(attractions),
        "attractions": attractions or prev.get("attractions", []),
        "must_include_check": {w: h for w, h in check.items()},
        "must_include_missing": missing,
        "category_errors": cat_errors,
        "ok": bool(attractions),
    }
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)

    with open(ATTR, "w") as f:
        f.write("WELCOMESA ATTRIBUTION\n=====================\n"
                "Attraction text and images are from Wikipedia, licensed CC BY-SA 4.0.\n"
                "Each entry links to its source article. Maps (when added): (c) OpenStreetMap contributors, ODbL.\n"
                f"Generated: {NOW.isoformat()}\n")

    print(f"attractions: {len(attractions)} | must-include missing: {missing or 'NONE'}")
    print("categories with errors:", list(cat_errors) or "none")
    print("RESULT:", "M1 GATE PASS" if attractions and not missing else "M1 GATE CHECK NEEDED")
    sys.exit(0 if attractions else 1)


if __name__ == "__main__":
    main()
