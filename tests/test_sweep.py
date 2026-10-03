# pyrefly: ignore [missing-import]
import sqlite3

import pytest

import sweep


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
            started_at TEXT NOT NULL,
            finished_at TEXT
        );

        CREATE TABLE store_sweeps (
            as_of TEXT NOT NULL,
            store_id TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            item_count INTEGER NOT NULL DEFAULT 0,
            fetched_at TEXT,
            PRIMARY KEY (as_of, store_id),
            FOREIGN KEY (as_of) REFERENCES sweeps(as_of),
            FOREIGN KEY (store_id) REFERENCES stores(store_id)
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
            PRIMARY KEY (as_of, store_id, sku_id),
            FOREIGN KEY (as_of) REFERENCES sweeps(as_of),
            FOREIGN KEY (store_id) REFERENCES stores(store_id)
        );
        """
    )

    return conn


def add_store(conn, store_id, active=1, serviceable=1):
    conn.execute(
        """
        INSERT INTO stores (
            store_id, city, name, is_active, is_serviceable
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            store_id,
            "Mumbai",
            store_id,
            active,
            serviceable,
        ),
    )
    conn.commit()

def add_sweep(conn, as_of):
    conn.execute(
        """
        INSERT INTO sweeps (
            as_of, ist_date, started_at, finished_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            as_of,
            "2026-09-28",
            "2026-09-28T00:00:00Z",
            None,
        ),
    )
    conn.commit()

def test_parse_as_of_requires_timezone():
    with pytest.raises(ValueError, match="must include a timezone"):
        sweep.parse_as_of("2026-09-28T04:30:00")


def test_parse_as_of_normalizes_to_utc():
    result = sweep.parse_as_of(
        "2026-09-28T10:00:00+05:30"
    )

    assert result.isoformat() == "2026-09-28T04:30:00+00:00"


def test_utc_timestamp_maps_to_correct_ist_date():
    as_of = sweep.parse_as_of(
        "2026-09-27T19:00:00Z"
    )

    assert sweep.get_ist_date(as_of) == "2026-09-28"


def test_observed_at_utc_is_normalized():
    result = sweep.normalize_observed_at(
        "2026-09-28T04:30:00Z"
    )

    assert result == "2026-09-28T04:30:00Z"


def test_observed_at_ist_is_converted_to_utc():
    result = sweep.normalize_observed_at(
        "2026-09-28T10:00:00+05:30"
    )

    assert result == "2026-09-28T04:30:00Z"


def test_timezone_less_observed_at_is_rejected():
    with pytest.raises(
        ValueError,
        match="must include a timezone",
    ):
        sweep.normalize_observed_at(
            "2026-09-28T04:30:00"
        )


def test_price_normalization_accepts_string():
    assert sweep.normalize_price("42.50") == 42.50


def test_price_normalization_accepts_number():
    assert sweep.normalize_price(42.50) == 42.50


def test_normalize_item_uses_in_stock():
    item = {
        "sku_id": "SKU-0001",
        "name": "Milk",
        "in_stock": True,
        "qty": 0,
        "price": "45.50",
        "observed_at": "2026-09-28T04:30:00Z",
    }

    result = sweep.normalize_item(item)

    assert result["sku_id"] == "SKU-0001"
    assert result["in_stock"] == 1
    assert result["qty"] == 0
    assert result["price"] == 45.50
    assert result["observed_at"] == "2026-09-28T04:30:00Z"


def test_normalize_item_requires_sku_id():
    item = {
        "name": "Milk",
        "in_stock": True,
        "qty": 1,
        "price": 45,
        "observed_at": "2026-09-28T04:30:00Z",
    }

    with pytest.raises(ValueError, match="missing sku_id"):
        sweep.normalize_item(item)


def test_fetch_inventory_deduplicates_skus(monkeypatch):
    responses = [
        (
            {
                "items": [
                    {
                        "sku_id": "SKU-001",
                        "name": "Milk",
                    },
                    {
                        "sku_id": "SKU-002",
                        "name": "Bread",
                    },
                ],
                "next_cursor": "15",
                "partial": False,
                "meta": {"source": "origin"},
            },
            None,
        ),
        (
            {
                "items": [
                    {
                        "sku_id": "SKU-002",
                        "name": "Bread",
                    },
                    {
                        "sku_id": "SKU-003",
                        "name": "Rice",
                    },
                ],
                "next_cursor": None,
                "partial": False,
                "meta": {"source": "origin"},
            },
            None,
        ),
    ]

    def fake_fetch_inventory_page(
        store_id,
        as_of,
        cursor,
    ):
        return responses.pop(0)

    monkeypatch.setattr(
        sweep,
        "fetch_inventory_page",
        fake_fetch_inventory_page,
    )

    items, error = sweep.fetch_inventory(
        "MUM-001",
        "2026-09-28T04:30:00Z",
    )

    assert error is None
    assert len(items) == 3
    assert {
        item["sku_id"]
        for item in items
    } == {
        "SKU-001",
        "SKU-002",
        "SKU-003",
    }


def test_fetch_inventory_rejects_partial_response(
    monkeypatch,
):
    def fake_fetch_inventory_page(
        store_id,
        as_of,
        cursor,
    ):
        return (
            {
                "items": [],
                "next_cursor": None,
                "partial": True,
                "meta": {"source": "origin"},
            },
            None,
        )

    monkeypatch.setattr(
        sweep,
        "fetch_inventory_page",
        fake_fetch_inventory_page,
    )

    items, error = sweep.fetch_inventory(
        "DEL-004",
        "2026-09-28T10:30:00Z",
    )

    assert items is None
    assert error == "partial_response"


def test_fetch_inventory_detects_soft_ban(
    monkeypatch,
):
    responses = [
        (
            {
                "items": [],
                "next_cursor": None,
                "partial": False,
                "meta": {"source": "edge"},
            },
            None,
        ),
        (
            {
                "items": [],
                "next_cursor": None,
                "partial": False,
                "meta": {"source": "edge"},
            },
            None,
        ),
        (
            {
                "items": [],
                "next_cursor": None,
                "partial": False,
                "meta": {"source": "edge"},
            },
            None,
        ),
    ]

    def fake_fetch_inventory_page(
        store_id,
        as_of,
        cursor,
    ):
        return responses.pop(0)

    sleep_calls = []

    def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        sweep,
        "fetch_inventory_page",
        fake_fetch_inventory_page,
    )

    monkeypatch.setattr(
        sweep.time,
        "sleep",
        fake_sleep,
    )

    items, error = sweep.fetch_inventory(
        "MUM-001",
        "2026-09-28T04:30:00Z",
    )

    assert items is None
    assert error == "soft_ban_persisted"
    assert sleep_calls == [
        sweep.SOFT_BAN_WAIT_SECONDS,
        sweep.SOFT_BAN_WAIT_SECONDS,
    ]


def test_save_store_result_is_idempotent():
    conn = create_database()

    add_store(conn, "MUM-001")

    as_of = "2026-09-28T04:30:00Z"
    add_sweep(conn, as_of)

    items = [
        {
            "sku_id": "SKU-0001",
            "name": "Milk",
            "in_stock": True,
            "qty": 1,
            "price": 40,
            "observed_at": "2026-09-28T04:30:00Z",
        },
        {
            "sku_id": "SKU-0002",
            "name": "Bread",
            "in_stock": False,
            "qty": 0,
            "price": 30,
            "observed_at": "2026-09-28T04:30:00Z",
        },
    ]

    sweep.save_store_result(
        conn,
        as_of,
        "MUM-001",
        items,
    )

    first_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM observations
        WHERE as_of = ?
          AND store_id = ?
        """,
        (as_of, "MUM-001"),
    ).fetchone()[0]

    sweep.save_store_result(
        conn,
        as_of,
        "MUM-001",
        items,
    )

    second_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM observations
        WHERE as_of = ?
          AND store_id = ?
        """,
        (as_of, "MUM-001"),
    ).fetchone()[0]

    assert first_count == 2
    assert second_count == 2

    status = conn.execute(
        """
        SELECT status
        FROM store_sweeps
        WHERE as_of = ?
          AND store_id = ?
        """,
        (as_of, "MUM-001"),
    ).fetchone()[0]

    assert status == "complete"

    conn.close()


def test_incomplete_store_creates_no_observations():
    conn = create_database()

    add_store(conn, "DEL-004")

    as_of = "2026-09-28T10:30:00Z"
    add_sweep(conn, as_of)

    sweep.save_incomplete_store(
        conn,
        as_of,
        "DEL-004",
        "partial_response",
    )

    observation_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM observations
        WHERE as_of = ?
          AND store_id = ?
        """,
        (as_of, "DEL-004"),
    ).fetchone()[0]

    assert observation_count == 0

    row = conn.execute(
        """
        SELECT status, reason, item_count
        FROM store_sweeps
        WHERE as_of = ?
          AND store_id = ?
        """,
        (as_of, "DEL-004"),
    ).fetchone()

    assert row["status"] == "incomplete"
    assert row["reason"] == "partial_response"
    assert row["item_count"] == 0

    conn.close()


def test_existing_complete_store_is_not_replaced_by_incomplete():
    conn = create_database()

    add_store(conn, "MUM-001")

    as_of = "2026-09-28T04:30:00Z"
    add_sweep(conn, as_of)

    items = [
        {
            "sku_id": "SKU-0001",
            "name": "Milk",
            "in_stock": True,
            "qty": 1,
            "price": 40,
            "observed_at": "2026-09-28T04:30:00Z",
        }
    ]

    sweep.save_store_result(
        conn,
        as_of,
        "MUM-001",
        items,
    )

    sweep.save_incomplete_store(
        conn,
        as_of,
        "MUM-001",
        "partial_response",
    )

    status = conn.execute(
        """
        SELECT status
        FROM store_sweeps
        WHERE as_of = ?
          AND store_id = ?
        """,
        (as_of, "MUM-001"),
    ).fetchone()[0]

    observation_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM observations
        WHERE as_of = ?
          AND store_id = ?
        """,
        (as_of, "MUM-001"),
    ).fetchone()[0]

    assert status == "complete"
    assert observation_count == 1

    conn.close()


def test_get_tracked_stores_returns_only_active_stores():
    conn = create_database()

    add_store(
        conn,
        "MUM-001",
        active=1,
        serviceable=1,
    )

    add_store(
        conn,
        "MUM-009",
        active=0,
        serviceable=1,
    )

    add_store(
        conn,
        "DEL-006",
        active=1,
        serviceable=0,
    )

    conn.commit()

    stores = sweep.get_tracked_stores(conn)

    store_ids = [
        row["store_id"]
        for row in stores
    ]

    assert "MUM-001" in store_ids
    assert "DEL-006" in store_ids
    assert "MUM-009" not in store_ids

    conn.close()