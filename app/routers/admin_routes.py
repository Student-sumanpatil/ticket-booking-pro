from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole, Venue, SeatCategory, Seat
from app.schemas import VenueCreate, VenueOut
from app.auth import require_role

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/venues", response_model=VenueOut)
def create_venue(
    payload: VenueCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    venue = Venue(name=payload.name, address=payload.address, created_by_id=admin.id)
    db.add(venue)
    db.flush()

    category_by_name = {}
    for cat in payload.seat_categories:
        category = SeatCategory(venue_id=venue.id, name=cat.name)
        db.add(category)
        db.flush()
        category_by_name[cat.name] = category.id

    for seat in payload.seats:
        if seat.category_name not in category_by_name:
            db.rollback()
            raise ValueError(f"Seat category '{seat.category_name}' was not declared")
        db.add(
            Seat(
                venue_id=venue.id,
                category_id=category_by_name[seat.category_name],
                row_label=seat.row_label,
                seat_number=seat.seat_number,
                label=f"{seat.row_label}{seat.seat_number}",
            )
        )

    db.commit()
    db.refresh(venue)
    return venue


@router.get("/venues", response_model=list[VenueOut])
def list_venues(db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):
    return db.query(Venue).all()
