"""
The heart of the assignment: seat holds with TTL, concurrency-safe seat
locking, booking confirmation, and waitlist auto-assignment.

CONCURRENCY PROTECTION
----------------------
Every seat state transition uses a single conditional UPDATE of the form:

    UPDATE show_seats SET status = 'held', ...
    WHERE id = :id AND status = 'available'

...and then checks `rowcount`. If two requests race for the same seat,
the database's own write-serialization guarantees only one UPDATE can
match `status = 'available'` - the loser's UPDATE affects zero rows,
so we can detect the conflict deterministically instead of trusting a
read-then-write check (which would be racy). See README / DESIGN.md for
the full explanation of why this is safe under SQLite's WAL mode too.

If ANY seat in a multi-seat hold request loses its race, the whole
transaction is rolled back (all-or-nothing) so a customer never ends up
with a partial, confusing seat selection.
"""
import uuid
from datetime import datetime, timedelta
from typing import List

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    ShowSeat, Seat, SeatStatus, Show, ShowCategoryPrice, Booking,
    BookingStatus, WaitlistEntry, WaitlistStatus, User,
)
from app.qr_utils import generate_ticket_qr
from app.email_utils import send_email


def _price_map_for_show(db: Session, show_id: int) -> dict:
    rows = db.query(ShowCategoryPrice).filter(ShowCategoryPrice.show_id == show_id).all()
    return {r.category_id: r.price for r in rows}


def place_hold(db: Session, show_id: int, seat_labels: List[str], customer: User) -> dict:
    show = db.query(Show).filter(Show.id == show_id).first()
    if not show:
        raise HTTPException(404, "Show not found")

    show_seats = (
        db.query(ShowSeat)
        .join(Seat, ShowSeat.seat_id == Seat.id)
        .filter(ShowSeat.show_id == show_id, Seat.label.in_(seat_labels))
        .all()
    )
    if len(show_seats) != len(set(seat_labels)):
        raise HTTPException(404, "One or more seat labels don't exist for this show")

    hold_token = uuid.uuid4().hex
    expires_at = datetime.utcnow() + timedelta(minutes=settings.SEAT_HOLD_TTL_MINUTES)
    conflicts = []

    for ss in show_seats:
        result = db.execute(
            update(ShowSeat)
            .where(ShowSeat.id == ss.id, ShowSeat.status == SeatStatus.available)
            .values(
                status=SeatStatus.held,
                held_by_id=customer.id,
                hold_token=hold_token,
                hold_expires_at=expires_at,
            )
        )
        if result.rowcount != 1:
            conflicts.append(ss.seat.label)

    if conflicts:
        db.rollback()
        raise HTTPException(
            409,
            f"These seats were just taken by someone else, pick again: {', '.join(conflicts)}",
        )

    db.commit()

    price_map = _price_map_for_show(db, show_id)
    total = sum(price_map.get(ss.seat.category_id, 0) for ss in show_seats)

    return {
        "hold_token": hold_token,
        "expires_at": expires_at,
        "seat_labels": seat_labels,
        "total_price": total,
    }


def confirm_booking(db: Session, hold_token: str, customer: User) -> Booking:
    show_seats = (
        db.query(ShowSeat)
        .filter(
            ShowSeat.hold_token == hold_token,
            ShowSeat.held_by_id == customer.id,
            ShowSeat.status == SeatStatus.held,
        )
        .all()
    )
    if not show_seats:
        raise HTTPException(410, "This hold has expired or doesn't belong to you. Please select seats again.")

    if any(ss.hold_expires_at < datetime.utcnow() for ss in show_seats):
        raise HTTPException(410, "Your seat hold expired. Please select seats again.")

    show_id = show_seats[0].show_id
    price_map = _price_map_for_show(db, show_id)
    total = sum(price_map.get(ss.seat.category_id, 0) for ss in show_seats)
    seat_labels = sorted(ss.seat.label for ss in show_seats)

    booking = Booking(
        show_id=show_id,
        customer_id=customer.id,
        seat_labels=",".join(seat_labels),
        total_price=total,
        status=BookingStatus.confirmed,
    )
    db.add(booking)
    db.flush()  # get booking.id before we reference it

    for ss in show_seats:
        ss.status = SeatStatus.booked
        ss.booking_id = booking.id
        ss.hold_token = None
        ss.hold_expires_at = None

    db.commit()
    db.refresh(booking)

    qr_path = generate_ticket_qr(booking.booking_reference)
    booking.qr_path = qr_path
    db.commit()

    send_email(
        to=customer.email,
        subject=f"Your CineBook ticket - {booking.booking_reference}",
        html_body=(
            f"<h2>Booking confirmed</h2>"
            f"<p>Seats: {booking.seat_labels}</p>"
            f"<p>Total: Rs. {booking.total_price:.2f}</p>"
            f"<p>Reference: <strong>{booking.booking_reference}</strong></p>"
            f"<p>Your QR ticket is attached / generated at {qr_path}</p>"
        ),
        attachment_path=qr_path,
    )
    return booking


def cancel_booking(db: Session, booking: Booking) -> None:
    if booking.status == BookingStatus.cancelled:
        return

    booking.status = BookingStatus.cancelled
    show_seats = db.query(ShowSeat).filter(ShowSeat.booking_id == booking.id).all()

    for ss in show_seats:
        ss.booking_id = None
        promoted = _promote_waitlist(db, ss)
        if not promoted:
            ss.status = SeatStatus.available
            ss.held_by_id = None
            ss.hold_token = None
            ss.hold_expires_at = None

    db.commit()


def _promote_waitlist(db: Session, freed_show_seat: ShowSeat) -> bool:
    """
    Offers a just-freed seat to the earliest waiting customer for that
    show + seat category. Returns True if an offer was made (seat stays
    'held', now against the waitlisted customer with a fresh, shorter
    TTL) or False if there's no one waiting (seat becomes available).
    """
    category_id = freed_show_seat.seat.category_id
    entry = (
        db.query(WaitlistEntry)
        .filter(
            WaitlistEntry.show_id == freed_show_seat.show_id,
            WaitlistEntry.category_id == category_id,
            WaitlistEntry.status == WaitlistStatus.waiting,
        )
        .order_by(WaitlistEntry.created_at.asc())
        .first()
    )
    if not entry:
        return False

    offer_token = uuid.uuid4().hex
    expires_at = datetime.utcnow() + timedelta(minutes=settings.WAITLIST_OFFER_TTL_MINUTES)

    freed_show_seat.status = SeatStatus.held
    freed_show_seat.held_by_id = entry.customer_id
    freed_show_seat.hold_token = offer_token
    freed_show_seat.hold_expires_at = expires_at

    entry.status = WaitlistStatus.offered
    entry.offered_show_seat_id = freed_show_seat.id
    entry.offer_token = offer_token
    entry.offer_expires_at = expires_at

    accept_url = f"{settings.BASE_URL}/waitlist/offer/{offer_token}"
    send_email(
        to=entry.customer.email,
        subject="A seat opened up - claim it before it expires",
        html_body=(
            f"<h2>Seat available</h2>"
            f"<p>Seat {freed_show_seat.seat.label} ({freed_show_seat.seat.category.name}) "
            f"is being held for you.</p>"
            f"<p>Confirm within {settings.WAITLIST_OFFER_TTL_MINUTES} minutes or it goes to "
            f"the next person on the waitlist:</p>"
            f"<p><a href='{accept_url}'>{accept_url}</a></p>"
        ),
    )
    return True


def release_expired_holds(db: Session) -> None:
    """
    Scheduled job (see scheduler.py). Runs periodically to:
      1. Release plain customer holds that timed out (abandoned checkout)
         back to the 'available' pool.
      2. Expire waitlist offers that timed out and chain the offer to
         the next person on the waitlist (or free the seat if no one
         else is waiting).
    """
    now = datetime.utcnow()
    expired = (
        db.query(ShowSeat)
        .filter(ShowSeat.status == SeatStatus.held, ShowSeat.hold_expires_at < now)
        .all()
    )

    for ss in expired:
        offer = (
            db.query(WaitlistEntry)
            .filter(
                WaitlistEntry.offered_show_seat_id == ss.id,
                WaitlistEntry.status == WaitlistStatus.offered,
                WaitlistEntry.offer_token == ss.hold_token,
            )
            .first()
        )
        if offer:
            offer.status = WaitlistStatus.expired
            ss.status = SeatStatus.available
            ss.held_by_id = None
            ss.hold_token = None
            ss.hold_expires_at = None
            db.flush()
            _promote_waitlist(db, ss)  # chain to next in line, if any
        else:
            ss.status = SeatStatus.available
            ss.held_by_id = None
            ss.hold_token = None
            ss.hold_expires_at = None

    db.commit()


def accept_waitlist_offer(db: Session, offer_token: str) -> Booking:
    entry = (
        db.query(WaitlistEntry)
        .filter(WaitlistEntry.offer_token == offer_token, WaitlistEntry.status == WaitlistStatus.offered)
        .first()
    )
    if not entry:
        raise HTTPException(404, "This offer link is invalid or has already been used.")
    if entry.offer_expires_at < datetime.utcnow():
        raise HTTPException(410, "This offer has expired.")

    booking = confirm_booking(db, hold_token=offer_token, customer=entry.customer)
    entry.status = WaitlistStatus.fulfilled
    db.commit()
    return booking
