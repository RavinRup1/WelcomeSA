#!/usr/bin/env python3
"""WelcomeSA robot 5 - Deep Dives for every attraction.
Phase B of the editor-robot plan (Ravin GO, 8 Oct 2026). Gemini writes an
extensive, warm, POSITIVE deep-dive for every attraction, grounded ONLY in
the Wikipedia summary the attractions robot already fetched - never invent.
Jury: AI writer -> AI critic -> AI judge (proven on gigs).
GATE: PUBLISH=False writes data/dives_review.json for Ravin's eyeball GO.
After his approval, flip PUBLISH=True -> writes data/dives.json live.
Monthly throttle like the other pillars; FORCE=1 overrides."""

import json, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

SAST = ZoneInfo("Africa/Johannesburg")
NOW = datetime.now(SAST)
H = {"User-Agent": "WelcomeSA-robot/1.0 (ravin.rup1@gmail.com)"}
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
ATT = os.path.join(DATA, "attractions.json")

# ---------------- GATE ----------------
PUBLISH = False   # False = review file only. Flip to True after Ravin's GO.
OUT = os.path.join(DATA, "dives.json" if PUBLISH else "dives_review.json")
THROTTLE_DAYS = 30


def fresh_out(path, days):
    """Self-throttle: skip if output younger than `days` unless FORCE=1."""
    if os.environ.get("FORCE") == "1":
        return False
    if os.path.exists(path):
        try:
            d = json.load(open(path))
            ts = d.get("generated_at")
            if ts:
                age = (NOW - datetime.fromisoformat(ts)).total_seconds()
                return age < days * 86400
        except Exception:
            pass
    return False


def _gemini_json(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    # discover live models, prefer flash variants (pattern proven 8 Oct)
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
                                           "temperature": 0.4}},
                timeout=90)
            if r.status_code == 200:
                print("gemini ok via", model)
                return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            print("gemini http", r.status_code, "model", model)
        except Exception as e:
            print("gemini failed:", type(e).__name__)
    return None


def ai_writer(att):
    return _gemini_json(
        "You write for Welcome SA, a proudly South African travel showcase. "
        "Using ONLY the MATERIAL below (never invent facts), write about the "
        "place in a warm, positive, welcoming voice - a local showing a guest "
        "the best of the country. Return JSON with:\n"
        '- "story": 4-6 vivid sentences - what it is, what it feels like, why '
        "it matters. Positive only; if the material mentions a problem, skip it "
        "or frame it as a practical tip.\n"
        '- "best": one short sentence - the best time or way to experience it.\n'
        '- "tip": one short practical insider tip drawn from the material.\n'
        "Plain English, no exclamation marks.\n\n"
        f"PLACE: {att.get('name')} | province: {att.get('province')} | "
        f"category: {att.get('category')}\nMATERIAL:\n{att.get('summary','')[:4500]}")


def ai_critic(att, draft):
    return _gemini_json(
        "You are a strict fact-checker for a South African travel guide. Check:\n"
        "1. Does the DRAFT claim anything not supported by the MATERIAL?\n"
        "2. Is the tone positive and welcoming (no doom, no warnings beyond a "
        "practical tip)?\n"
        'Return JSON: {"invented": "none or the claim", "positive": true/false, '
        '"verdict": "PASS" or "FAIL", "issues": "one short sentence"}\n\n'
        f"PLACE: {att.get('name')}\nMATERIAL:\n{att.get('summary','')[:3000]}"
        "\n\nDRAFT:\n" + json.dumps(draft)[:1800])


def ai_judge(draft, critic):
    critic = critic or {}
    return _gemini_json(
        "You are the final editor of a proudly South African travel showcase. "
        "Decide SERVE or DROP. Rules: DROP if invented is not 'none', or "
        "verdict is FAIL, or the story is flat/negative. Reply JSON: "
        '{"decision": "SERVE" or "DROP", "reason": "one short sentence"}\n\n'
        "DRAFT:\n" + json.dumps(draft)[:1800] + "\n\nCRITIC:\n"
        + json.dumps(critic)[:900])


def main():
    print("AI key visible:", bool(os.environ.get("GEMINI_API_KEY")))
    if fresh_out(OUT, THROTTLE_DAYS):
        print("fresh output, skipping (FORCE=1 to override)")
        return
    atts = json.load(open(ATT)).get("attractions", [])
    print("attractions:", len(atts))

    old = {}
    if os.path.exists(OUT):
        try:
            old = {d["id"]: d for d in json.load(open(OUT)).get("dives", [])}
        except Exception:
            pass

    dives, served, dropped = [], 0, 0
    for att in atts:
        if att.get("id") in old:            # carry-forward
            dives.append(old[att["id"]])
            served += 1
            continue
        draft = ai_writer(att)
        if not draft:
            continue                        # no key / API down: keep short summary only
        draft = {k: str(draft.get(k, "")).strip() for k in ("story", "best", "tip")}
        critic = ai_critic(att, draft)
        judge = ai_judge(draft, critic)
        if judge and judge.get("decision") == "SERVE":
            dives.append({"id": att["id"], "name": att["name"], **draft})
            served += 1
        else:
            dropped += 1
            print("dropped:", att["id"], "-", (judge or {}).get("reason", "no jury"))

    out = {"generated_at": NOW.isoformat(timespec="seconds"),
           "publish": PUBLISH, "dives": dives}
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"served {served}, dropped {dropped}, total {len(dives)} -> {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
