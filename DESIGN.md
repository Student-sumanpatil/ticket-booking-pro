# System Design Write-up — CineBook Ticket Booking System

*(≈790 words)*

## Overview

The hard part of a ticket booking system isn't displaying seats — it's
guaranteeing that a seat is never sold twice, that abandoned selections
don't permanently lock inventory, and that cancellations get redirected
to waiting customers automatically. This write-up covers those four
mechanisms: seat holds with TTL, concurrency prevention, waitlist
auto-assignment, and time-limited offers.

## Seat hold and TTL mechanism

Every physical seat has exactly one live row per show in `show_seats`,
holding its current `status` (`available` / `held` / `booked`), who is
holding it (`held_by_id`), a `hold_token` grouping seats selected
together in one checkout, and `hold_expires_at`.

When a customer selects seats, `POST /api/holds` stamps
`hold_expires_at = now + SEAT_HOLD_TTL_MINUTES` (default 10) and flips
status to `held`. The seat map immediately reflects this to every other
customer polling it. If the customer completes checkout in time,
`POST /api/bookings` converts `held → booked`. If they abandon the
page, nothing needs to happen client-side — a background job
(APScheduler, running every 15 seconds) scans for `held` rows whose
`hold_expires_at` has passed and flips them back to `available`. TTL
enforcement therefore lives entirely at the database + scheduler level,
not in client state, so it's correct even if the customer's browser
crashes or closes.

## Concurrency prevention

The naive approach — read a seat's status, check it's available, then
write `held` — is racy: two requests can both read "available" before
either writes. Instead, every hold is a single conditional UPDATE:

```sql
UPDATE show_seats SET status='held', held_by_id=:cust, hold_token=:tok,
       hold_expires_at=:exp
WHERE id=:seat_id AND status='available'
```

The `WHERE status='available'` clause makes the check and the write
atomic from the database's point of view — there's no gap between
"check" and "write" for a second transaction to slip into. We inspect
`rowcount` afterward: exactly one concurrent request can ever get
`rowcount=1` for a given seat; every other simultaneous request gets 0
and is treated as a conflict. If a customer requests multiple seats and
even one loses its race, the entire transaction is rolled back — nobody
ends up with a confusing partial selection.

Under SQLite (used for local dev/grading), this is made robust by
enabling **WAL mode** with a `busy_timeout`. WAL allows concurrent
readers alongside a single writer, and the timeout means a second
writer *waits* briefly for the first to finish instead of immediately
erroring with "database is locked" — by the time it runs, it correctly
sees the seat is no longer available. The identical UPDATE-with-WHERE
pattern is safe on Postgres/MySQL under standard read-committed
isolation, since row-level locking during the UPDATE provides the same
guarantee — so the same code works unchanged if `DATABASE_URL` is
switched to Postgres for production.

## Waitlist auto-assignment flow

A customer joins a waitlist for a specific `(show, category)` pair via
`POST /api/waitlist` when it's sold out. Waitlist entries are strictly
FIFO, ordered by `created_at`.

The trigger for reassignment is a booking cancellation. When
`POST /api/bookings/{id}/cancel` runs, each seat that was part of the
cancelled booking calls an internal `_promote_waitlist()` step: it looks
for the oldest `waiting` entry matching that show and category. If one
exists, instead of the seat becoming plainly `available` again, it goes
back into `held` status — but now held *for the waitlisted customer*,
under a brand new `hold_token` that doubles as the offer's token. The
waitlist entry's status becomes `offered`, recording which seat it was
offered and when the offer expires. If no one is waiting, the seat is
simply released to the general pool as normal.

## Time-limited offer handling

The offer is deliberately implemented as *the same hold mechanism*
described above, just with a shorter TTL
(`WAITLIST_OFFER_TTL_MINUTES`, default 15) and a different trigger. The
customer receives an email containing `{BASE_URL}/waitlist/offer/{token}`.
Visiting that link calls `accept_waitlist_offer()`, which internally
calls the exact same `confirm_booking()` used for a normal checkout —
so an accepted offer goes through identical validation and concurrency
guarantees as any other booking.

If the offer's TTL lapses unclaimed, the same background scheduler that
handles ordinary hold expiry notices it, but with one difference: rather
than releasing the seat straight to `available`, it checks whether the
expiring hold corresponds to an outstanding waitlist offer (matched by
`hold_token`). If so, it marks that entry `expired` and immediately
re-runs `_promote_waitlist()` on the same seat — chaining the offer to
the next person in line. Only when the waitlist for that category is
completely empty does the seat finally return to general availability.
This produces a clean, auditable state chain per entry:
`waiting → offered → fulfilled`, or
`waiting → offered → expired → (offered again, or available)`.
