"""
Populates the database with a demo admin/organiser/customer, one venue,
one event, and one scheduled show - so a grader (or you) can log in and
try the whole flow immediately without manually calling every API first.

Run with:  python seed.py
"""
from app.database import Base, engine, SessionLocal
from app.models import (
    User, UserRole, Venue, SeatCategory, Seat, Event, Show, ShowCategoryPrice, ShowSeat,
)
from app.auth import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()

if db.query(User).count() > 0:
    print("Database already has data - skipping seed. Delete ticketing.db to reseed.")
else:
    admin = User(name="Ada Admin", email="admin@demo.com", password_hash=hash_password("password123"), role=UserRole.admin)
    organiser = User(name="Oscar Organiser", email="organiser@demo.com", password_hash=hash_password("password123"), role=UserRole.organiser)
    customer = User(name="Cara Customer", email="customer@demo.com", password_hash=hash_password("password123"), role=UserRole.customer)
    db.add_all([admin, organiser, customer])
    db.flush()

    venue = Venue(name="Downtown Cineplex - Screen 3", address="12 Market Street", created_by_id=admin.id)
    db.add(venue)
    db.flush()

    premium = SeatCategory(venue_id=venue.id, name="Premium")
    standard = SeatCategory(venue_id=venue.id, name="Standard")
    db.add_all([premium, standard])
    db.flush()

    for row in ["A", "B"]:
        for n in range(1, 9):
            db.add(Seat(venue_id=venue.id, category_id=premium.id, row_label=row, seat_number=n, label=f"{row}{n}"))
    for row in ["C", "D", "E"]:
        for n in range(1, 9):
            db.add(Seat(venue_id=venue.id, category_id=standard.id, row_label=row, seat_number=n, label=f"{row}{n}"))
    db.flush()

    event = Event(
        title="The Last Horizon", genre="Sci-Fi",
        description="A stranded crew races against time to repair their ship before a dying star consumes the only path home.",
        organiser_id=organiser.id,
    )
    db.add(event)
    db.flush()

    show = Show(event_id=event.id, venue_id=venue.id, show_date="2026-07-20", show_time="19:30")
    db.add(show)
    db.flush()

    db.add(ShowCategoryPrice(show_id=show.id, category_id=premium.id, price=350))
    db.add(ShowCategoryPrice(show_id=show.id, category_id=standard.id, price=220))

    for seat in db.query(Seat).filter(Seat.venue_id == venue.id).all():
        db.add(ShowSeat(show_id=show.id, seat_id=seat.id))

    db.commit()
    print("Seeded demo data:")
    print("  Admin:     admin@demo.com / password123")
    print("  Organiser: organiser@demo.com / password123")
    print("  Customer:  customer@demo.com / password123")
    print(f"  Venue ID: {venue.id}, Event ID: {event.id}, Show ID: {show.id}")

db.close()
