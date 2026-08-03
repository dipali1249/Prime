#!/usr/bin/env python3
"""
Continuous Prime Finder — runs inside a GitHub Actions workflow.

Each invocation runs for SESSION_SECONDS (default 300 s = 5 min), picks up
where the last run left off (state stored in state.json), and regenerates
index.html with a live report.

Schedule: 12 runs/day × 5 min = 60 min/day, triggered by GitHub Actions cron
every 2 hours (00:00, 02:00, … 22:00 UTC).

Usage:
    python prime_finder.py            # run a full 5-minute session
    python prime_finder.py --test 5   # run for 5 seconds (smoke test)
"""

import json
import os
import time
import math
import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SESSION_SECONDS = int(os.environ.get("SESSION_SECONDS", "300"))  # 5 minutes
KEEP_PRIMES     = 1000            # max primes kept in state / report
STATE_FILE      = Path("state.json")
REPORT_FILE     = Path("index.html")

SLOTS_UTC = list(range(0, 24, 2))  # 00,02,04,…,22

# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------
def load_state():
    """Load saved state, or initialise fresh."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "n": 2,
        "count": 0,
        "last_prime": None,
        "last_tested": None,
        "primes": [],
        "last_run_iso": None,
        "total_sessions": 0,
        "total_runtime_s": 0.0,
    }

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ---------------------------------------------------------------------------
# Primality — deterministic trial division
# ---------------------------------------------------------------------------
def is_prime(n):
    if n < 2:
        return False
    if n in (2, 3):
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True

# ---------------------------------------------------------------------------
# Search loop
# ---------------------------------------------------------------------------
def run_search(state, duration_s):
    """Check numbers for `duration_s` seconds, updating state in place."""
    n      = state["n"]
    primes = state["primes"]
    count  = state["count"]
    last_p = state["last_prime"]
    last_t = state["last_tested"]

    deadline = time.monotonic() + duration_s
    checks_since_flush = 0

    while time.monotonic() < deadline:
        # check a batch before re-reading the clock (clock reads are slow)
        for _ in range(2000):
            if is_prime(n):
                count += 1
                last_p = n
                primes.append(n)
                if len(primes) > KEEP_PRIMES:
                    primes.pop(0)
            last_t = n
            n += 1
            checks_since_flush += 1

        # periodic flush so a crash never loses a whole session
        if checks_since_flush >= 50000:
            state.update(n=n, count=count, last_prime=last_p,
                         last_tested=last_t, primes=primes)
            save_state(state)
            checks_since_flush = 0

    state["n"]           = n
    state["count"]       = count
    state["last_prime"]  = last_p
    state["last_tested"] = last_t
    state["primes"]      = primes

# ---------------------------------------------------------------------------
# Report generation (index.html)
# ---------------------------------------------------------------------------
def next_slot_utc(now_iso):
    """Return ISO string of the next 2-hour slot after `now`."""
    now = datetime.datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    for h in SLOTS_UTC:
        slot = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if slot > now:
            return slot.strftime("%Y-%m-%d %H:%M UTC")
    # after 22:00 → 00:00 next day
    tomorrow = now + datetime.timedelta(days=1)
    return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M UTC")

def generate_report(state):
    last_prime  = state["last_prime"]
    last_tested = state["last_tested"]
    count       = state["count"]
    primes      = state["primes"][-KEEP_PRIMES:]
    last_run    = state["last_run_iso"]
    next_run    = next_slot_utc(last_run) if last_run else "—"
    sessions    = state.get("total_sessions", 0)
    runtime     = state.get("total_runtime_s", 0.0)

    last_prime_s  = f"{last_prime:,}"   if last_prime  is not None else "—"
    last_tested_s = f"{last_tested:,}"  if last_tested is not None else "—"
    last_run_s    = last_run[:19] + " UTC" if last_run else "—"

    primes_html = "\n".join(
        f'<span class="{"new" if i==len(primes)-1 else ""}">{p:,} </span>'
        for i, p in enumerate(primes)
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Continuous Prime Finder — Live Report</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family:'Segoe UI',Tahoma,sans-serif;
    background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);
    color:#e0e0e0; min-height:100vh;
    display:flex; flex-direction:column; align-items:center; padding:28px 15px 40px;
  }}
  h1 {{
    font-size:1.9rem; margin-bottom:6px; text-align:center;
    background:linear-gradient(90deg,#00f2fe,#4facfe);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
  }}
  .subtitle {{ color:#999; margin-bottom:22px; font-size:.85rem; text-align:center; }}
  .status-bar {{
    display:flex; align-items:center; gap:10px;
    background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.12);
    border-radius:30px; padding:10px 24px; margin-bottom:22px; font-size:.95rem;
  }}
  .status-dot {{ width:12px; height:12px; border-radius:50%; background:#96c93d; box-shadow:0 0 12px #96c93d; }}
  .stats {{
    display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
    gap:14px; width:100%; max-width:760px; margin-bottom:22px;
  }}
  .stat-box {{
    background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.1);
    border-radius:14px; padding:16px 20px;
  }}
  .stat-box .label {{ font-size:.7rem; color:#888; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px; }}
  .stat-box .value {{ font-size:1.45rem; font-weight:700; color:#4facfe; font-family:'Courier New',monospace; word-break:break-all; }}
  .stat-box.prime .value {{ color:#96c93d; }}
  .stat-box.time .value {{ color:#f7971e; font-size:1.2rem; }}
  .section-title {{ align-self:flex-start; margin-left:calc(50% - 380px); margin-bottom:8px; font-size:.8rem; color:#888; text-transform:uppercase; letter-spacing:1px; }}
  @media (max-width:820px) {{ .section-title {{ margin-left:0; }} }}
  #primeList {{
    width:100%; max-width:760px; height:280px; overflow-y:auto;
    background:rgba(0,0,0,.35); border:1px solid rgba(255,255,255,.1);
    border-radius:14px; padding:16px; font-family:'Courier New',monospace;
    font-size:.82rem; line-height:1.7; columns:5; column-gap:14px;
  }}
  #primeList span {{ display:inline-block; color:#00f2fe; break-inside:avoid; }}
  #primeList span.new {{ color:#96c93d; font-weight:bold; }}
  .footer {{ margin-top:16px; font-size:.78rem; color:#555; text-align:center; max-width:760px; }}
  #primeList::-webkit-scrollbar {{ width:8px; }}
  #primeList::-webkit-scrollbar-thumb {{ background:rgba(79,172,254,.5); border-radius:10px; }}
</style>
</head>
<body>
  <h1>🔬 Continuous Prime Finder</h1>
  <p class="subtitle">Runs 12 sessions × 5 minutes every 2 hours via GitHub Actions — 60 min/day total.</p>

  <div class="status-bar">
    <span class="status-dot"></span>
    <span>Server-side search • last updated {last_run_s}</span>
  </div>

  <div class="stats">
    <div class="stat-box prime">
      <div class="label">Last Prime Found</div>
      <div class="value">{last_prime_s}</div>
    </div>
    <div class="stat-box">
      <div class="label">Last Tested Number</div>
      <div class="value">{last_tested_s}</div>
    </div>
    <div class="stat-box">
      <div class="label">Total Primes Found</div>
      <div class="value">{count:,}</div>
    </div>
    <div class="stat-box time">
      <div class="label">Last Run (UTC)</div>
      <div class="value">{last_run_s}</div>
    </div>
    <div class="stat-box time">
      <div class="label">Next Run (UTC)</div>
      <div class="value">{next_run}</div>
    </div>
    <div class="stat-box">
      <div class="label">Sessions / Total Runtime</div>
      <div class="value">{sessions} / {runtime:.0f}s</div>
    </div>
  </div>

  <p class="section-title">Last {len(primes)} Primes (most recent highlighted)</p>
  <div id="primeList">
{primes_html}
  </div>

  <p class="footer">
    This page is auto-generated by GitHub Actions. State persists across runs via state.json committed to the repo.
    Enable GitHub Pages (Settings → Pages → branch: main / root) to view this live.
  </p>
</body>
</html>
"""
    REPORT_FILE.write_text(html)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Continuous prime finder (GitHub Actions).")
    parser.add_argument("--test", type=int, metavar="SECS",
                        help="run for only SECS seconds (smoke test)")
    args = parser.parse_args()
    duration = args.test if args.test else SESSION_SECONDS

    state = load_state()

    print(f"=== Prime Finder Session ===")
    print(f"  Resuming from n = {state['n']:,}")
    print(f"  Primes found so far: {state['count']:,}")
    print(f"  Running for {duration}s …")

    t0 = time.monotonic()
    run_search(state, duration)
    elapsed = time.monotonic() - t0

    state["last_run_iso"]      = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state["total_sessions"]    = state.get("total_sessions", 0) + 1
    state["total_runtime_s"]   = state.get("total_runtime_s", 0.0) + elapsed

    save_state(state)
    generate_report(state)

    print(f"  Done in {elapsed:.1f}s")
    print(f"  Last tested: {state['last_tested']:,}")
    print(f"  Last prime:  {state['last_prime']:,}")
    print(f"  Total primes: {state['count']:,}")
    print(f"  Sessions: {state['total_sessions']}")
    print(f"  State saved → {STATE_FILE}")
    print(f"  Report  saved → {REPORT_FILE}")

if __name__ == "__main__":
    main()
