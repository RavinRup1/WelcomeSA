#!/usr/bin/env python3
"""WelcomeSA watchdog - DBN-Stacks-standard voice (refined 10 Oct, Ravin GO).

Two health signals, never one:
  1. MISSED RUNS - hours since welcomesa-robot last completed (>26h = alarm)
  2. FILE FRESHNESS - pillar files past their age thresholds
On alarm: re-run the robot AND open exactly ONE robot-down issue (dedupe by
label) so Ravin's GitHub app pings him. Kimi closes robot-down issues after
verified recovery - that is the 00-PROTOCOL standard, not time."""

import json, os, subprocess, sys
from datetime import datetime, timezone

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
THRESHOLDS = [
    ("news.json", 2),
    ("gigs.json", 2),
    ("attractions.json", 35),
    ("projects.json", 35),
]
RUN_STALE_HOURS = 26  # daily robot + buffer
REPO = os.environ.get("GITHUB_REPOSITORY", "RavinRup1/WelcomeSA")

now = datetime.now(timezone.utc)
problems = []


def gh(args):
    return subprocess.run(["gh"] + args, capture_output=True, text=True)


# --- signal 1: missed runs -----------------------------------------------
try:
    out = gh(["api", f"repos/{REPO}/actions/runs?per_page=30"])
    hours = None
    if out.returncode == 0:
        for run in json.loads(out.stdout).get("workflow_runs", []):
            if run.get("name") == "welcomesa-robot" and run.get("status") == "completed":
                t = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
                hours = (now - t).total_seconds() / 3600
                break
    if hours is None:
        problems.append("no completed welcomesa-robot run found in the last 30 runs")
    elif hours > RUN_STALE_HOURS:
        problems.append(f"welcomesa-robot last ran {hours:.1f}h ago (limit {RUN_STALE_HOURS}h)")
    else:
        print(f"robot last ran {hours:.1f}h ago - ok")
except Exception as e:
    print("run-check failed (non-fatal):", type(e).__name__)

# --- signal 2: file freshness --------------------------------------------
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
        problems.append(f"{f} stale or missing")

if not problems:
    print("all signals green - nothing to do")
    sys.exit(0)

print("ALARM:", " | ".join(problems))

# --- heal: re-run the robot ----------------------------------------------
print("re-running welcomesa-robot")
gh(["workflow", "run", "welcomesa-robot", "--ref", "main"])

# --- shout: exactly ONE issue per incident --------------------------------
open_issues = gh(["issue", "list", "--label", "robot-down", "--state", "open",
                  "--json", "number"])
n = len(json.loads(open_issues.stdout or "[]"))
if n == 0:
    body = ("Watchdog alarm at " + now.isoformat() + "\n\n"
            + "\n".join("- " + p for p in problems)
            + "\n\nAuto re-run attempted. If this issue is still open, the "
              "robot needs eyes. Kimi closes these after verified recovery.")
    gh(["issue", "create", "--title",
        "ROBOT-DOWN: welcomesa robot stale or data old",
        "--body", body, "--label", "robot-down"])
    print("robot-down issue opened")
else:
    print(f"robot-down issue already open - not duplicating")
