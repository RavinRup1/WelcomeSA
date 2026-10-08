#!/usr/bin/env python3
"""WelcomeSA watchdog - re-run the robot if any pillar goes stale.
Checks news/gigs (>2 days) and attractions/projects (>35 days).
Acts only on 3-hour boundaries, so worst case is 8 robot runs/day."""

import json, os, subprocess, sys
from datetime import datetime, timezone

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
THRESHOLDS = [
    ("news.json", 2),
    ("gigs.json", 2),
    ("attractions.json", 35),
    ("projects.json", 35),
]

now = datetime.now(timezone.utc)
stale = []
for f, days in THRESHOLDS:
    path = os.path.join(DATA, f)
    ok = False
    if os.path.exists(path):
        try:
            ts = json.load(open(path)).get("generated_at")
            if ts:
                age = (now - datetime.fromisoformat(ts)).total_seconds() / 86400
                print(f"{f}: {age:.1f} days old (limit {days})")
                ok = age < days
        except Exception as e:
            print(f"{f}: unreadable ({e})")
    else:
        print(f"{f}: missing")
    if not ok:
        stale.append(f)

if not stale:
    print("all pillars fresh - nothing to do")
    sys.exit(0)

print("STALE:", ", ".join(stale))
if now.hour % 3 != 0:
    print(f"hour {now.hour}: not a 3-hour boundary - waiting for the next check")
    sys.exit(0)

print("re-running welcomesa-robot")
r = subprocess.run(["gh", "workflow", "run", "welcomesa-robot", "--ref", "main"])
sys.exit(r.returncode)
