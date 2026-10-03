# NOTES.md

## QuickMart API Exploration and Implementation Notes

This file records important observations, implementation decisions, edge cases,
and reasoning used while completing the DataFuel Backend Engineer take-home assignment.

The original assignment, README.md, and API.md are the source of truth.

---

# 1. Authentication

Most QuickMart API endpoints require:

X-Api-Key: dfhire-2026

The /v1/health endpoint does not require authentication.

Requests without the API key were rejected with:

{"error": "missing or invalid X-Api-Key"}

This is expected behavior.

---

# 2. Store Discovery

The store API is paginated. The implementation follows all store pages until
next_page becomes null.

The complete store roster is saved in the stores table.

The implementation tracks stores where:

is_active = true

is_serviceable is not used as the main tracking condition because a store can
temporarily become non-serviceable while still belonging to the network.

The implementation discovered 30 stores and tracks 26 active stores.

---

# 3. Database

The project creates a local SQLite database named:

osa.db

The main tables are:

- stores
- sweeps
- store_sweeps
- observations

The stores table contains the QuickMart store roster.

The sweeps table contains one row for each requested inventory sweep.

The store_sweeps table records whether each store was complete or incomplete
for a particular sweep.

The observations table stores individual SKU observations.

The observations primary key is:

(as_of, store_id, sku_id)

This prevents the same SKU observation from being stored twice for the same
store and sweep.

---

# 4. Pagination

QuickMart inventory is paginated using cursor and next_cursor.

The first request starts at cursor 0.

The scraper continues requesting pages until next_cursor is null.

The implementation also deduplicates products by sku_id because the mock API
can return a duplicate item across pages.

---

# 5. Partial Responses

QuickMart can return:

partial = true

A partial response means that the inventory snapshot is incomplete.

The scraper does not treat missing products as out-of-stock.

Instead, the store-sweep is marked:

incomplete

with a reason such as:

partial_response

This follows the assignment rule:

Never turn missing data into out-of-stock.

---

# 6. Soft Ban

QuickMart can silently degrade responses when inventory requests are made too
aggressively.

A soft-ban response can still have HTTP 200 but contain:

meta.source = edge

instead of:

meta.source = origin

The scraper checks meta.source rather than trusting HTTP 200 alone.

The implementation pauses, restarts the store from cursor 0, and limits the
number of recovery rounds.

If recovery does not succeed, the store-sweep is marked incomplete instead of
saving unreliable data.

The soft-ban recovery logic is implemented in sweep.py.

The recovery code is implemented and tested with mocked responses, but a final
naturally occurring soft-ban recovery event was not separately captured during
the six required sweeps.

---

# 7. Rate Limiting

QuickMart can return:

HTTP 429 Too Many Requests

The response can contain a Retry-After header.

The scraper respects Retry-After before retrying.

The scraper also uses sequential requests and pacing to reduce the probability
of triggering rate limits.

---

# 8. Temporary Server Errors

HTTP 500 and HTTP 503 are treated as temporary failures.

The scraper retries them using bounded exponential backoff.

Timeouts and connection errors are also retried.

The retry count is limited so the program cannot retry forever.

Permanent errors such as HTTP 400, 401, and 404 are not blindly retried.

---

# 9. Timeout

The scraper specifies a request timeout.

This is important because the mock server can deliberately delay requests.

A timeout causes a bounded retry rather than allowing the sweep to hang forever.

---

# 10. Timezones

The assignment defines dates using the IST calendar day.

The scraper normalizes timestamps to UTC for storage and separately calculates
the IST date for each sweep.

Important mapping:

2026-09-27T04:30:00Z -> 2026-09-27 10:00 IST -> 2026-09-27

2026-09-27T10:30:00Z -> 2026-09-27 16:00 IST -> 2026-09-27

2026-09-27T19:00:00Z -> 2026-09-28 00:30 IST -> 2026-09-28

2026-09-28T04:30:00Z -> 2026-09-28 10:00 IST -> 2026-09-28

2026-09-28T10:30:00Z -> 2026-09-28 16:00 IST -> 2026-09-28

2026-09-28T18:40:00Z -> 2026-09-29 00:10 IST -> 2026-09-29

Therefore date=2026-09-28 uses these three sweeps:

2026-09-27T19:00:00Z
2026-09-28T04:30:00Z
2026-09-28T10:30:00Z

---

# 11. Mixed Timestamp Formats

QuickMart can return timestamps in UTC or with an IST offset.

For example:

2026-09-28T04:37:00Z

and:

2026-09-28T10:15:00+05:30

The scraper converts timezone-aware timestamps to UTC before storing them.

---

# 12. Price Normalization

The API can return prices as numbers or strings.

The scraper normalizes the price into a numeric value before storing it.

---

# 13. in_stock vs qty

QuickMart provides both:

in_stock

and:

qty

The assignment requires OSA to use in_stock.

qty is informational.

The mock API can produce ghost stock:

in_stock = true
qty = 0

Therefore:

qty > 0

must not be used to determine availability.

The implementation stores both values but calculates OSA using in_stock.

---

# 14. OSA Calculation

OSA means On-Shelf Availability.

The required formula is:

total in_stock observations
--------------------------- x 100
total observations

The implementation does not average individual store percentages.

Example:

Store A = 9/10
Store B = 1/2

Wrong calculation:

(90% + 50%) / 2 = 70%

Correct calculation:

(9 + 1) / (10 + 2) x 100 = 83.33%

The calculation is implemented in app.py.

---

# 15. Incomplete Stores

Incomplete store-sweeps are excluded from the OSA calculation.

Their missing products are never converted into out-of-stock observations.

The incomplete store and reason are still reported in the coverage section.

---

# 16. No Data

No data must not become 0%.

The API returns:

status = no_data
osa_pct = null

This follows the assignment rule that a wrong number is worse than no number.

---

# 17. Coverage

The /osa response reports:

stores_expected
stores_complete
incomplete

The incomplete list contains the affected store, sweep, and reason.

This makes the OSA result explainable.

---

# 18. Idempotency

Idempotency means that rerunning the same sweep does not create duplicate
observations.

The observation primary key is:

(as_of, store_id, sku_id)

The implementation also protects an existing complete store-sweep from being
replaced by a worse incomplete result.

---

# 19. Transactions

Inventory writes are performed using database transactions.

The basic flow is:

BEGIN
save observations
save store-sweep result
COMMIT

If an error occurs:

ROLLBACK

This helps prevent partially written store results.

---

# 20. Six Required Sweeps

All six required sweeps were executed.

Verified results:

Sweep 1:
2026-09-27T04:30:00Z
26 complete
0 incomplete
714 observations

Sweep 2:
2026-09-27T10:30:00Z
26 complete
0 incomplete
714 observations

Sweep 3:
2026-09-27T19:00:00Z
26 complete
0 incomplete
714 observations

Sweep 4:
2026-09-28T04:30:00Z
26 complete
0 incomplete
744 observations

Sweep 5:
2026-09-28T10:30:00Z
25 complete
1 incomplete
716 observations

The incomplete store was:

DEL-004

Reason:

partial_response

Sweep 6:
2026-09-28T18:40:00Z
26 complete
0 incomplete
744 observations

---

# 21. 2026-09-28 OSA Results

The current database produced:

Mumbai:
86.06%
753 observations
9 expected stores
9 complete stores

Delhi:
79.63%
761 observations
9 expected stores
9 complete stores
DEL-004 had an incomplete sweep with reason partial_response

Bengaluru:
89.57%
690 observations
8 expected stores
8 complete stores

These values should be regenerated from the final database immediately before
submission if the database changes.

---

# 22. Review of review_me.py

review_me.py was intentionally bad code supplied by the company.

The review identified these real problems:

1. Infinite retries and missing timeout.
2. Incorrect HTTP 429 handling.
3. Timezone-less as_of timestamp.
4. Retrying permanent HTTP errors.
5. Mutable default argument.
6. Unsafe SQL string construction.
7. Using qty instead of in_stock.
8. Incorrect city OSA aggregation.
9. Missing sweep history and completeness tracking.
10. Missing idempotency.

Only the most important targeted fixes were made in review_me.py.

The complete production implementation remains in sweep.py and app.py.

---

# 23. Exact Assignment Questions

## Question 1

A brand says:

"Your dashboard shows our Delhi availability fell from 92% to 41% yesterday."

What would you check first, before replying?

I would first check data coverage and completeness.

I would check the affected sweeps, incomplete stores, partial responses,
rate limiting, soft-ban indicators, timezone/date mapping, and whether the
calculation used the official in_stock field.

I would not immediately assume that the 41% represents a real business change.

---

## Question 2

The app's own dashboard says a city sold ₹4.20 lakh yesterday, but adding up
its store-level numbers gives ₹4.61 lakh. Which number would you show the brand,
and why?

I would not choose one number without investigating the discrepancy.

I would identify the authoritative source, check the aggregation logic, and
verify why the two numbers disagree before presenting a value to the brand.

The principle is to never present an unexplained number.

---

## Question 3

Where in this project would you not use an AI/LLM, and why?

I would not use an AI/LLM as the runtime decision-maker for inventory
availability or OSA calculation.

The API's in_stock field is authoritative and the OSA calculation should be
deterministic code.

AI can assist during development, documentation, and debugging, but final
business numbers should come from deterministic application logic and verified
source data.

---

# 24. Scaling to 20,000 Stores

The current implementation is deliberately conservative because correctness is
more important than maximum speed for this assignment.

For approximately 20,000 stores, I would introduce controlled concurrency using:

- a worker queue
- a fixed number of workers
- global rate limiting
- request timeouts
- bounded retries
- Retry-After handling
- soft-ban detection
- resumable store-sweep processing
- database batching
- monitoring and metrics

I would not simply send thousands of requests in parallel.

The same correctness rules would remain:

Never turn missing data into out-of-stock.
Never retry forever.
Never ignore partial responses.
Never ignore soft bans.

---

# 25. Final Principle

The project prioritizes:

Correctness > Completeness > Speed

If the API cannot provide trustworthy data, the system should report incomplete
coverage or no data instead of inventing an OSA percentage.

Wrong number is worse than no number.