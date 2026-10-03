"""
review_me.py: written by an AI coding assistant in one shot and merged without review.

Your job (write it in REVIEW.md):
  1. Find at least 5 real problems, most serious first. For each, say what goes wrong,
     with a concrete example (not just "bad practice").
  2. Fix the 2-3 most serious ones in this file.
Don't rewrite it from scratch. Reviewing is the skill being tested.
"""

import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

import requests

PORTAL = "http://127.0.0.1:8765"
HEADERS = {"X-Api-Key": "dfhire-2026"}

MAX_ATTEMPTS = 5
REQUEST_TIMEOUT = 5


def fetch_inventory(store_id, as_of, cursor="0", results=None):
    """Fetch every inventory page for a store with bounded retries."""
    if results is None:
        results = []

    while True:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                r = requests.get(
                    f"{PORTAL}/v1/stores/{store_id}/inventory",
                    params={"as_of": as_of, "cursor": cursor},
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT,
                )

                # QuickMart tells us how long to wait after rate limiting.
                if r.status_code == 429:
                    retry_after = int(r.headers.get("Retry-After", "2"))

                    if attempt == MAX_ATTEMPTS:
                        r.raise_for_status()

                    time.sleep(retry_after)
                    continue

                # Temporary server failures can be retried with backoff.
                if r.status_code in (500, 503):
                    if attempt == MAX_ATTEMPTS:
                        r.raise_for_status()

                    time.sleep(0.5 * (2 ** (attempt - 1)))
                    continue

                # Other HTTP errors are not blindly retried.
                r.raise_for_status()
                body = r.json()
                break

            except (requests.Timeout, requests.ConnectionError):
                if attempt == MAX_ATTEMPTS:
                    raise

                time.sleep(0.5 * (2 ** (attempt - 1)))

        results.extend(body["items"])

        if body["next_cursor"]:
            cursor = body["next_cursor"]
            continue

        return results


def save(conn, store_id, items):
    for it in items:
        conn.execute(
            f"INSERT INTO inventory VALUES ('{store_id}', '{it['sku_id']}', "
            f"'{it['name']}', {int(it['in_stock'])}, {it['qty']}, "
            f"'{it['observed_at']}')"
        )

    conn.commit()


def city_osa(conn, city, day=None):
    """On-shelf availability for a city on a day. Defaults to yesterday."""
    day = day or (date.today() - timedelta(days=1)).isoformat()

    stores = [
        r[0]
        for r in conn.execute(
            "SELECT store_id FROM stores WHERE city = ?",
            (city,),
        )
    ]

    per_store = []

    for s in stores:
        rows = conn.execute(
            "SELECT qty FROM inventory "
            "WHERE store_id = ? AND substr(observed_at, 1, 10) = ?",
            (s, day),
        ).fetchall()

        in_stock = sum(1 for (qty,) in rows if qty > 0)
        per_store.append(
            in_stock / len(rows) if rows else 0.0
        )

    return round(
        100 * sum(per_store) / len(per_store),
        2,
    )


if __name__ == "__main__":
    conn = sqlite3.connect("osa.db")

    conn.execute(
        "CREATE TABLE IF NOT EXISTS stores "
        "(store_id TEXT, city TEXT)"
    )

    conn.execute(
        "CREATE TABLE IF NOT EXISTS inventory "
        "(store_id TEXT, sku_id TEXT, name TEXT, "
        "in_stock INT, qty INT, observed_at TEXT)"
    )

    # Use a timezone-aware UTC timestamp.
    as_of = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    for sid in ["MUM-001", "MUM-002"]:
        save(
            conn,
            sid,
            fetch_inventory(sid, as_of),
        )

    print(city_osa(conn, "Mumbai"))