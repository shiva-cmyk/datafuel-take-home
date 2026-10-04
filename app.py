from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import sqlite3

from fastapi import FastAPI, HTTPException, Query


DB_PATH = "osa.db"
IST = ZoneInfo("Asia/Kolkata")

VALID_CITIES = {"Mumbai", "Delhi", "Bengaluru"}

app = FastAPI(title="QuickMart OSA API")


def get_connection():
    """Open a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_yesterday_ist():
    """Return yesterday's date according to IST."""
    return (datetime.now(IST).date() - timedelta(days=1)).isoformat()


def validate_date(value):
    """Validate a date in YYYY-MM-DD format."""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="date must be in YYYY-MM-DD format",
        )

    return parsed.isoformat()


def get_incomplete_store_sweeps(
    conn,
    expected_store_ids,
    sweep_times,
):
    """
    Find every incomplete store-sweep.

    Each incomplete record includes:
    - store_id
    - sweep
    - reason
    """

    incomplete = []

    for store_id in expected_store_ids:
        for sweep_time in sweep_times:

            row = conn.execute(
                """
                SELECT status, reason
                FROM store_sweeps
                WHERE as_of = ?
                  AND store_id = ?
                """,
                (sweep_time, store_id),
            ).fetchone()

            if row is None:
                incomplete.append(
                    {
                        "store_id": store_id,
                        "sweep": sweep_time,
                        "reason": "no_record",
                    }
                )

            elif row["status"] != "complete":
                incomplete.append(
                    {
                        "store_id": store_id,
                        "sweep": sweep_time,
                        "reason": row["reason"] or "incomplete",
                    }
                )

    return incomplete


def get_complete_store_sweeps(
    conn,
    expected_store_ids,
    sweep_times,
):
    """
    Return individual complete store-sweep pairs.

    Example:

    DEL-004 + 04:30 -> complete
    DEL-004 + 10:30 -> incomplete
    DEL-004 + 18:40 -> complete

    Only the two complete pairs are returned.
    """

    if not expected_store_ids or not sweep_times:
        return set()

    store_placeholders = ",".join(
        "?" for _ in expected_store_ids
    )

    sweep_placeholders = ",".join(
        "?" for _ in sweep_times
    )

    rows = conn.execute(
        f"""
        SELECT as_of, store_id
        FROM store_sweeps
        WHERE status = 'complete'
          AND store_id IN ({store_placeholders})
          AND as_of IN ({sweep_placeholders})
        """,
        expected_store_ids + sweep_times,
    ).fetchall()

    return {
        (row["as_of"], row["store_id"])
        for row in rows
    }


def calculate_sku_results(
    observations,
):
    """
    Calculate per-SKU observation counts.

    Product identity is SKU ID.

    The latest observation's name is used as the
    current name for that SKU.
    """

    sku_data = {}

    for row in observations:

        sku_id = row["sku_id"]

        if sku_id not in sku_data:
            sku_data[sku_id] = {
                "sku_id": sku_id,
                "name": row["name"],
                "observations": 0,
                "in_stock": 0,
                "latest_as_of": row["as_of"],
            }

        # Use the newest sweep's product name.
        if row["as_of"] > sku_data[sku_id]["latest_as_of"]:
            sku_data[sku_id]["name"] = row["name"]
            sku_data[sku_id]["latest_as_of"] = row["as_of"]

        sku_data[sku_id]["observations"] += 1

        if row["in_stock"] == 1:
            sku_data[sku_id]["in_stock"] += 1

    results = []

    for data in sku_data.values():

        observations_count = data["observations"]
        in_stock_count = data["in_stock"]

        sku_osa = round(
            (
                in_stock_count
                / observations_count
            ) * 100,
            2,
        )

        results.append(
            {
                "sku_id": data["sku_id"],
                "name": data["name"],
                "observations": observations_count,
                "in_stock": in_stock_count,
                "osa_pct": sku_osa,
            }
        )

    results.sort(
        key=lambda item: item["sku_id"]
    )

    return results


def calculate_osa(conn, city, day):
    """
    Calculate city-level OSA.

    OSA = total in_stock observations
          / total observations * 100

    Only complete store-sweeps are used.
    """

    # ---------------------------------------------------------
    # 1. Find expected active stores in this city.
    # ---------------------------------------------------------

    expected_rows = conn.execute(
        """
        SELECT store_id
        FROM stores
        WHERE city = ?
          AND is_active = 1
        ORDER BY store_id
        """,
        (city,),
    ).fetchall()

    expected_store_ids = [
        row["store_id"]
        for row in expected_rows
    ]

    # ---------------------------------------------------------
    # 2. Find sweeps belonging to this IST calendar day.
    # ---------------------------------------------------------

    sweep_rows = conn.execute(
        """
        SELECT as_of
        FROM sweeps
        WHERE ist_date = ?
        ORDER BY as_of
        """,
        (day,),
    ).fetchall()

    sweep_times = [
        row["as_of"]
        for row in sweep_rows
    ]

    # ---------------------------------------------------------
    # 3. No sweep data means no_data.
    # ---------------------------------------------------------

    if not sweep_times:

        return {
            "status": "no_data",
            "city": city,
            "date": day,
            "osa_pct": None,
            "observations": 0,
            "coverage": {
                "stores_expected": len(
                    expected_store_ids
                ),
                "stores_complete": 0,
                "incomplete": [
                    {
                        "store_id": store_id,
                        "sweep": None,
                        "reason": "no_sweep_data",
                    }
                    for store_id in expected_store_ids
                ],
            },
            "skus": [],
        }

    # ---------------------------------------------------------
    # 4. Find incomplete store-sweeps.
    # ---------------------------------------------------------

    incomplete = get_incomplete_store_sweeps(
        conn,
        expected_store_ids,
        sweep_times,
    )

    # ---------------------------------------------------------
    # 5. Find complete store-sweep pairs.
    # ---------------------------------------------------------

    complete_pairs = get_complete_store_sweeps(
        conn,
        expected_store_ids,
        sweep_times,
    )

    # ---------------------------------------------------------
    # 6. Determine which stores have at least one
    #    complete store-sweep.
    #
    #    A store is counted as "complete" when it has
    #    at least one usable store-sweep for the day.
    # ---------------------------------------------------------

    complete_store_ids = sorted(
        {
            store_id
            for sweep_time, store_id
            in complete_pairs
        }
    )

    # ---------------------------------------------------------
    # 7. If there are no usable store-sweeps,
    #    return no_data.
    # ---------------------------------------------------------

    if not complete_pairs:

        return {
            "status": "no_data",
            "city": city,
            "date": day,
            "osa_pct": None,
            "observations": 0,
            "coverage": {
                "stores_expected": len(
                    expected_store_ids
                ),
                "stores_complete": 0,
                "incomplete": incomplete,
            },
            "skus": [],
        }

    # ---------------------------------------------------------
    # 8. Build SQL conditions for only COMPLETE
    #    store-sweep pairs.
    # ---------------------------------------------------------

    pair_conditions = []
    pair_parameters = []

    for sweep_time, store_id in complete_pairs:

        pair_conditions.append(
            "(as_of = ? AND store_id = ?)"
        )

        pair_parameters.extend(
            [sweep_time, store_id]
        )

    pair_where = " OR ".join(
        pair_conditions
    )

    # ---------------------------------------------------------
    # 9. Read observations from only those complete
    #    store-sweep pairs.
    # ---------------------------------------------------------

    observations = conn.execute(
        f"""
        SELECT
            as_of,
            store_id,
            sku_id,
            name,
            in_stock
        FROM observations
        WHERE {pair_where}
        ORDER BY as_of, store_id, sku_id
        """,
        pair_parameters,
    ).fetchall()

    total_observations = len(observations)

    # ---------------------------------------------------------
    # 10. No observations means no_data.
    # ---------------------------------------------------------

    if total_observations == 0:

        return {
            "status": "no_data",
            "city": city,
            "date": day,
            "osa_pct": None,
            "observations": 0,
            "coverage": {
                "stores_expected": len(
                    expected_store_ids
                ),
                "stores_complete": len(
                    complete_store_ids
                ),
                "incomplete": incomplete,
            },
            "skus": [],
        }

    # ---------------------------------------------------------
    # 11. Calculate total in-stock observations.
    #
    # IMPORTANT:
    # Use in_stock, NOT qty.
    # ---------------------------------------------------------

    in_stock_observations = sum(
        1
        for row in observations
        if row["in_stock"] == 1
    )

    # ---------------------------------------------------------
    # 12. Calculate weighted city OSA.
    #
    # DO NOT average store percentages.
    # ---------------------------------------------------------

    osa_pct = round(
        (
            in_stock_observations
            / total_observations
        ) * 100,
        2,
    )

    # ---------------------------------------------------------
    # 13. Calculate per-SKU results.
    # ---------------------------------------------------------

    skus = calculate_sku_results(
        observations
    )

    # ---------------------------------------------------------
    # 14. Return final report.
    # ---------------------------------------------------------

    return {
        "status": "ok",
        "city": city,
        "date": day,
        "osa_pct": osa_pct,
        "observations": total_observations,
        "coverage": {
            "stores_expected": len(
                expected_store_ids
            ),
            "stores_complete": len(
                complete_store_ids
            ),
            "incomplete": incomplete,
        },
        "skus": skus,
    }


@app.get("/osa")
def get_osa(
    city: str = Query(...),
    date_value: str | None = Query(
        None,
        alias="date",
    ),
):
    """
    GET /osa?city=Mumbai&date=2026-09-28
    """

    # Validate city.
    if city not in VALID_CITIES:
        raise HTTPException(
            status_code=400,
            detail="invalid city",
        )

    # If date is missing, use yesterday in IST.
    if date_value is None:
        requested_day = get_yesterday_ist()
    else:
        requested_day = validate_date(
            date_value
        )

    conn = get_connection()

    try:
        return calculate_osa(
            conn,
            city,
            requested_day,
        )
    finally:
        conn.close()


@app.get("/health")
def health():
    """Health check for the OSA application."""

    return {
        "ok": True
    }


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
    )