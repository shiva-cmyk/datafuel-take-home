
import sqlite3

from app import calculate_osa
from sweep import get_ist_date, parse_as_of

def create_database():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.executescript(
        """
        CREATE TABLE stores (
            store_id TEXT PRIMARY KEY,
            city TEXT NOT NULL,
            name TEXT,
            is_active INTEGER NOT NULL,
            is_serviceable INTEGER NOT NULL
        );

        CREATE TABLE sweeps (
            as_of TEXT PRIMARY KEY,
            ist_date TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        );

        CREATE TABLE store_sweeps (
            as_of TEXT NOT NULL,
            store_id TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            item_count INTEGER NOT NULL,
            fetched_at TEXT,
            PRIMARY KEY (as_of, store_id)
        );

        CREATE TABLE observations (
            as_of TEXT NOT NULL,
            store_id TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            name TEXT NOT NULL,
            in_stock INTEGER NOT NULL,
            qty INTEGER,
            price REAL,
            observed_at TEXT NOT NULL,
            PRIMARY KEY (as_of, store_id, sku_id)
        );
        """
    )

    return conn


def add_complete_store(conn, store_id, city="Mumbai"):
    conn.execute(
        """
        INSERT INTO stores (
            store_id, city, name, is_active, is_serviceable
        )
        VALUES (?, ?, ?, 1, 1)
        """,
        (store_id, city, store_id),
    )


def add_sweep(conn, as_of, ist_date):
    conn.execute(
        """
        INSERT INTO sweeps (
            as_of, ist_date, started_at, finished_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            as_of,
            ist_date,
            "2026-10-03T00:00:00Z",
            "2026-10-03T00:01:00Z",
        ),
    )


def add_store_sweep(conn, as_of, store_id, status="complete", reason=None):
    conn.execute(
        """
        INSERT INTO store_sweeps (
            as_of, store_id, status, reason, item_count, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            as_of,
            store_id,
            status,
            reason,
            0,
            "2026-10-03T00:01:00Z",
        ),
    )


def add_observation(
    conn,
    as_of,
    store_id,
    sku_id,
    in_stock,
):
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
            sku_id,
            sku_id,
            in_stock,
            1 if in_stock else 0,
            10.0,
            "2026-09-28T04:30:00Z",
        ),
    )


def test_weighted_city_osa():
    """
    OSA must use total in-stock observations / total observations.

    Store A: 9/10
    Store B: 1/2

    Correct:
    10/12 = 83.33%

    Incorrect store-percentage average:
    (90% + 50%) / 2 = 70%
    """

    conn = create_database()

    add_complete_store(conn, "MUM-001")
    add_complete_store(conn, "MUM-002")

    as_of = "2026-09-27T19:00:00Z"
    add_sweep(conn, as_of, "2026-09-28")

    add_store_sweep(conn, as_of, "MUM-001")
    add_store_sweep(conn, as_of, "MUM-002")

    for i in range(10):
        add_observation(
            conn,
            as_of,
            "MUM-001",
            f"SKU-A-{i}",
            i < 9,
        )

    for i in range(2):
        add_observation(
            conn,
            as_of,
            "MUM-002",
            f"SKU-B-{i}",
            i < 1,
        )

    conn.commit()

    result = calculate_osa(
        conn,
        "Mumbai",
        "2026-09-28",
    )

    assert result["status"] == "ok"
    assert result["osa_pct"] == 83.33

    conn.close()


def test_ghost_stock_uses_in_stock_not_qty():
    """
    A product can have:
        in_stock = 1
        qty = 0

    OSA must use in_stock because that is the official
    availability field from QuickMart.
    """

    conn = create_database()

    add_complete_store(conn, "MUM-001")

    as_of = "2026-09-27T19:00:00Z"
    add_sweep(conn, as_of, "2026-09-28")
    add_store_sweep(conn, as_of, "MUM-001")

    add_observation(
        conn,
        as_of,
        "MUM-001",
        "SKU-0001",
        1,
    )

    conn.commit()

    result = calculate_osa(
        conn,
        "Mumbai",
        "2026-09-28",
    )

    assert result["status"] == "ok"
    assert result["osa_pct"] == 100.0

    conn.close()


def test_incomplete_store_is_excluded_from_osa():
    """
    An incomplete store must not contribute fake out-of-stock
    observations to the OSA calculation.
    """

    conn = create_database()

    add_complete_store(conn, "MUM-001")
    add_complete_store(conn, "MUM-002")

    as_of = "2026-09-27T19:00:00Z"
    add_sweep(conn, as_of, "2026-09-28")

    add_store_sweep(conn, as_of, "MUM-001", "complete")
    add_store_sweep(
        conn,
        as_of,
        "MUM-002",
        "incomplete",
        "partial_response",
    )

    add_observation(
        conn,
        as_of,
        "MUM-001",
        "SKU-0001",
        1,
    )

    conn.commit()

    result = calculate_osa(
        conn,
        "Mumbai",
        "2026-09-28",
    )

    assert result["status"] == "ok"
    assert result["osa_pct"] == 100.0
    assert result["coverage"]["stores_expected"] == 2
    assert result["coverage"]["stores_complete"] == 1
    assert result["coverage"]["incomplete"] == [
    {
        "store_id": "MUM-002",
        "sweep": "2026-09-27T19:00:00Z",
        "reason": "partial_response",
    }
]
   
    conn.close()


def test_no_data_does_not_become_zero_percent():

    """
    No observations must return no_data with osa_pct=None.
    It must never return 0%.
    """

    conn = create_database()

    add_complete_store(conn, "MUM-001")

    as_of = "2026-09-27T19:00:00Z"
    add_sweep(conn, as_of, "2026-09-28")
    add_store_sweep(conn, as_of, "MUM-001")

    conn.commit()

    result = calculate_osa(
        conn,
        "Mumbai",
        "2026-09-28",
    )

    assert result["status"] == "no_data"
    assert result["osa_pct"] is None

    conn.close()
def test_sweep_crossing_utc_day_maps_to_correct_ist_day():
    """
    2026-09-27T19:00:00Z is already September 28 in IST.
    """

    as_of = parse_as_of("2026-09-27T19:00:00Z")

    assert get_ist_date(as_of) == "2026-09-28"
def test_duplicate_observation_is_rejected():
    """
    The database primary key must prevent the same observation
    from being inserted twice.
    """

    conn = create_database()

    as_of = "2026-09-27T19:00:00Z"

    add_observation(
        conn,
        as_of,
        "MUM-001",
        "SKU-0001",
        1,
    )

    conn.commit()

    try:
        add_observation(
            conn,
            as_of,
            "MUM-001",
            "SKU-0001",
            1,
        )
        conn.commit()

        assert False, "Duplicate observation was accepted"

    except sqlite3.IntegrityError:
        conn.rollback()

    conn.close()
