#!/usr/bin/env python3
"""WelcomeSA robot 1 - Explore SA: KZN attractions from Wikipedia (CC BY-SA,
attributed). Category walk for breadth + must-include verification (the M1 gate).
Writes data/attractions.json and data/ATTRIBUTION.md. Never a blank app:
on failure keeps previous data and stamps the error."""

import json, os, re, sys, time
from datetime import datetime, timezone

def fresh_out(path, days):
    """Self-throttle: skip if output younger than `days` unless FORCE=1."""
    if os.environ.get("FORCE") == "1":
        return False
    if os.path.exists(path):
        try:
            d = json.load(open(path))
            ts = d.get("generated_at") or d.get("updated")
            if ts:
                age = (NOW - datetime.fromisoformat(ts)).total_seconds()
                return age < days * 86400
        except Exception:
            pass
    return False

from zoneinfo import ZoneInfo

import requests

SAST = ZoneInfo("Africa/Johannesburg")
NOW = datetime.now(SAST)
H = {"User-Agent": "WelcomeSA-robot/1.0 (ravin.rup1@gmail.com)"}
API = "https://en.wikipedia.org/w/api.php"

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUT = os.path.join(DATA, "attractions.json")
ATTR = os.path.join(DATA, "ATTRIBUTION.md")

# Manual overrides for the must-include gate: display name -> exact
# Wikipedia title. Ravin decides these (local knowledge wins).
OVERRIDES = {}

# Ravin's 30 approved curated picks that the CATEGORY WALK misses (Batch 1,
# approved 6 Oct). The 8 Oct multi-province regen silently dropped 21 of them
# (Ravin caught the symptom: every carousel tap felt the same). This list makes
# the robot fetch them DIRECTLY from Wikipedia every run - curated content can
# never be lost to a regen again. Ravin catch -> system fix.
CURATED_EXTRA = {
    "Ballito (Willard Beach)": ("Ballito", "beach"),
    "Umdloti Beach": ("Umdloti Beach", "beach"),
    "Southbroom": ("Southbroom", "beach"),
    "Krantzkloof Nature Reserve": ("Krantzkloof Nature Reserve", "natural"),
    "Phoenix Settlement (Inanda)": ("Phoenix Settlement", "historical"),
    "BAT Centre": ("BAT Centre", "cultural"),
    "KZNSA Gallery (Glenwood)": ("KZNSA", "cultural"),
    "Isandlwana & Rorke's Drift": ("Isandlwana", "historical"),
    "The Old Fort, Durban": ("Old Fort (Durban)", "historical"),
    "KwaDukuza (Stanger)": ("KwaDukuza", "historical"),
    "Durban City Hall": ("Durban City Hall", "historical"),
    "Groutville - Chief Albert Luthuli": ("Groutville", "historical"),
    "Valley of a Thousand Hills": ("Valley of a Thousand Hills", "natural"),
    "Aliwal Shoal (Umkomaas)": ("Aliwal Shoal", "wildlife"),
    "Giba Gorge (Hillcrest)": ("Giba Gorge", "activity"),
    "The Sardine Run": ("Sardine run", "wildlife"),
    "Hluhluwe-iMfolozi Park": ("Hluhluwe\u2013iMfolozi Park", "wildlife"),
    "iSimangaliso Wetland Park (St Lucia)": ("iSimangaliso Wetland Park", "natural"),
}

# Ravin's must-include list (the M1 quality gate)
MUST_INCLUDE = [
    "uShaka Marine World", "Moses Mabhida Stadium",
    "Suncoast Casino, Hotels & Entertainment",
    "Umgeni River Bird Park",
    "Golden Mile, Durban", "Durban Botanic Gardens",
    "uMhlanga Rocks", "Beachwood Mangroves Nature Reserve",
    "Kenneth Stainbank Nature Reserve",
]

CATEGORIES = {
    "Category:Tourist attractions in KwaZulu-Natal": ("KwaZulu-Natal", None),
    "Category:Tourist attractions in Durban": ("KwaZulu-Natal", None),
    "Category:Beaches of KwaZulu-Natal": ("KwaZulu-Natal", "beach"),
    "Category:Nature reserves in KwaZulu-Natal": ("KwaZulu-Natal", "natural"),
    "Category:Museums in KwaZulu-Natal": ("KwaZulu-Natal", "cultural"),
    "Category:Sports venues in KwaZulu-Natal": ("KwaZulu-Natal", "activity"),
    "Category:Parks in KwaZulu-Natal": ("KwaZulu-Natal", "natural"),
    "Category:Botanical gardens in South Africa": ("South Africa", "natural"),
    "Category:Aquaria in South Africa": ("South Africa", "wildlife"),
    "Category:Zoos in South Africa": ("South Africa", "wildlife"),
    "Category:Casinos in South Africa": ("South Africa", "cultural"),
    "Category:Amusement parks in South Africa": ("South Africa", "activity"),
    "Category:Tourist attractions in Gauteng": ("Gauteng", None),
    "Category:Tourist attractions in Johannesburg": ("Gauteng", None),
    "Category:Tourist attractions in Pretoria": ("Gauteng", None),
    "Category:Museums in Johannesburg": ("Gauteng", "cultural"),
    "Category:Tourist attractions in the Western Cape": ("Western Cape", None),
    "Category:Tourist attractions in Cape Town": ("Western Cape", None),
    "Category:Museums in Cape Town": ("Western Cape", "cultural"),
    "Category:Beaches of the Western Cape": ("Western Cape", "beach"),
    "Category:Nature reserves in the Western Cape": ("Western Cape", "natural"),
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
    """Multi-attempt: full name, then shorter variants, then full-text search."""
    variants = [name, name.split(",")[0], " ".join(name.split()[:3])]
    for v in dict.fromkeys(variants):
        try:
            d = wiki({"action": "opensearch", "search": v, "limit": 5, "namespace": 0})
            if d and len(d) == 4 and d[1]:
                return d[1][0]
        except Exception:
            pass
        time.sleep(1)
    try:
        d = wiki({"action": "query", "list": "search", "srsearch": f'"{name}"',
                  "srlimit": 1})
        hits = d["query"]["search"]
        return hits[0]["title"] if hits else None
    except Exception:
        return None


def fetch_pages(titles):
    """Batch-fetch intro extract, coordinates, thumbnail for <=20 titles."""
    pages = {}
    req_map = {}
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        d = wiki({"action": "query", "prop": "extracts|coordinates|pageimages",
                  "exintro": 1, "explaintext": 1, "exchars": "600",
                  "colimit": "max", "pithumbsize": 500, "redirects": 1,
                  "titles": "|".join(batch)})
        for pid, pg in d["query"]["pages"].items():
            pages[pg["title"]] = pg
        for red in d["query"].get("redirects", []):
            req_map.setdefault(norm(red["to"]), set()).add(red["from"])
        for t in batch:
            req_map.setdefault(norm(t), set()).add(t)
        time.sleep(1)  # polite
    # retry stubs: pages whose intro extract came back empty (some redirects/short
    # articles have no exintro) - take the lead of the full plain-text extract
    nointro = [t for t, pg in pages.items() if not (pg.get("extract") or "").strip()]
    for i in range(0, len(nointro), 20):
        d = wiki({"action": "query", "prop": "extracts", "explaintext": 1,
                  "exchars": "900", "redirects": 1,
                  "titles": "|".join(nointro[i:i + 20])})
        for pid, pg in d.get("query", {}).get("pages", {}).items():
            key = next((t for t in pages if norm(t) == norm(pg.get("title", ""))), None)
            if key and not (pages[key].get("extract") or "").strip():
                pages[key]["extract"] = pg.get("extract") or ""
        time.sleep(1)
    return pages, req_map


def norm(s):
    """lowercase alphanumeric+spaces key for tolerant title matching"""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", (s or "").lower())).strip()


def commons_image(queries):
    """Fallback when a Wikipedia article has no lead image: search Wikimedia
    Commons for a usable photo. A candidate counts only if its FILE NAME
    carries at least min(2, available) significant words of the place name -
    learned 10 Oct the hard way: fulltext search served "KZNSA_women's_400m.jpg"
    (an athletics meet) for the KZNSA ART GALLERY."""
    stop = {"south", "africa", "kwazulu", "natal"}

    def sig(q):
        return [w for w in re.sub(r"[^a-z0-9 ]", "", q.lower()).split()
                if len(w) >= 5 and w not in stop]

    for query in queries:
        words = sig(query)
        if not words:
            continue
        try:
            d = requests.get("https://commons.wikimedia.org/w/api.php", params={
                "action": "query", "format": "json", "list": "search",
                "srsearch": query, "srnamespace": "6", "srlimit": "8"},
                headers=H, timeout=30).json()
            for hit in d.get("query", {}).get("search", []):
                t = hit["title"]
                if not t.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    continue
                fn = t.lower()
                if sum(1 for w in words if w in fn) < min(2, len(words)):
                    continue
                di = requests.get("https://commons.wikimedia.org/w/api.php", params={
                    "action": "query", "format": "json", "titles": t,
                    "prop": "imageinfo", "iiprop": "url", "iiurlwidth": "800"},
                    headers=H, timeout=30).json()
                for _pid, pg in di.get("query", {}).get("pages", {}).items():
                    ii = (pg.get("imageinfo") or [{}])[0]
                    if ii.get("thumburl"):
                        return ii["thumburl"]
        except Exception:
            pass
    return None


def categorize(title, in_cats):
    for cat, forced in in_cats.items():
        if isinstance(forced, str) and title in forced:
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
    if fresh_out(OUT, 30):
        print("attractions: fresh (<30 days), skipping")
        return
    # 1. breadth: category walk
    titles, in_cats = set(), {}
    cat_errors = {}
    prov_of = {}
    forced_cat = {}
    for cat, (prov, forced) in CATEGORIES.items():
        try:
            for t in category_members(cat):
                titles.add(t)
                prov_of.setdefault(t, prov)
                if forced:
                    in_cats.setdefault(cat, set()).add(t)
        except Exception as e:
            cat_errors[cat] = str(e)
        time.sleep(1)

    # 2. must-include gate: make sure each is present (search if missing)
    check = {}
    for want in MUST_INCLUDE:
        hit = OVERRIDES.get(want) or (want if want in titles else search_title(want))
        check[want] = hit
        if hit:
            titles.add(hit)
    missing = [w for w, h in check.items() if not h]

    # 2b. curated extras: direct fetch every run (regen-proof, Ravin catch 8 Oct)
    JUNK_TITLES = {"BabyCenter", "Crossworld"}   # search fallback can grab these; never serve them
    extra_check = {}
    extra_alias = {}
    for want, (wiki_name, cat) in CURATED_EXTRA.items():
        hit = OVERRIDES.get(want) or (wiki_name if wiki_name in titles else search_title(wiki_name))
        if hit in JUNK_TITLES:
            hit = None
        extra_check[want] = hit
        if hit:
            titles.add(hit)
            prov_of[hit] = "KwaZulu-Natal"
            forced_cat[hit] = cat
            extra_alias.setdefault(hit, [])
            if want not in extra_alias[hit]:
                extra_alias[hit].append(want)
            if wiki_name not in extra_alias[hit]:
                extra_alias[hit].append(wiki_name)

    # 3. fetch page data
    pages, req_map = fetch_pages(sorted(titles))

    # 4. build records
    attractions = []
    for title in sorted(pages):
        pg = pages[title]
        extract = (pg.get("extract") or "").strip()
        if not extract:
            continue
        summary = extract.split("\n")[0][:400]
        coord = (pg.get("coordinates") or [{}])[0]
        img = (pg.get("thumbnail") or {}).get("source")
        img_lic = "Wikipedia, CC BY-SA 4.0"
        if not img:
            names_q = [title.split("(")[0].strip()] + sorted(req_map.get(norm(title), set()))
            cimg = commons_image(names_q)
            if cimg:
                img = cimg
                img_lic = "Wikimedia Commons - see file page for its licence"
        attractions.append({
            "id": re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"),
            "name": title,
            "summary": summary,
            "province": prov_of.get(title, "South Africa"),
            "category": forced_cat.get(title) or categorize(title, in_cats),
            "lat": coord.get("lat"), "lng": coord.get("lon"),
            "image": img,
            "source_url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
            "license": "Text: Wikipedia, CC BY-SA 4.0. Image: " + img_lic,
            "added": NOW.date().isoformat(),
        })
        requested = req_map.get(norm(title), set())
        for k, v in extra_alias.items():
            if norm(k) == norm(title) or norm(k) in {norm(t) for t in requested}:
                attractions[-1]["aliases"] = v
                break

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
        "curated_extra_check": extra_check,
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
