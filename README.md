# DataFuel Backend Engineer Take-Home

## Overview

This project implements the DataFuel Backend Engineer take-home assignment.

The project has two main responsibilities:

1. Collect inventory data reliably from the provided QuickMart mock API using `sweep.py`.
2. Provide a FastAPI endpoint, `GET /osa`, that calculates On-Shelf Availability (OSA) for a city and IST calendar day.

The main principle of the implementation is:

> Wrong data is worse than no data.

Therefore, incomplete or unreliable inventory data is not converted into out-of-stock observations.

---

# 1. Problem Being Solved

Quick-commerce platforms contain inventory information for many stores and products.

DataFuel needs to collect this information reliably and answer:

> What percentage of the time was inventory in stock in a particular city on a particular day?

The QuickMart server intentionally behaves like an unreliable real-world API. It can return:

* HTTP 429 rate limits
* HTTP 500 errors
* HTTP 503 errors
* slow requests
* partial responses
* missing data
* duplicate products
* mixed timestamp formats
* soft-banned responses
* different price types
* different store states

The scraper therefore has to collect data carefully and record when a store could not be completely collected.

---

# 2. Project Structure

```text
datafuel-take-home/
│
├── README.md
├── API.md
├── mock_portal.py
├── sweep.py
├── app.py
├── review_me.py
├── REVIEW.md
├── NOTES.md
├── AI_LOG.md
├── RECORDING.md
├── requirements.txt
├── .gitignore
├── pytest.ini
├── osa.db                 # local SQLite database, not committed
│
└── tests/
    ├── test_osa.py
    └── test_sweep.py
```

### Important files

| File                  | Purpose                                                                                 |
| --------------------- | --------------------------------------------------------------------------------------- |
| `mock_portal.py`      | Company-provided QuickMart mock server. It must not be modified.                        |
| `API.md`              | Company-provided API contract.                                                          |
| `sweep.py`            | Fetches stores and inventory and stores reliable observations in SQLite.                |
| `app.py`              | FastAPI application that reads the database and calculates OSA.                         |
| `review_me.py`        | Provided intentionally problematic code with only the requested targeted fixes.         |
| `REVIEW.md`           | Code review containing real problems found in `review_me.py`.                           |
| `NOTES.md`            | Implementation decisions, observations, edge cases and answers to assignment questions. |
| `AI_LOG.md`           | Records AI usage and mistakes that were caught through verification.                    |
| `RECORDING.md`        | Screen-recording information and final recording links.                                 |
| `tests/test_sweep.py` | Tests scraper reliability and normalization behavior.                                   |
| `tests/test_osa.py`   | Tests OSA calculations and wrong-number cases.                                          |
| `osa.db`              | Local SQLite database created by the implementation.                                    |
| `.gitignore`          | Prevents local environment, cache and database files from being committed.              |

---

# 3. Requirements

* Python 3.10+
* `requests`
* `fastapi`
* `uvicorn`
* `pytest`

The project was implemented and tested using Python 3.10.8.

---

# 4. Setup

Create a virtual environment:

### Windows

```powershell
python -m venv datafuel_env
.\datafuel_env\Scripts\Activate.ps1
```

### Linux/macOS

```bash
python3 -m venv datafuel_env
source datafuel_env/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

# 5. Start the QuickMart Mock API

The company provides `mock_portal.py`.

It must not be modified.

Start it with:

### Windows

```powershell
python mock_portal.py
```

### Linux/macOS

```bash
python3 mock_portal.py
```

The mock server runs at:

```text
http://127.0.0.1:8765
```

Health check:

```bash
curl http://127.0.0.1:8765/v1/health
```

Expected:

```json
{"ok":true}
```

The `/v1/health` endpoint does not require the API key.

Other API endpoints require:

```text
X-Api-Key: dfhire-2026
```

The complete API contract is documented in `API.md`.

---

# 6. QuickMart API Behavior

The mock server intentionally simulates unreliable production behavior.

Important behaviors include:

* pagination
* HTTP 429
* HTTP 500
* HTTP 503
* slow requests
* partial inventory responses
* duplicate inventory items
* mixed timestamp formats
* soft-ban responses
* different price representations
* store activation/serviceability changes

The implementation does not assume that an HTTP 200 response automatically means that the data is valid.

For example, a soft-ban response can return HTTP 200 while using:

```text
meta.source = edge
```

instead of:

```text
meta.source = origin
```

The scraper treats this as degraded data rather than valid inventory.

---

# 7. Store Selection

The scraper first retrieves the complete store list using pagination.

The QuickMart mock API contains 30 stores:

* 10 Mumbai
* 10 Delhi
* 10 Bengaluru

The implementation tracks stores that are:

```text
is_active = true
```

The current tracked set contains:

```text
26 stores
```

Inactive stores are not included in inventory collection.

`is_serviceable` is retained as store information but is not used as the condition for network membership.

---

# 8. Inventory Sweeps

A sweep means taking an inventory snapshot for all tracked stores at one requested timestamp.

The scraper accepts:

```bash
python sweep.py --as-of <timestamp>
```

Example:

```bash
python sweep.py --as-of 2026-09-28T04:30:00Z
```

The timestamp must contain timezone information.

The scraper normalizes the timestamp to UTC before making API requests.

---

# 9. Required Six Sweeps

The assignment requires these exact six sweeps:

```text
2026-09-27T04:30:00Z
2026-09-27T10:30:00Z
2026-09-27T19:00:00Z
2026-09-28T04:30:00Z
2026-09-28T10:30:00Z
2026-09-28T18:40:00Z
```

All six required sweeps are present in the local database.

Verified results:

| Sweep UTC              | IST date   | Complete | Incomplete | Observations |
| ---------------------- | ---------- | -------: | ---------: | -----------: |
| `2026-09-27T04:30:00Z` | 2026-09-27 |       26 |          0 |          714 |
| `2026-09-27T10:30:00Z` | 2026-09-27 |       26 |          0 |          714 |
| `2026-09-27T19:00:00Z` | 2026-09-28 |       26 |          0 |          744 |
| `2026-09-28T04:30:00Z` | 2026-09-28 |       26 |          0 |          744 |
| `2026-09-28T10:30:00Z` | 2026-09-28 |       25 |          1 |          716 |
| `2026-09-28T18:40:00Z` | 2026-09-29 |       26 |          0 |          744 |

The `2026-09-28T10:30:00Z` sweep contains one incomplete store because the mock API intentionally returns a partial response for `DEL-004`.

The incomplete store is recorded rather than being treated as out of stock.

---

# 10. UTC and IST

The assignment defines the requested report date as an IST calendar day.

India Standard Time is:

```text
UTC + 05:30
```

Therefore:

```text
2026-09-27T19:00:00Z
        ↓
2026-09-28 00:30 IST
        ↓
IST date = 2026-09-28
```

This is why the third required sweep belongs to the `2026-09-28` report date.

The implementation stores sweep timestamps in UTC and separately records the corresponding IST calendar date.

---

# 11. Pagination

The QuickMart API does not return all inventory in one response.

The inventory endpoint uses:

```text
cursor
```

The scraper starts from the first page and continues until:

```text
next_cursor = null
```

For example:

```text
Request page 1
      ↓
items + next_cursor
      ↓
Request next cursor
      ↓
items + next_cursor
      ↓
continue
      ↓
next_cursor = null
      ↓
finished
```

The implementation also removes duplicate products that may appear across pages.

---

# 12. Rate Limiting

The QuickMart server can return:

```text
HTTP 429
```

This means the client has made requests too quickly.

The API provides:

```text
Retry-After
```

The scraper respects the server-provided retry delay instead of immediately sending another request.

The implementation also uses request pacing to avoid unnecessarily hammering the mock server.

---

# 13. Temporary Server Errors

The API may return:

```text
500
503
```

These are treated as temporary server-side failures.

The scraper retries them using bounded exponential backoff.

Retries are bounded so the program cannot retry forever.

Permanent client errors such as:

```text
400
401
404
```

are not blindly retried.

---

# 14. Timeout Handling

The mock server can intentionally delay requests.

The scraper uses request timeouts so a slow request cannot block the entire sweep forever.

A timeout is treated as a temporary request failure and is handled within the bounded retry logic.

---

# 15. Soft-Ban Handling

The mock server can silently degrade responses after sustained high inventory traffic.

A soft-ban can still return:

```text
HTTP 200
```

but the response may contain:

```text
meta.source = edge
```

instead of:

```text
meta.source = origin
```

The scraper checks this metadata.

When a soft-ban is detected, the scraper does not treat the response as a successful inventory snapshot.

The implementation:

1. Detects the degraded source.
2. Waits before trying again.
3. Restarts inventory pagination from the beginning.
4. Limits the number of recovery rounds.
5. Marks the store incomplete if recovery cannot produce a reliable snapshot.

The soft-ban recovery behavior is also covered by the automated tests.

A naturally occurring soft-ban response was not separately captured during the six final sweeps, so this README does not claim that one occurred during those six runs.

---

# 16. Partial Responses

The API can return:

```json
{
  "partial": true
}
```

A partial response does not represent a complete inventory snapshot.

The implementation therefore marks the store-sweep as:

```text
incomplete
```

and records the reason.

It does not turn the missing products into out-of-stock observations.

This follows the assignment's principle:

> Wrong data is worse than no data.

---

# 17. Duplicate Products

The mock API can return duplicate products between inventory pages.

The scraper deduplicates products using their SKU identity before saving observations.

This prevents the same product from incorrectly contributing multiple times to the OSA calculation.

There is also a database primary key that prevents duplicate observation records for the same:

```text
as_of + store_id + sku_id
```

---

# 18. Data Normalization

The API can return data in different representations.

The scraper normalizes:

### Timestamps

All observation timestamps are converted to UTC.

### Prices

Prices are converted to numeric values.

This handles cases where Bengaluru can return price as a string while other cities return numeric values.

### Inventory status

The official availability field is:

```text
in_stock
```

The implementation uses `in_stock` for OSA.

It does not use `qty` to decide whether a product is available.

This is important because the mock API can create ghost-stock situations where:

```text
in_stock = true
qty = 0
```

The server's official availability flag must be trusted.

---

# 19. Database

The project uses SQLite.

The local database file is:

```text
osa.db
```

The database is created by the application when needed.

It is not provided as a separate company database.

The database is local and must not be committed to Git.

The `.gitignore` contains rules for:

```text
*.db
*.sqlite
*.sqlite3
```

---

# 20. Database Tables

The implementation uses four tables.

## `stores`

Stores information about QuickMart stores.

Important fields:

```text
store_id
city
name
is_active
is_serviceable
```

One row represents one store.

---

## `sweeps`

Stores the overall sweep history.

Important fields:

```text
as_of
ist_date
started_at
finished_at
```

One row represents one requested inventory sweep.

---

## `store_sweeps`

Stores the result for each store during each sweep.

Important fields:

```text
as_of
store_id
status
reason
item_count
fetched_at
```

A store-sweep can be:

```text
complete
```

or:

```text
incomplete
```

The reason is stored when a store cannot be completely collected.

---

## `observations`

Stores the actual inventory observations.

Important fields:

```text
as_of
store_id
sku_id
name
in_stock
qty
price
observed_at
```

One row represents one product observation for one store during one sweep.

The primary key prevents duplicate observations for the same:

```text
as_of + store_id + sku_id
```

---

# 21. Transactions and Idempotency

Database writes for a store are protected using transactions.

A transaction means the database changes are treated as one unit.

The goal is:

```text
all valid observations saved
OR
no partial observation set saved
```

The implementation also protects already-complete store-sweeps from being incorrectly replaced by incomplete data.

The database primary keys prevent duplicate observations.

This supports idempotent reruns.

Idempotency means:

> Running the same operation again should not create duplicate data or change a previously valid result incorrectly.

---

# 22. OSA Calculation

OSA means:

```text
On-Shelf Availability
```

It measures the percentage of product observations that were in stock.

The assignment requires:

```text
OSA =
total in-stock observations
--------------------------- × 100
total observations
```

The calculation is performed across all included stores and products for the requested city and IST date.

The implementation uses:

```text
in_stock
```

rather than:

```text
qty
```

---

# 23. Weighted OSA

The implementation does not calculate the average of store percentages.

For example:

```text
Store A:
9 in-stock / 10 observations

Store B:
1 in-stock / 2 observations
```

The correct calculation is:

```text
(9 + 1) / (10 + 2) × 100

= 10 / 12 × 100

= 83.33%
```

It is not:

```text
(90% + 50%) / 2
```

because the stores have different numbers of observations.

---

# 24. Incomplete Stores

Incomplete store-sweeps are excluded from the OSA calculation.

They are still reported in the API response.

This prevents missing inventory from being interpreted as out-of-stock inventory.

For example, during:

```text
2026-09-28T10:30:00Z
```

`DEL-004` returned a partial response.

Therefore:

```text
DEL-004 = incomplete
```

Its missing inventory is not converted into false out-of-stock observations.

---

# 25. No Data Behavior

If there is no valid inventory data for the requested city and date, the API returns:

```text
status = no_data
```

and:

```text
osa_pct = null
```

The implementation does not return:

```text
osa_pct = 0
```

because zero availability and no available data are different situations.

---

# 26. FastAPI Application

Start the API with:

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

The API runs at:

```text
http://127.0.0.1:8000
```

The FastAPI application only reads the local database.

It does not call QuickMart directly.

The architecture is:

```text
             QuickMart Mock API
                    |
                    | HTTP requests
                    v
                sweep.py
                    |
                    | normalized data
                    v
                  osa.db
                    |
                    | SQL queries
                    v
                  app.py
                    |
                    v
                GET /osa
```

This separation means the external API is collected during sweeps and the reporting API can answer requests from stored historical data.

---

# 27. GET /osa

Endpoint:

```text
GET /osa
```

Example:

```text
GET /osa?city=Mumbai&date=2026-09-28
```

Query parameters:

```text
city
date
```

Valid cities are:

```text
Mumbai
Delhi
Bengaluru
```

The date is an IST calendar date.

If the date is omitted, the API uses yesterday according to the assignment's IST requirement.

Invalid cities and invalid dates return HTTP 400.

---

# 28. OSA Response

The response contains information such as:

```text
status
city
date
osa_pct
stores_expected
stores_complete
incomplete
observations
skus
```

For the verified `2026-09-28` database:

### Mumbai

```text
OSA: 86.06%
Observations: 753
Expected stores: 9
Complete stores: 9
Incomplete stores: 0
```

### Delhi

```text
OSA: 79.63%
Observations: 761
Expected stores: 9
Complete stores: 9
Incomplete store-sweep records include DEL-004 at 10:30 UTC.
```

### Bengaluru

```text
OSA: 89.57%
Observations: 690
Expected stores: 8
Complete stores: 8
Incomplete stores: 0
```

These values are based on the local database generated by the required sweeps.

---

# 29. Code Review

The company provided `review_me.py` as intentionally problematic code.

The assignment requires identifying real problems and fixing only the top 2–3 serious issues.

The implementation made three targeted fixes:

1. Bounded retries with timeout, Retry-After handling and temporary-error backoff.
2. Timezone-aware UTC timestamp.
3. Removal of the mutable default argument.

Other problems identified in the review were intentionally not rewritten because the assignment asked for only targeted fixes.

`REVIEW.md` contains eight documented real problems, ordered by seriousness.

The reviewed code was executed successfully with the mock server running.

---

# 30. Testing

The project contains:

```text
tests/test_osa.py
tests/test_sweep.py
```

The final test suite contains:

```text
23 tests
```

Final verification:

```text
23 passed
```

Important tested cases include:

* weighted city OSA
* ghost stock
* incomplete store exclusion
* no-data behavior
* IST date mapping
* duplicate observation protection
* timezone validation
* UTC normalization
* mixed timestamp normalization
* price normalization
* pagination deduplication
* partial responses
* soft-ban handling
* retry behavior
* idempotent store saving
* incomplete store protection
* active-store tracking

Run all tests with:

```bash
pytest -q
```

---

# 31. Important Wrong-Number Cases

The tests specifically protect against incorrect OSA values.

### Ghost stock

A product can have:

```text
in_stock = true
qty = 0
```

The implementation still counts it as in stock because `in_stock` is the official field.

### Duplicate observations

Duplicate observations are prevented by deduplication and database primary keys.

### Incomplete store

An incomplete store-sweep is not treated as an out-of-stock observation.

### Weighted calculation

Store percentages are not averaged.

The implementation calculates:

```text
total in_stock / total observations
```

### IST mapping

UTC sweep timestamps are converted to IST before deciding which calendar date they belong to.

---

# 32. Running a Sweep

Start the mock API first.

Then run:

```bash
python sweep.py --as-of 2026-09-28T04:30:00Z
```

The scraper:

1. Validates the timestamp.
2. Converts it to UTC.
3. Calculates the IST calendar date.
4. Fetches all store pages.
5. Selects active stores.
6. Fetches inventory pages for each tracked store.
7. Handles pagination.
8. Handles retries.
9. Handles timeouts.
10. Handles 429 responses.
11. Handles 500/503 responses.
12. Detects degraded soft-ban responses.
13. Handles partial responses.
14. Deduplicates products.
15. Normalizes timestamps and prices.
16. Saves complete store observations.
17. Records incomplete store-sweeps when necessary.
18. Prints a sweep summary.

---

# 33. Verification Principle

The implementation follows these rules:

```text
Do not guess missing data.
Do not convert missing data into out-of-stock.
Do not treat every HTTP 200 as valid inventory.
Do not retry forever.
Do not use qty as the official availability field.
Do not calculate OSA using simple averages.
Do not use the UTC calendar date directly for IST reports.
```

---

# 34. AI Usage

AI was used as a development and review assistant.

AI-generated suggestions were checked against:

* the original assignment
* `API.md`
* actual source code
* the SQLite database
* actual API responses
* automated tests

Examples of mistakes caught during verification included:

* assuming database state without querying it
* treating HTTP 200 as automatically valid
* using `qty` instead of `in_stock`
* averaging store-level OSA percentages

These verification steps are documented in:

```text
AI_LOG.md
```

---

# 35. Notes

Implementation decisions and observations are documented in:

```text
NOTES.md
```

This includes:

* API behavior
* store selection
* database design
* pagination
* partial responses
* soft-ban handling
* retry behavior
* timestamps
* price normalization
* OSA calculation
* incomplete stores
* idempotency
* transactions
* six sweep results
* review findings
* assignment questions
* optional scaling considerations

---

# 36. Screen Recording

Recording information is documented in:

```text
RECORDING.md
```

The assignment work was recorded in multiple parts.

The public recording links and final timestamps will be added before submission.

The recording must be verified in an incognito/private browser before submission.

---

# 37. Git and Submission

The following local files must not be committed:

```text
osa.db
datafuel_env/
.venv/
venv/
__pycache__/
.pytest_cache/
*.pyc
```

The `.gitignore` contains rules for these files.

The final repository should contain the source code, documentation and tests, but not the local SQLite database or Python virtual environment.

---

# 38. Final Verification Checklist

Before submission:

* [x] `sweep.py` implemented
* [x] `app.py` implemented
* [x] SQLite schema implemented
* [x] Store pagination implemented
* [x] Inventory pagination implemented
* [x] Duplicate inventory handling implemented
* [x] Retry handling implemented
* [x] Timeout handling implemented
* [x] HTTP 429 handling implemented
* [x] HTTP 500/503 handling implemented
* [x] Soft-ban detection implemented
* [x] Partial-response handling implemented
* [x] Timestamp normalization implemented
* [x] Price normalization implemented
* [x] `in_stock` used for OSA
* [x] Incomplete store tracking implemented
* [x] Idempotent database behavior implemented
* [x] OSA calculation implemented
* [x] Coverage information implemented
* [x] No-data behavior implemented
* [x] Six required sweeps executed
* [x] 23 automated tests passing
* [x] `review_me.py` reviewed
* [x] Three targeted review fixes implemented
* [x] `REVIEW.md` completed
* [x] `NOTES.md` completed
* [x] `AI_LOG.md` completed
* [x] `RECORDING.md` prepared
* [x] `.gitignore` configured

---

# 39. Final Principle

The most important design principle in this assignment is:

> Wrong data is worse than no data.

The scraper therefore prefers to record an incomplete store-sweep rather than invent missing inventory information.

The reporting API then calculates OSA only from reliable, complete store-sweeps and clearly reports incomplete data to the caller.
