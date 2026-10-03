# AI_LOG.md

## Purpose

This file records how AI assistance was used during the DataFuel Backend
Engineer take-home assignment.

AI was used as an assistance, learning, coding, debugging, testing, and
documentation tool.

AI suggestions were not treated as automatically correct. Important
suggestions were checked against the original assignment, README.md,
API.md, the actual QuickMart mock API, source code, database contents,
and test results.

The final implementation decisions were based on the assignment requirements
and actual verification.

---

# 1. AI Tool Used

The main AI assistant used during this assignment was ChatGPT.

AI assistance was used for:

- understanding the assignment requirements
- understanding the QuickMart API
- explaining HTTP concepts
- understanding pagination
- understanding retries and rate limiting
- understanding soft-ban behavior
- designing the SQLite database structure
- reviewing review_me.py
- identifying edge cases
- designing tests
- debugging implementation issues
- explaining OSA calculation
- checking UTC and IST handling
- preparing documentation
- preparing interview explanations

AI suggestions were checked against the actual project rather than being
accepted automatically.

---

# 2. Representative Prompt 1

A representative prompt used during the assignment was:

"Explain the entire DataFuel assignment clearly in beginner language. Treat the
original assignment document, README.md, and API.md as the source of truth.
Do not hallucinate or assume that something is implemented. Explain what
sweep.py, app.py, the database, OSA, pagination, retries, rate limiting,
soft bans, partial responses, UTC and IST are supposed to do."

## Why this was useful

The assignment contains many requirements that depend on each other.

AI helped break the assignment into smaller concepts and explain how the
components fit together.

The resulting implementation was then checked against the actual assignment
and project files.

---

# 3. Representative Prompt 2

Another representative prompt was:

"Review the actual review_me.py file and identify real problems. Compare the
code behavior against the QuickMart API requirements. Explain what can go
wrong and identify the most serious problems that should be fixed."

## Why this was useful

review_me.py was intentionally provided as problematic code.

AI helped identify real problems including:

- infinite retries
- missing timeout
- incorrect 429 handling
- timezone-less timestamps
- mutable default arguments
- retrying permanent HTTP errors
- unsafe SQL construction
- using qty instead of in_stock
- incorrect city OSA aggregation
- missing idempotency
- missing sweep history
- missing completeness tracking

The identified issues were checked against the actual code before being
documented in REVIEW.md.

Only the most serious targeted problems were fixed in review_me.py, as required
by the assignment.

---

# 4. Representative Prompt 3

Another representative prompt was:

"Explain how the six required UTC sweep timestamps map to IST dates and which
sweeps should be used for date=2026-09-28."

## Why this was useful

The assignment defines the /osa date using the IST calendar day.

The six required timestamps were checked by converting them from UTC to IST.

The important mapping is:

2026-09-27T04:30:00Z -> 2026-09-27 10:00 IST -> 2026-09-27

2026-09-27T10:30:00Z -> 2026-09-27 16:00 IST -> 2026-09-27

2026-09-27T19:00:00Z -> 2026-09-28 00:30 IST -> 2026-09-28

2026-09-28T04:30:00Z -> 2026-09-28 10:00 IST -> 2026-09-28

2026-09-28T10:30:00Z -> 2026-09-28 16:00 IST -> 2026-09-28

2026-09-28T18:40:00Z -> 2026-09-29 00:10 IST -> 2026-09-29

Therefore the three sweeps belonging to IST date 2026-09-28 are:

2026-09-27T19:00:00Z
2026-09-28T04:30:00Z
2026-09-28T10:30:00Z

The result was verified against the database and the /osa implementation.

---

# 5. AI Mistake #1 - Assuming the Database/Sweep State

During development, AI explanations initially focused on what the completed
database and sweep results should look like.

That could have caused an incorrect assumption that the required sweeps had
already been executed.

## How the mistake was caught

The actual SQLite database was inspected directly.

The sweeps table, store_sweeps table, and observations table were queried.

The six required timestamps were then verified against the actual database.

This showed the actual execution state rather than relying on an assumption.

## Lesson

A file existing or code looking correct is not proof that the required
operation was executed.

Database contents and execution evidence must be checked directly.

---

# 6. AI Mistake #2 - Treating HTTP 200 as Successful Inventory Data

During discussion of QuickMart's API behavior, it was initially easy to think
that a successful HTTP status code such as 200 meant that the inventory
response was valid.

However, the assignment specifically warns about soft bans.

The QuickMart API can return HTTP 200 while:

meta.source = edge

and the inventory response can be empty or truncated.

## How the mistake was caught

API.md and mock_portal.py were inspected.

The mock server behavior showed that meta.source is an important soft-ban
indicator.

The implementation was therefore changed to inspect the response body and
meta.source instead of trusting HTTP status alone.

Tests were also added for soft-ban handling.

## Lesson

HTTP 200 only means that the HTTP request itself succeeded.

It does not necessarily mean that the returned business data is complete or
trustworthy.

---

# 7. AI Mistake #3 - Using qty to Determine Stock Availability

During the implementation discussion, qty was an obvious field to consider
for availability because it represents a quantity.

However, the QuickMart API contract explicitly defines in_stock as the
official availability flag.

The mock API can also create ghost-stock situations where:

in_stock = true
qty = 0

## How the mistake was caught

API.md was checked and confirmed that in_stock is the authoritative field.

The mock API behavior was also inspected.

A real inventory response contained a case where the two values differed.

The implementation and tests were therefore written to use in_stock for OSA.

## Lesson

The field that looks intuitive is not necessarily the business-authoritative
field.

The API contract must be followed.

---

# 8. AI Mistake #4 - Averaging Store Percentages

A simple approach to city OSA would be:

1. calculate each store's percentage
2. average those percentages

That approach was identified as incorrect for this assignment.

For example:

Store A:
9 in-stock observations / 10 total = 90%

Store B:
1 in-stock observation / 2 total = 50%

Incorrect:

(90% + 50%) / 2 = 70%

Correct:

(9 + 1) / (10 + 2) * 100 = 83.33%

## How the mistake was caught

The assignment's OSA definition was checked.

A dedicated test was added to verify the weighted calculation.

The test expects:

83.33

rather than:

70.00

## Lesson

The OSA calculation must use total observations across the city, not an
unweighted average of store percentages.

---

# 9. How AI Suggestions Were Verified

AI-generated suggestions were verified using several methods.

## Assignment Verification

The original assignment and README.md were treated as the source of truth.

## API Verification

API.md and mock_portal.py were inspected to understand actual server behavior.

## Code Verification

The actual Python implementation was inspected rather than assuming that
a suggested feature existed.

## Runtime Verification

The mock QuickMart server was executed and API behavior was tested.

## Database Verification

osa.db was inspected to verify sweep records, store-sweep records, and
observations.

## Automated Testing

pytest was used to verify important behavior.

The current test suite contains 23 tests.

The verified test run produced:

23 passed

## Output Verification

The /osa endpoint was tested using the actual database data.

The six required sweeps were also checked in the database.

---

# 10. Important Principle

AI was used as an assistant, not as the source of truth.

The source of truth was:

1. Original assignment
2. README.md
3. API.md
4. mock_portal.py behavior
5. Actual source code
6. Actual database contents
7. Automated tests
8. Runtime results

If an AI suggestion conflicted with the assignment or actual API behavior,
the assignment and actual behavior were followed.

---

# 11. AI Usage Summary

AI helped with:

- learning unfamiliar backend concepts
- understanding the assignment
- reviewing code
- identifying edge cases
- writing and improving tests
- debugging
- documentation
- interview preparation

AI did not replace verification.

Important implementation decisions were checked using the actual repository,
mock server, database, tests, and assignment requirements.

---

# 12. Final Lesson

The most important lesson from using AI on this assignment was:

Do not trust an AI-generated answer just because it sounds technically correct.

For backend systems, the actual API contract, source code, database state,
runtime behavior, and tests must be checked.

The goal was not simply to produce code that looked correct.

The goal was to produce code whose behavior could be verified.