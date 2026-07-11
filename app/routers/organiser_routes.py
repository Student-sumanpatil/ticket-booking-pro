from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    User, UserRole, Event, Show, ShowCategoryPrice, ShowSeat, Seat,
    SeatCategory, Venue, Booking, BookingStatus,
)
from app.schemas import EventCreate, ShowCreate, ShowOut
from app.auth import require_role

router = APIRouter(prefix="/api/organiser", tags=["organiser"])


@router.post("/events")
def create_event(
    payload: EventCreate,
    db: Session = Depends(get_db),
    organiser: User = Depends(require_role(UserRole.organiser)),
):
    event = Event(
        title=payload.title, genre=payload.genre, description=payload.description,
        organiser_id=organiser.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"id": event.id, "title": event.title}


@router.post("/shows", response_model=ShowOut)
def create_show(
    payload: ShowCreate,
    db: Session = Depends(get_db),
    organiser: User = Depends(require_role(UserRole.organiser)),
):
    event = db.query(Event).filter(Event.id == payload.event_id, Event.organiser_id == organiser.id).first()
    if not event:
        raise HTTPException(404, "Event not found or not owned by you")

    venue = db.query(Venue).filter(Venue.id == payload.venue_id).first()
    if not venue:
        raise HTTPException(404, "Venue not found")

    show = Show(
        event_id=event.id, venue_id=venue.id,
        show_date=payload.show_date, show_time=payload.show_time,
    )
    db.add(show)
    db.flush()

    categories = {c.name: c for c in db.query(SeatCategory).filter(SeatCategory.venue_id == venue.id).all()}
    for cp in payload.category_prices:
        if cp.category_name not in categories:
            db.rollback()
            raise HTTPException(400, f"Venue has no category named '{cp.category_name}'")
        db.add(ShowCategoryPrice(show_id=show.id, category_id=categories[cp.category_name].id, price=cp.price))

    # Materialize one ShowSeat row per physical seat in the venue - this is
    # the live per-show seat map that holds/bookings/waitlist all operate on.
    for seat in db.query(Seat).filter(Seat.venue_id == venue.id).all():
        db.add(ShowSeat(show_id=show.id, seat_id=seat.id))

    db.commit()
    db.refresh(show)
    return show


@router.get("/events/{event_id}/revenue")
def event_revenue(
    event_id: int,
    db: Session = Depends(get_db),
    organiser: User = Depends(require_role(UserRole.organiser)),
):
    event = db.query(Event).filter(Event.id == event_id, Event.organiser_id == organiser.id).first()
    if not event:
        raise HTTPException(404, "Event not found or not owned by you")

    show_ids = [s.id for s in event.shows]
    bookings = (
        db.query(Booking)
        .filter(Booking.show_id.in_(show_ids), Booking.status == BookingStatus.confirmed)
        .all()
    )
    total_revenue = sum(b.total_price for b in bookings)
    total_seats_sold = sum(len(b.seat_labels.split(",")) for b in bookings)

    return {
        "event": event.title,
        "shows": len(show_ids),
        "confirmed_bookings": len(bookings),
        "seats_sold": total_seats_sold,
        "total_revenue": total_revenue,
    }
