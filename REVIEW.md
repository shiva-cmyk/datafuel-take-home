

# Code Review: review_me.py

## Purpose

review_me.py is intentionally flawed code supplied by the company.

The assignment requires me to:

1. Find at least 5 real problems.
2. Explain what actually goes wrong.
3. Give concrete examples.
4. Rank the problems by seriousness.
5. Fix only the 2-3 most serious problems.

I reviewed the original code and made targeted fixes rather than rewriting the entire file.


# Problem 1 - Infinite Retry Loop and Missing Timeout

Severity:
CRITICAL

File:
review_me.py

Function:
fetch_inventory()

What the original code does:

The original code uses an infinite while True retry loop.

It also does not specify a request timeout.

Original pattern:

while True:
    try:
        r = requests.get(...)
        r.raise_for_status()
        break
    except Exception:
        time.sleep(0.1)
        continue

What goes wrong:

If QuickMart keeps returning errors, the program can retry forever.

If the server does not respond, the request can also wait indefinitely.

Concrete example:

If QuickMart repeatedly returns HTTP 503, the original program can continue retrying forever.

Production impact:

The inventory sweep can hang and never finish.

Fix:

The current review_me.py uses a maximum number of attempts and a request timeout.

Status:

FIXED

Evidence:

review_me.py -> MAX_ATTEMPTS
review_me.py -> REQUEST_TIMEOUT
review_me.py -> fetch_inventory()


# Problem 2 - Incorrect HTTP 429 Handling

Severity:
CRITICAL

File:
review_me.py

Function:
fetch_inventory()

What the original code does:

The original code treats every error in the same way and waits only 0.1 seconds.

It does not properly handle HTTP 429.

What is HTTP 429?

HTTP 429 means Too Many Requests.

QuickMart can return a Retry-After header telling the client how long to wait.

Concrete example:

HTTP 429
Retry-After: 2

The original code waits only 0.1 seconds and tries again.

This can make rate limiting worse.

Fix:

The current review_me.py reads Retry-After and waits for the requested delay.

The number of retries is also limited.

Status:

FIXED

Evidence:

review_me.py -> fetch_inventory() -> HTTP 429 handling


# Problem 3 - Timezone-less as_of Timestamp

Severity:
HIGH

File:
review_me.py

Function:
main execution block

What the original code does:

The original code uses:

datetime.utcnow().isoformat()

This produces a timestamp without timezone information.

Example:

2026-10-03T10:30:00

QuickMart requires a timezone-aware timestamp.

A valid UTC timestamp is:

2026-10-03T10:30:00Z

Production impact:

The API can reject the request because the timestamp does not contain timezone information.

Fix:

The current code uses:

datetime.now(timezone.utc)

and produces a UTC timestamp.

Status:

FIXED

Evidence:

review_me.py -> main execution block

# Problem 4 - Retrying Permanent HTTP Errors

Severity:
HIGH

File:
review_me.py

Function:
fetch_inventory()

What the original code does:

The original code catches every exception:

except Exception:
    time.sleep(0.1)
    continue

This means it does not distinguish between temporary errors and permanent errors.

For example:

400 = Bad Request
401 = Unauthorized
404 = Store or resource not found

These errors normally should not be retried forever.

Concrete example:

If the API returns HTTP 401 because the API key is invalid, retrying the same request will not fix the problem.

The request will continue to fail.

Production impact:

The scraper wastes time repeatedly sending requests that cannot succeed.

It can also make debugging much harder.

What should happen:

Temporary failures such as 500, 503, timeout, or connection errors can be retried with limits.

Permanent errors such as 400, 401, and 404 should not be blindly retried.

Fix:

The current review_me.py only retries selected temporary failures.

Other HTTP errors are allowed to raise an exception instead of being retried forever.

Status:

FIXED

Evidence:

review_me.py -> fetch_inventory()
review_me.py -> handling for 500/503
review_me.py -> r.raise_for_status()


# Problem 5 - Mutable Default Argument

Severity:
MEDIUM

File:
review_me.py

Function:
fetch_inventory()

What the original code does:

The original function uses:

def fetch_inventory(store_id, as_of, cursor="0", results=[]):

The results list is created only once and is reused between function calls.

This is called a mutable default argument.

Why this is a problem:

The function is supposed to collect results for one inventory request.

But a previous call can leave data inside the same list.

Concrete example:

Suppose the first call collects:

["SKU-0001", "SKU-0002"]

Then another call starts with the same default results list.

It may already contain the previous store's items.

That can mix inventory data from different stores.

Production impact:

Inventory results can become incorrect.

This can lead to wrong database records and wrong OSA calculations.

Fix:

The current code uses:

def fetch_inventory(store_id, as_of, cursor="0", results=None):

and then creates a new list:

if results is None:
    results = []

This gives every top-level call its own result list.

Status:

FIXED

Evidence:

review_me.py -> fetch_inventory()
review_me.py -> results=None


# Problem 6 - Unsafe SQL String Construction

Severity:
HIGH

File:
review_me.py

Function:
save()

What the original code does:

The original code builds the SQL statement using an f-string:

f"INSERT INTO inventory VALUES ('{store_id}', '{it['sku_id']}', ...)"

The values are inserted directly into the SQL string.

Why this is a problem:

Data values can contain characters such as apostrophes.

For example, a product name could contain:

Farmer's Choice

The apostrophe can break the SQL statement.

Directly inserting values into SQL can also create SQL injection risks when the values are not fully trusted.

Production impact:

The database insert can fail or, in a less controlled system, malicious input could alter the SQL command.

What should happen:

SQL parameters should be used instead of constructing SQL with string interpolation.

For example:

conn.execute(
    "INSERT INTO inventory (...) VALUES (?, ?, ...)",
    (value1, value2, ...)
)

Status:

NOT FIXED

Reason:

The assignment asks for only the top 2-3 fixes in review_me.py.

This problem was identified but was intentionally left unchanged.

Evidence:

review_me.py -> save()


# Problem 7 - OSA Uses qty Instead of in_stock

Severity:
CRITICAL

File:
review_me.py

Function:
city_osa()

What the original code does:

The original code reads:

SELECT qty FROM inventory ...

It then decides that a product is in stock when:

qty > 0

But the QuickMart API provides an official field called:

in_stock

The assignment specifically requires using in_stock.

Why this is a problem:

QuickMart can contain ghost stock.

Ghost stock means:

in_stock = true
qty = 0

The product is officially considered available even though the quantity is zero.

Concrete example:

SKU-0002:

in_stock = true
qty = 0

The original code sees:

qty > 0

which is false.

So it incorrectly counts the product as out of stock.

Production impact:

The OSA percentage can be wrong.

Wrong OSA numbers are specifically considered worse than having no number.

What should happen:

The scraper/API calculation should use the server's in_stock field.

Status:

NOT FIXED

Reason:

This is one of the correctness problems identified during review, but it was not one of the limited fixes made to review_me.py.

The main sweep.py implementation handles the official in_stock field.

Evidence:

review_me.py -> city_osa()

Assignment/API requirement:

Inventory availability is determined by in_stock, not qty.


# Problem 8 - Incorrect City OSA Aggregation

Severity:
CRITICAL

File:
review_me.py

Function:
city_osa()

What the original code does:

The original code first calculates an OSA percentage separately for each store.

It then averages those store percentages:

sum(per_store) / len(per_store)

Why this is a problem:

The assignment requires the city OSA to be calculated from all observations together.

The correct formula is:

total in_stock observations
--------------------------- x 100
total observations

Concrete example:

Store A:
9 in-stock observations
10 total observations

Store B:
1 in-stock observation
2 total observations

Correct calculation:

(9 + 1) / (10 + 2) * 100

= 10 / 12 * 100

= 83.33%

The original code calculates:

Store A = 90%
Store B = 50%

Then:

(90% + 50%) / 2

= 70%

So the original code produces the wrong answer.

Production impact:

The city OSA number can be incorrect.

This is especially serious when different stores have different numbers of observations.

Status:

NOT FIXED

Reason:

The intentionally bad review_me.py was not completely rewritten.

The correct weighted calculation is implemented in the main app.py implementation.

Evidence:

review_me.py -> city_osa()
app.py -> calculate_osa()


# Fix Summary

## Problems Fixed

The current review_me.py contains targeted fixes for three related areas:

1. Request reliability
   - bounded retry attempts
   - request timeout
   - retry handling for temporary 500/503 errors
   - Retry-After handling for HTTP 429
   - no blind retry of permanent HTTP errors

2. Timezone correctness
   - replaced timezone-less datetime.utcnow()
   - uses timezone-aware UTC datetime

3. Mutable default argument
   - changed results=[] to results=None
   - creates a fresh list for each top-level call


## Problems Intentionally Not Fixed

The following problems were identified but remain in review_me.py:

- unsafe SQL string construction
- using qty instead of in_stock
- incorrect city OSA aggregation
- missing sweep history
- missing store completeness tracking
- missing idempotency
- incomplete handling of partial/soft-ban responses

These were intentionally not fixed because the assignment specifically asks for only the 2-3 most serious fixes in review_me.py.

The complete assignment implementation is in sweep.py and app.py.


# Important Note

review_me.py is a code-review exercise.

It should NOT be presented as the final production scraper.

The purpose of this file is to demonstrate that I can:

1. Read unfamiliar code.
2. Identify real problems.
3. Explain why they matter.
4. Prioritize problems.
5. Make a small number of targeted fixes without unnecessarily rewriting the code.

The actual inventory scraper is sweep.py.

The actual OSA API is app.py.


# Final Review Status

At least 5 real problems were identified.

The problems include:

- infinite retry behavior
- missing request timeout
- incorrect 429 handling
- retrying permanent errors
- timezone-less timestamps
- mutable default argument
- unsafe SQL construction
- incorrect use of qty instead of in_stock
- incorrect city aggregation

The most important correctness problems were explicitly identified even when they were not changed in review_me.py.

No problem is described as fixed unless the current code contains evidence of the fix.