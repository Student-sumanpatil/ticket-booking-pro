from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    User, UserRole, Event, Show, ShowSeat, Seat, SeatCategory, ShowCategoryPrice,
    SeatStatus, Booking, WaitlistEntry, WaitlistStatus,
)
from app.schemas import (
    SeatMapEntry, HoldRequest, HoldOut, BookingConfirmRequest, BookingOut,
    WaitlistJoinRequest, WaitlistOut,
)
from app.auth import require_role, get_current_user
from app.booking_logic import place_hold, confirm_booking, cancel_booking, accept_waitlist_offer

router = APIRouter(tags=["customer"])


@router.get("/api/events")
def list_events(db: Session = Depends(get_db)):
    events = db.query(Event).all()
    return [
        {
            "id": e.id, "title": e.title, "genre": e.genre, "description": e.description,
            "shows": [{"id": s.id, "date": s.show_date, "time": s.show_time, "venue": s.venue.name} for s in e.shows],
        }
        for e in events
    ]


@router.get("/api/shows/{show_id}/seatmap", response_model=list[SeatMapEntry])
def seat_map(show_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    show = db.query(Show).filter(Show.id == show_id).first()
    if not show:
        raise HTTPException(404, "Show not found")

    price_map = {p.category_id: p.price for p in db.query(ShowCategoryPrice).filter(ShowCategoryPrice.show_id == show_id)}
    show_seats = db.query(ShowSeat).filter(ShowSeat.show_id == show_id).all()

    return [
        SeatMapEntry(
            show_seat_id=ss.id,
            label=ss.seat.label,
            category=ss.seat.category.name,
            price=price_map.get(ss.seat.category_id, 0),
            status=ss.status,
            held_by_me=(ss.held_by_id == user.id and ss.status == SeatStatus.held),
        )
        for ss in show_seats
    ]


@router.post("/api/holds", response_model=HoldOut)
def create_hold(
    payload: HoldRequest,
    db: Session = Depends(get_db),
    customer: User = Depends(require_role(UserRole.customer)),
):
    return place_hold(db, payload.show_id, payload.seat_labels, customer)


@router.post("/api/bookings", response_model=BookingOut)
def create_booking(
    payload: BookingConfirmRequest,
    db: Session = Depends(get_db),
    customer: User = Depends(require_role(UserRole.customer)),
):
    return confirm_booking(db, payload.hold_token, customer)


@router.get("/api/bookings/me", response_model=list[BookingOut])
def my_bookings(db: Session = Depends(get_db), customer: User = Depends(require_role(UserRole.customer))):
    return (
        db.query(Booking)
        .filter(Booking.customer_id == customer.id)
        .order_by(Booking.created_at.desc())
        .all()
    )


@router.post("/api/bookings/{booking_id}/cancel")
def cancel_my_booking(
    booking_id: int, db: Session = Depends(get_db),
    customer: User = Depends(require_role(UserRole.customer)),
):
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.customer_id == customer.id).first()
    if not booking:
        raise HTTPException(404, "Booking not found")
    cancel_booking(db, booking)
    return {"status": "cancelled"}


@router.post("/api/waitlist", response_model=WaitlistOut)
def join_waitlist(
    payload: WaitlistJoinRequest,
    db: Session = Depends(get_db),
    customer: User = Depends(require_role(UserRole.customer)),
):
    category = (
        db.query(SeatCategory)
        .join(Show, Show.venue_id == SeatCategory.venue_id)
        .filter(Show.id == payload.show_id, SeatCategory.name == payload.category_name)
        .first()
    )
    if not category:
        raise HTTPException(404, "Category not found for this show")

    entry = WaitlistEntry(show_id=payload.show_id, category_id=category.id, customer_id=customer.id)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/waitlist/offer/{offer_token}")
def claim_waitlist_offer(offer_token: str, db: Session = Depends(get_db)):
    """
    The time-limited link sent in the waitlist-offer email. Deliberately
    unauthenticated-by-role here so the email link works with just the
    unguessable token; in production this would also verify the logged-in
    user matches the offer's customer_id.
    """
    booking = accept_waitlist_offer(db, offer_token)
    return {
        "status": "booked",
        "booking_reference": booking.booking_reference,
        "seats": booking.seat_labels,
    }
