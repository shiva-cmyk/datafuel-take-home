
import argparse
import sqlite3
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests


DB_PATH = "osa.db"

PORTAL = "http://127.0.0.1:8765"
HEADERS = {"X-Api-Key": "dfhire-2026"}

IST = ZoneInfo("Asia/Kolkata")

MAX_HTTP_ATTEMPTS = 5
MAX_SOFT_BAN_ROUNDS = 3
SOFT_BAN_WAIT_SECONDS = 30
MAX_INVENTORY_PAGES = 100


def safe_get(url, params=None):
    """
    Make a bounded HTTP GET request.

    Retries:
    - 429
    - 500
    - 503
    - timeout
    - connection/request errors

    Does not retry:
    - 400
    - 401
    - 404
    """

    for attempt in range(MAX_HTTP_ATTEMPTS):
        time.sleep(0.5)

        try:
            response = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=5,
            )

            if response.status_code == 429:
                retry_after = response.headers.get(
                    "Retry-After",
                    "2",
                )

                try:
                    wait_seconds = float(retry_after)
                except ValueError:
                    wait_seconds = 2.0

                print(
                    f"HTTP 429. Waiting {wait_seconds} "
                    f"seconds before retry."
                )

                time.sleep(wait_seconds)
                continue

            if response.status_code in (500, 503):
                wait_seconds = 2 ** attempt

                print(
                    f"HTTP {response.status_code}. "
                    f"Waiting {wait_seconds} "
                    f"seconds before retry."
                )

                time.sleep(wait_seconds)
                continue

            if response.status_code in (400, 401, 404):
                return response

            return response

        except requests.exceptions.Timeout:
            wait_seconds = 2 ** attempt

            print(
                f"Request timeout. Waiting {wait_seconds} "
                f"seconds before retry."
            )

            time.sleep(wait_seconds)

        except requests.exceptions.RequestException as exc:
            wait_seconds = 2 ** attempt

            print(
                f"Request error: {exc}. "
                f"Waiting {wait_seconds} "
                f"seconds before retry."
            )

            time.sleep(wait_seconds)

    raise RuntimeError(
        "Maximum HTTP retry attempts exceeded"
    )


def parse_as_of(value):
    """Parse an ISO-8601 timestamp and normalize it to UTC."""

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            "Invalid --as-of timestamp. "
            "Use ISO-8601 format."
        ) from exc

    if parsed.tzinfo is None:
        raise ValueError(
            "--as-of must include a timezone."
        )

    return parsed.astimezone(timezone.utc)


def get_ist_date(as_of_utc):
    """Convert UTC timestamp to its IST calendar date."""

    return (
        as_of_utc
        .astimezone(IST)
        .date()
        .isoformat()
    )


def create_sweep(conn, as_of_utc):
    """Create the sweep metadata row."""

    as_of_text = (
        as_of_utc
        .isoformat()
        .replace("+00:00", "Z")
    )

    ist_date = get_ist_date(as_of_utc)

    started_at = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    conn.execute(
        """
        INSERT INTO sweeps (
            as_of,
            ist_date,
            started_at,
            finished_at
        )
        VALUES (?, ?, ?, NULL)

        ON CONFLICT(as_of) DO UPDATE SET
            ist_date = excluded.ist_date,
            started_at = excluded.started_at,
            finished_at = NULL
        """,
        (
            as_of_text,
            ist_date,
            started_at,
        ),
    )

    conn.commit()

    return as_of_text, ist_date


def fetch_inventory_page(store_id, as_of, cursor="0"):
    """Fetch one inventory page."""

    url = (
        f"{PORTAL}/v1/stores/"
        f"{store_id}/inventory"
    )

    response = safe_get(
        url,
        params={
            "as_of": as_of,
            "cursor": cursor,
        },
    )

    if response.status_code != 200:
        return (
            None,
            f"http_{response.status_code}",
        )

    try:
        body = response.json()
    except ValueError:
        return (
            None,
            "invalid_json",
        )

    return body, None


def fetch_inventory(store_id, as_of):
    """
    Fetch all inventory pages for one store.

    Returns:

        items, None

    when successful.

    Returns:

        None, reason

    when the store cannot be safely completed.
    """

    for soft_ban_round in range(
        MAX_SOFT_BAN_ROUNDS
    ):
        items_by_sku = {}
        cursor = "0"
        page_number = 0
        restart_store = False

        print(
            f"{store_id}: starting inventory fetch "
            f"(round {soft_ban_round + 1}/"
            f"{MAX_SOFT_BAN_ROUNDS})"
        )

        while True:
            page_number += 1

            if page_number > MAX_INVENTORY_PAGES:
                return (
                    None,
                    "inventory_page_limit_exceeded",
                )

            body, error = fetch_inventory_page(
                store_id,
                as_of,
                cursor,
            )

            if error:
                return None, error

            meta = body.get(
                "meta",
                {},
            )

            source = meta.get(
                "source",
                "origin",
            )

            # -----------------------------------------
            # SOFT BAN
            # -----------------------------------------
            if source != "origin":
                print(
                    f"{store_id}: soft ban detected "
                    f"(meta.source={source})"
                )

                restart_store = True
                break

            # -----------------------------------------
            # PARTIAL RESPONSE
            # -----------------------------------------
            if body.get("partial") is True:
                return (
                    None,
                    "partial_response",
                )

            # -----------------------------------------
            # COLLECT ITEMS
            # -----------------------------------------
            page_items = body.get(
                "items",
                [],
            )

            for item in page_items:
                sku_id = item.get("sku_id")

                if not sku_id:
                    continue

                # The same SKU can appear on more than
                # one page. Keep only one copy.
                if sku_id not in items_by_sku:
                    items_by_sku[sku_id] = item

            next_cursor = body.get(
                "next_cursor"
            )

            if next_cursor is None:
                break

            cursor = str(next_cursor)

        # ---------------------------------------------
        # RESTART AFTER SOFT BAN
        # ---------------------------------------------
        if restart_store:
            if (
                soft_ban_round
                == MAX_SOFT_BAN_ROUNDS - 1
            ):
                return (
                    None,
                    "soft_ban_persisted",
                )

            print(
                f"{store_id}: waiting "
                f"{SOFT_BAN_WAIT_SECONDS} seconds "
                f"before restarting from cursor 0."
            )

            time.sleep(
                SOFT_BAN_WAIT_SECONDS
            )

            continue

        return (
            list(items_by_sku.values()),
            None,
        )

    return (
        None,
        "soft_ban_persisted",
    )


def normalize_observed_at(value):
    """
    Convert an API timestamp to canonical UTC text.

    The API can return UTC or IST timestamps.
    """

    if not isinstance(value, str):
        raise ValueError(
            "observed_at must be a string"
        )

    parsed = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if parsed.tzinfo is None:
        raise ValueError(
            "observed_at must include a timezone"
        )

    parsed_utc = parsed.astimezone(
        timezone.utc
    )

    return (
        parsed_utc
        .isoformat()
        .replace("+00:00", "Z")
    )


def normalize_price(value):
    """
    Convert numeric or string prices into float.
    """

    if value is None:
        return None

    return float(value)


def normalize_item(item):
    """
    Validate and normalize one inventory item.
    """

    sku_id = item.get("sku_id")

    if not sku_id:
        raise ValueError(
            "Inventory item is missing sku_id"
        )

    name = item.get("name")

    if name is None:
        raise ValueError(
            f"{sku_id} is missing name"
        )

    if "in_stock" not in item:
        raise ValueError(
            f"{sku_id} is missing in_stock"
        )

    in_stock = bool(
        item["in_stock"]
    )

    qty = item.get("qty")

    if qty is not None:
        qty = int(qty)

    price = normalize_price(
        item.get("price")
    )

    observed_at = normalize_observed_at(
        item.get("observed_at")
    )

    return {
        "sku_id": sku_id,
        "name": name,
        "in_stock": int(in_stock),
        "qty": qty,
        "price": price,
        "observed_at": observed_at,
    }


def store_already_complete(
    conn,
    as_of,
    store_id,
):
    """
    Check whether this store already has a
    valid complete result for this sweep.
    """

    row = conn.execute(
        """
        SELECT status
        FROM store_sweeps
        WHERE as_of = ?
          AND store_id = ?
        """,
        (
            as_of,
            store_id,
        ),
    ).fetchone()

    return (
        row is not None
        and row[0] == "complete"
    )


def save_store_result(
    conn,
    as_of,
    store_id,
    items,
):
    """
    Save a successful store inventory result.

    The whole store is written inside one transaction.

    Existing observations for the same
    (as_of, store_id) are replaced so that
    rerunning the same sweep is idempotent.
    """

    fetched_at = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    try:
        conn.execute("BEGIN")

        # Remove old result for this exact store/sweep.
        conn.execute(
            """
            DELETE FROM observations
            WHERE as_of = ?
              AND store_id = ?
            """,
            (
                as_of,
                store_id,
            ),
        )

        conn.execute(
            """
            DELETE FROM store_sweeps
            WHERE as_of = ?
              AND store_id = ?
            """,
            (
                as_of,
                store_id,
            ),
        )

        for raw_item in items:
            item = normalize_item(
                raw_item
            )

            conn.execute(
                """
                INSERT INTO observations (
                    as_of,
                    store_id,
                    sku_id,
                    name,
                    in_stock,
                    qty,
                    price,
                    observed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    as_of,
                    store_id,
                    item["sku_id"],
                    item["name"],
                    item["in_stock"],
                    item["qty"],
                    item["price"],
                    item["observed_at"],
                ),
            )

        conn.execute(
            """
            INSERT INTO store_sweeps (
                as_of,
                store_id,
                status,
                reason,
                item_count,
                fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                as_of,
                store_id,
                "complete",
                None,
                len(items),
                fetched_at,
            ),
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise


def save_incomplete_store(
    conn,
    as_of,
    store_id,
    reason,
):
    """
    Record that a store could not be safely
    completed.

    We do NOT create fake observations.
    """

    fetched_at = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    # If a valid complete result already exists,
    # never replace it with a worse incomplete result.
    if store_already_complete(
        conn,
        as_of,
        store_id,
    ):
        print(
            f"{store_id}: existing complete data "
            f"kept; not replacing with incomplete result."
        )
        return

    conn.execute(
        """
        DELETE FROM observations
        WHERE as_of = ?
          AND store_id = ?
        """,
        (
            as_of,
            store_id,
        ),
    )

    conn.execute(
        """
        INSERT INTO store_sweeps (
            as_of,
            store_id,
            status,
            reason,
            item_count,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?)

        ON CONFLICT(as_of, store_id)
        DO UPDATE SET
            status = excluded.status,
            reason = excluded.reason,
            item_count = excluded.item_count,
            fetched_at = excluded.fetched_at
        """,
        (
            as_of,
            store_id,
            "incomplete",
            reason,
            0,
            fetched_at,
        ),
    )

    conn.commit()


def fetch_all_stores():
    """Fetch every store page."""

    stores = []
    page = 1

    while True:
        response = safe_get(
            f"{PORTAL}/v1/stores",
            params={"page": page},
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Could not fetch store page {page}: "
                f"HTTP {response.status_code}"
            )

        body = response.json()

        stores.extend(
            body.get("stores", [])
        )

        next_page = body.get(
            "next_page"
        )

        if next_page is None:
            break

        page = next_page

    return stores


def save_stores(conn, stores):
    """Save the complete store roster."""

    for store in stores:
        conn.execute(
            """
            INSERT INTO stores (
                store_id,
                city,
                name,
                is_active,
                is_serviceable
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(store_id) DO UPDATE SET
                city = excluded.city,
                name = excluded.name,
                is_active = excluded.is_active,
                is_serviceable =
                    excluded.is_serviceable
            """,
            (
                store["store_id"],
                store["city"],
                store.get("name"),
                int(store["is_active"]),
                int(store["is_serviceable"]),
            ),
        )

    conn.commit()


def get_tracked_stores(conn):
    """Return active stores."""

    return conn.execute(
        """
        SELECT
            store_id,
            city,
            name,
            is_active,
            is_serviceable
        FROM stores
        WHERE is_active = 1
        ORDER BY store_id
        """
    ).fetchall()


def init_db():
    """Create the required SQLite tables."""

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS stores (
            store_id TEXT PRIMARY KEY,
            city TEXT NOT NULL,
            name TEXT,
            is_active INTEGER NOT NULL,
            is_serviceable INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sweeps (
            as_of TEXT PRIMARY KEY,
            ist_date TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS store_sweeps (
            as_of TEXT NOT NULL,
            store_id TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            item_count INTEGER NOT NULL DEFAULT 0,
            fetched_at TEXT,
            PRIMARY KEY (as_of, store_id),
            FOREIGN KEY (as_of)
                REFERENCES sweeps(as_of),
            FOREIGN KEY (store_id)
                REFERENCES stores(store_id)
        );

        CREATE TABLE IF NOT EXISTS observations (
            as_of TEXT NOT NULL,
            store_id TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            name TEXT NOT NULL,
            in_stock INTEGER NOT NULL,
            qty INTEGER,
            price REAL,
            observed_at TEXT NOT NULL,
            PRIMARY KEY (
                as_of,
                store_id,
                sku_id
            ),
            FOREIGN KEY (as_of)
                REFERENCES sweeps(as_of),
            FOREIGN KEY (store_id)
                REFERENCES stores(store_id)
        );
        """
    )

    conn.commit()
    conn.close()


def finish_sweep(conn, as_of):
    """Mark the sweep as finished."""

    finished_at = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    conn.execute(
        """
        UPDATE sweeps
        SET finished_at = ?
        WHERE as_of = ?
        """,
        (
            finished_at,
            as_of,
        ),
    )

    conn.commit()


def print_summary(
    conn,
    as_of,
    tracked_stores,
):
    """Print a simple sweep summary."""

    total = len(tracked_stores)

    complete = conn.execute(
        """
        SELECT COUNT(*)
        FROM store_sweeps
        WHERE as_of = ?
          AND status = 'complete'
        """,
        (as_of,),
    ).fetchone()[0]

    incomplete = conn.execute(
        """
        SELECT COUNT(*)
        FROM store_sweeps
        WHERE as_of = ?
          AND status = 'incomplete'
        """,
        (as_of,),
    ).fetchone()[0]

    observations = conn.execute(
        """
        SELECT COUNT(*)
        FROM observations
        WHERE as_of = ?
        """,
        (as_of,),
    ).fetchone()[0]

    print()
    print("========== SWEEP SUMMARY ==========")
    print(f"As-of: {as_of}")
    print(f"Expected stores: {total}")
    print(f"Complete stores: {complete}")
    print(f"Incomplete stores: {incomplete}")
    print(f"Observations: {observations}")
    print("===================================")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--as-of",
        required=True,
        help=(
            "UTC/ISO-8601 inventory "
            "snapshot timestamp"
        ),
    )

    args = parser.parse_args()

    as_of_utc = parse_as_of(
        args.as_of
    )

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    stores = fetch_all_stores()

    save_stores(
        conn,
        stores,
    )

    tracked_stores = get_tracked_stores(
        conn
    )

    as_of_text, ist_date = create_sweep(
        conn,
        as_of_utc,
    )

    print(
        f"Fetched {len(stores)} stores."
    )

    print(
        f"Tracking "
        f"{len(tracked_stores)} active stores."
    )

    print(
        f"Sweep as_of: {as_of_text}"
    )

    print(
        f"IST date: {ist_date}"
    )

    for store in tracked_stores:
        store_id = store[0]

        items, error = fetch_inventory(
            store_id,
            as_of_text,
        )

        if error:
            print(
                f"{store_id}: "
                f"INCOMPLETE - {error}"
            )

            save_incomplete_store(
                conn,
                as_of_text,
                store_id,
                error,
            )

            continue

        try:
            save_store_result(
                conn,
                as_of_text,
                store_id,
                items,
            )

            print(
                f"{store_id}: "
                f"{len(items)} unique products "
                f"saved"
            )

        except Exception as exc:
            print(
                f"{store_id}: "
                f"INCOMPLETE - database error: "
                f"{exc}"
            )

            save_incomplete_store(
                conn,
                as_of_text,
                store_id,
                f"database_error: {exc}",
            )

    finish_sweep(
        conn,
        as_of_text,
    )

    print_summary(
        conn,
        as_of_text,
        tracked_stores,
    )

    conn.close()


if __name__ == "__main__":
    init_db()
    main()