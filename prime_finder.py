#!/usr/bin/env python3
"""
Continuous prime finder using the 6k +/- 1 optimisation.

Every prime number greater than 3 can be written as 6k-1 or 6k+1.
This script walks k = 1, 2, 3, ... and tests the two candidates
6k-1 and 6k+1 for primality using trial division by divisors that
are themselves of the form 6k +/- 1 (up to sqrt(n)).

It is designed to run in short, resumable sessions: it loads its
position from state.json, searches until a wall-clock budget runs
out, then flushes the updated state and the newly found primes so
the next session picks up exactly where this one left off.
"""

import json
import os
import time
from pathlib import Path

# --- configuration -----------------------------------------------------------
# Wall-clock budget for a single session, in seconds.
# 5 minutes = 300s. We stop a little early so GitHub Actions has time
# to commit/push the updated state before the job is killed.
DEFAULT_BUDGET_SECONDS = int(os.environ.get("PRIME_BUDGET_SECONDS", "270"))

# Where state and results live. These sit next to the script so the
# GitHub Actions checkout keeps them versioned.
BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"
PRIMES_FILE = BASE_DIR / "primes.txt"
LOG_FILE = BASE_DIR / "session.log"


def is_prime(n: int) -> bool:
    """Deterministic primality test based on the 6k +/- 1 rule.

    Divisibility by 2 and 3 is handled first; every remaining factor
    must be of the form 6k-1 or 6k+1, so we only test those up to sqrt(n).
    """
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


def load_state() -> dict:
    """Read the resume point. Starts fresh if no state exists yet."""
    if STATE_FILE.exists():
        with STATE_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    # First-ever run: 2 and 3 are primes but not of the form 6k+/-1,
    # so seed them manually and begin scanning from k = 1.
    return {
        "last_k": 0,
        "primes_found": 2,
        "largest_prime": 3,
        "sessions_run": 0,
    }


def save_state(state: dict) -> None:
    """Persist the resume point atomically."""
    tmp = STATE_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    tmp.replace(STATE_FILE)


def append_primes(primes: list) -> None:
    """Append newly discovered primes (one per line) to the results file."""
    if not primes:
        return
    with PRIMES_FILE.open("a", encoding="utf-8") as fh:
        for p in primes:
            fh.write(f"{p}\n")


def log(message: str) -> None:
    """Append a timestamped line to the session log."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run_session(budget_seconds: int) -> None:
    state = load_state()
    k = state["last_k"]
    primes_found = state["primes_found"]
    largest_prime = state["largest_prime"]
    sessions_run = state.get("sessions_run", 0)

    log(
        f"Session start: k={k}, primes_found={primes_found}, "
        f"largest_prime={largest_prime}, budget={budget_seconds}s"
    )

    start = time.monotonic()
    new_primes = []
    checked = 0

    while time.monotonic() - start < budget_seconds:
        k += 1
        for candidate in (6 * k - 1, 6 * k + 1):
            if is_prime(candidate):
                new_primes.append(candidate)
                primes_found += 1
                largest_prime = candidate
        checked += 1

        # Flush every 50,000 candidates so a hard timeout cannot lose
        # too much progress.
        if checked % 50_000 == 0:
            append_primes(new_primes)
            new_primes = []
            state.update(
                last_k=k,
                primes_found=primes_found,
                largest_prime=largest_prime,
                sessions_run=sessions_run,
            )
            save_state(state)

    # Final flush for this session.
    append_primes(new_primes)

    elapsed = time.monotonic() - start
    state = {
        "last_k": k,
        "primes_found": primes_found,
        "largest_prime": largest_prime,
        "sessions_run": sessions_run + 1,
    }
    save_state(state)

    log(
        f"Session end: k={k}, new primes in session="
        f"{len(new_primes) + (checked // 50_000) * 0}, "
        f"total primes_found={primes_found}, largest_prime={largest_prime}, "
        f"elapsed={elapsed:.1f}s"
    )


def main() -> None:
    budget = DEFAULT_BUDGET_SECONDS
    run_session(budget)


if __name__ == "__main__":
    main()
