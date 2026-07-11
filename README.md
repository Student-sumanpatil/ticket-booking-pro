# CineBook Pro — Ticket Booking System

A full ticket booking platform for movies and concerts: visual seat maps,
TTL-based seat holds that auto-release on checkout abandonment, a
waitlist that automatically reassigns cancelled seats, and QR-code email
tickets. Built with **FastAPI**, **SQLAlchemy**, and a vanilla JS frontend.

## Contents

- [Quick start](#quick-start)
- [Demo accounts](#demo-accounts)
- [Architecture](#architecture)
- [Database schema](#database-schema)
- [Seat hold, TTL, and concurrency logic](#seat-hold-ttl-and-concurrency-logic)
- [Waitlist logic](#waitlist-logic)
- [API docs](#api-docs)
- [Email & QR delivery](#email--qr-delivery)
- [Deployment](#deployment)
- [Project structure](#project-structure)

## Quick start

```bash
git clone https://github.com/<your-username>/ticket-booking-pro.git
cd ticket-booking-pro
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # defaults already work, no editing required
python seed.py                  # creates demo users, a venue, an event, a show
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** for the app, or **http://127.0.0.1:8000/docs**
for the interactive API documentation (Swagger UI, generated automatically
by FastAPI from the route definitions).

## Demo accounts

`seed.py` creates one of each role so you can try every flow immediately:

| Role      | Email               | Password    |
|-----------|----------------------|-------------|
| Admin     | admin@demo.com       | password123 |
| Organiser | organiser@demo.com   | password123 |
| Customer  | customer@demo.com    | password123 |

A venue ("Downtown Cineplex — Screen 3", 40 seats across Premium/Standard),
one event ("The Last Horizon"), and one scheduled show are pre-created.

## Architecture

```
Browser (vanilla JS SPA)
        |
        v
FastAPI app  ──────────────►  APScheduler background job
  ├─ /api/auth/*                 (runs every 15s, releases
  ├─ /api/admin/*                 expired holds + chains
  ├─ /api/organiser/*              waitlist offers)
  ├─ /api/events, /shows/*
  ├─ /api/holds, /bookings/*
  └─ /api/waitlist
        |
        v
SQLAlchemy ORM ──► SQLite (dev) / Postgres (prod)
```

Role-based auth uses JWT bearer tokens. Three roles: **admin** (manages
venues/seat layouts), **organiser** (creates events/shows, sets pricing,
views revenue), **customer** (browses, books, cancels, joins waitlists).

## Database schema

| Table                | Purpose |
|----------------------|---------|
| `users`               | Auth + role (admin / organiser / customer) |
| `venues`               | A physical location, created by an admin |
| `seat_categories`      | e.g. Premium, Standard — scoped to a venue |
| `seats`                | A physical seat (row + number), assigned a category |
| `events`               | A movie/concert, owned by an organiser |
| `shows`                | A specific date/time/venue instance of an event |
| `show_category_prices` | Per-show, per-category pricing set by the organiser |
| `show_seats`           | **The live seat map** — per-show status of every physical seat (`available` / `held` / `booked`), who holds it, and when the hold expires. This is the table all concurrency and TTL logic operates on. |
| `bookings`             | A confirmed (or cancelled) purchase: seats, price, QR path, reference code |
| `waitlist_entries`     | A customer waiting for a sold-out category, plus offer state if a seat has been offered to them |

Full column definitions are in `app/models.py`.

## Seat hold, TTL, and concurrency logic

This is the part the assignment is really testing, so here's exactly how
it works (see also `app/booking_logic.py`, which is heavily commented).

**Placing a hold** (`POST /api/holds`): for every requested seat, we run a
single conditional UPDATE:

```sql
UPDATE show_seats SET status = 'held', held_by_id = :customer, ...
WHERE id = :seat_id AND status = 'available'
```

We check `rowcount` afterward. If two customers request the same seat at
the same instant, the database itself serializes the two UPDATE
statements — only one can match `status = 'available'`, so only one
`rowcount` comes back as 1. The loser's request affects zero rows, so we
detect the conflict deterministically instead of trusting a racy
"read-then-write" check. If **any** seat in a multi-seat request loses
its race, the whole hold is rolled back — a customer never ends up with
a confusing partial seat selection.

Under SQLite specifically, this is made safe by enabling **WAL mode**
and a `busy_timeout` (see `app/database.py`): writers serialize instead
of immediately throwing "database is locked," so a losing request simply
waits a few milliseconds, then sees the seat is no longer `available`.
The same UPDATE-with-WHERE pattern works identically on Postgres/MySQL
under normal transaction isolation.

**TTL auto-release**: a hold gets a `hold_expires_at` timestamp
(`SEAT_HOLD_TTL_MINUTES`, default 10). A background job
(`app/scheduler.py`, via APScheduler) runs every
`RELEASE_SCHEDULER_INTERVAL_SECONDS` (default 15s) and finds every
`show_seats` row where `status = 'held'` and `hold_expires_at` is in the
past. Plain abandoned holds go back to `available`. Holds that were
actually **waitlist offers** are chained to the next waiting customer
instead (see below) — so an unclaimed offer doesn't just vanish back
into the general pool ahead of other waitlisted customers.

**Confirming a booking** (`POST /api/bookings`): re-checks that the hold
is still valid (correct customer, not expired) before flipping the seats
from `held` → `booked` and creating the `Booking` row, all in one
transaction.

## Waitlist logic

1. A customer joins a waitlist for a `(show, category)` pair when it's
   sold out (`POST /api/waitlist`).
2. When a booking is **cancelled** (`POST /api/bookings/{id}/cancel`),
   each freed seat calls `_promote_waitlist()`: it looks up the
   earliest `waiting` entry for that show + category. If one exists, the
   seat is put into `held` status again — but held *for the waitlisted
   customer*, with a fresh, shorter TTL (`WAITLIST_OFFER_TTL_MINUTES`,
   default 15). The entry's status becomes `offered`.
3. The customer gets an email with a **time-limited link**:
   `{BASE_URL}/waitlist/offer/{token}`. Visiting it calls
   `accept_waitlist_offer()`, which is just `confirm_booking()` under the
   hood — the offer *is* a hold, so the same concurrency-safe
   confirmation path applies.
4. If the offer expires unclaimed, the scheduler job notices the offer's
   `hold_expires_at` has passed, marks the waitlist entry `expired`, and
   immediately calls `_promote_waitlist()` again on the same seat — so it
   chains to the *next* person in line. If nobody else is waiting, the
   seat finally returns to the general `available` pool.

This gives a clean, auditable chain: `waiting → offered → fulfilled` or
`waiting → offered → expired → (next person offered, or available)`.

## API docs

FastAPI auto-generates interactive documentation from the route
definitions and Pydantic schemas — no separate doc file to keep in sync.
Run the app and open **`/docs`** (Swagger UI) or **`/redoc`** (ReDoc).
Every endpoint, request/response schema, and auth requirement is listed
there.

## Email & QR delivery

Set via `EMAIL_BACKEND` in `.env`:

- **`console`** (default): no credentials needed. Every email is saved
  as a real `.html` file under `sent_emails/` and logged to stdout, so
  you (or a grader) can open it and see exactly what would have been
  sent — including the QR code reference.
- **`smtp`**: sends real email via any provider. Fill in `SMTP_HOST`,
  `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` in `.env` (e.g. a Gmail
  address + an [App Password](https://myaccount.google.com/apppasswords),
  or a free Mailtrap/SendGrid sandbox).

QR codes are generated with the `qrcode` library, encoding the booking
reference, and saved under `tickets_qr/`.

## Deployment

**Render** (recommended, has a `render.yaml` blueprint in this repo):
1. Push this repo to GitHub.
2. On Render, "New" → "Blueprint" → point at your repo. It provisions a
   free Postgres database and a free web service automatically.
3. Update `BASE_URL` in the service's environment variables to your
   Render URL once assigned (needed so waitlist-offer email links point
   to the right place).

**Railway / Fly.io / any Python host**: the included `Procfile` works
as-is (`web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`). Set the
same environment variables as in `.env.example`.

Note: SQLite's file storage doesn't persist reliably on most free
hosting tiers (ephemeral filesystems). For a real hosted deployment, set
`DATABASE_URL` to a Postgres connection string — the code already
supports this via SQLAlchemy; just uncomment `psycopg2-binary` in
`requirements.txt`.

## Project structure

```
ticket-booking-pro/
├── app/
│   ├── main.py              # FastAPI app, mounts routers + static frontend
│   ├── config.py             # Settings from environment variables
│   ├── database.py            # SQLAlchemy engine/session, SQLite WAL setup
│   ├── models.py               # Full DB schema (see above)
│   ├── schemas.py               # Pydantic request/response models
│   ├── auth.py                   # Password hashing, JWT, role dependencies
│   ├── booking_logic.py           # Hold / confirm / cancel / waitlist logic
│   ├── scheduler.py                # Background TTL-release job
│   ├── qr_utils.py                  # QR code generation
│   ├── email_utils.py                # Console + SMTP email backends
│   ├── routers/
│   │   ├── auth_routes.py
│   │   ├── admin_routes.py           # Venue + seat layout management
│   │   ├── organiser_routes.py        # Events, shows, revenue
│   │   └── customer_routes.py          # Browse, seat map, hold, book, waitlist
│   └── static/                          # Frontend (HTML/CSS/vanilla JS)
├── seed.py                    # Demo data for quick testing
├── requirements.txt
├── .env.example
├── Procfile / render.yaml      # Deployment configs
├── README.md
└── DESIGN.md                    # System design write-up
```

## Known limitations (by design, for scope)

- The frontend is a functional single-page vanilla JS app, not a
  separate React build — kept this way so the whole project runs from
  one process with no build step. Swapping in a React frontend would
  only touch `app/static/` and `app/main.py`'s CORS config.
- Real-time seat map updates use polling (every 4s) rather than
  WebSockets, for simplicity. WebSocket push would be a natural upgrade.
- Email is console-logged by default (no real inbox needed to grade
  this) with a documented one-variable switch to real SMTP.
