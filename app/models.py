import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean, UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return uuid.uuid4().hex


class UserRole(str, enum.Enum):
    admin = "admin"
    organiser = "organiser"
    customer = "customer"


class SeatStatus(str, enum.Enum):
    available = "available"
    held = "held"
    booked = "booked"


class BookingStatus(str, enum.Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"


class WaitlistStatus(str, enum.Enum):
    waiting = "waiting"
    offered = "offered"
    expired = "expired"
    fulfilled = "fulfilled"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.customer)
    created_at = Column(DateTime, default=datetime.utcnow)


class Venue(Base):
    __tablename__ = "venues"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"))

    seat_categories = relationship("SeatCategory", back_populates="venue", cascade="all, delete-orphan")
    seats = relationship("Seat", back_populates="venue", cascade="all, delete-orphan")


class SeatCategory(Base):
    """e.g. Premium, Standard, Balcony - scoped to a venue."""
    __tablename__ = "seat_categories"
    id = Column(Integer, primary_key=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    name = Column(String, nullable=False)

    venue = relationship("Venue", back_populates="seat_categories")


class Seat(Base):
    """A physical seat in a venue (row + number), assigned to one category."""
    __tablename__ = "seats"
    id = Column(Integer, primary_key=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("seat_categories.id"), nullable=False)
    row_label = Column(String, nullable=False)
    seat_number = Column(Integer, nullable=False)
    label = Column(String, nullable=False)  # e.g. "A1"

    venue = relationship("Venue", back_populates="seats")
    category = relationship("SeatCategory")

    __table_args__ = (UniqueConstraint("venue_id", "label", name="uq_seat_label_per_venue"),)


class Event(Base):
    """A movie or concert - the thing being advertised, independent of a specific showing."""
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    genre = Column(String, nullable=False)
    description = Column(String, nullable=False)
    organiser_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    shows = relationship("Show", back_populates="event", cascade="all, delete-orphan")


class Show(Base):
    """A specific date/time/venue instance of an event."""
    __tablename__ = "shows"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    show_date = Column(String, nullable=False)   # "2026-07-20"
    show_time = Column(String, nullable=False)   # "19:30"

    event = relationship("Event", back_populates="shows")
    venue = relationship("Venue")
    category_prices = relationship("ShowCategoryPrice", cascade="all, delete-orphan")
    show_seats = relationship("ShowSeat", back_populates="show", cascade="all, delete-orphan")


class ShowCategoryPrice(Base):
    """Per-show, per-category pricing set by the organiser."""
    __tablename__ = "show_category_prices"
    id = Column(Integer, primary_key=True)
    show_id = Column(Integer, ForeignKey("shows.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("seat_categories.id"), nullable=False)
    price = Column(Float, nullable=False)

    category = relationship("SeatCategory")

    __table_args__ = (UniqueConstraint("show_id", "category_id", name="uq_price_per_show_category"),)


class ShowSeat(Base):
    """
    The live, per-show status of one physical seat. This is the row that
    concurrency protection and TTL auto-release operate on.
    """
    __tablename__ = "show_seats"
    id = Column(Integer, primary_key=True)
    show_id = Column(Integer, ForeignKey("shows.id"), nullable=False)
    seat_id = Column(Integer, ForeignKey("seats.id"), nullable=False)

    status = Column(Enum(SeatStatus), nullable=False, default=SeatStatus.available)
    held_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    hold_token = Column(String, nullable=True)       # groups seats held together in one checkout
    hold_expires_at = Column(DateTime, nullable=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)

    show = relationship("Show", back_populates="show_seats")
    seat = relationship("Seat")

    __table_args__ = (UniqueConstraint("show_id", "seat_id", name="uq_show_seat"),)


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    show_id = Column(Integer, ForeignKey("shows.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seat_labels = Column(String, nullable=False)   # comma-separated, e.g. "A1,A2"
    total_price = Column(Float, nullable=False)
    booking_reference = Column(String, unique=True, nullable=False, default=gen_uuid)
    status = Column(Enum(BookingStatus), nullable=False, default=BookingStatus.confirmed)
    qr_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    show = relationship("Show")
    customer = relationship("User")


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    id = Column(Integer, primary_key=True)
    show_id = Column(Integer, ForeignKey("shows.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("seat_categories.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(WaitlistStatus), nullable=False, default=WaitlistStatus.waiting)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Populated when this entry is offered a specific freed-up seat
    offered_show_seat_id = Column(Integer, ForeignKey("show_seats.id"), nullable=True)
    offer_token = Column(String, nullable=True)
    offer_expires_at = Column(DateTime, nullable=True)

    show = relationship("Show")
    category = relationship("SeatCategory")
    customer = relationship("User")
