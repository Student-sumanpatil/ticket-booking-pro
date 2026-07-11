from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.models import UserRole, SeatStatus, BookingStatus, WaitlistStatus


# ---------- Auth ----------
class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: UserRole = UserRole.customer


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: UserRole

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Venue / seating ----------
class SeatCategoryIn(BaseModel):
    name: str


class SeatIn(BaseModel):
    row_label: str
    seat_number: int
    category_name: str


class VenueCreate(BaseModel):
    name: str
    address: str
    seat_categories: List[SeatCategoryIn]
    seats: List[SeatIn]


class VenueOut(BaseModel):
    id: int
    name: str
    address: str

    class Config:
        from_attributes = True


# ---------- Events / shows ----------
class EventCreate(BaseModel):
    title: str
    genre: str
    description: str


class CategoryPriceIn(BaseModel):
    category_name: str
    price: float


class ShowCreate(BaseModel):
    event_id: int
    venue_id: int
    show_date: str
    show_time: str
    category_prices: List[CategoryPriceIn]


class ShowOut(BaseModel):
    id: int
    show_date: str
    show_time: str
    venue_id: int

    class Config:
        from_attributes = True


# ---------- Seat map ----------
class SeatMapEntry(BaseModel):
    show_seat_id: int
    label: str
    category: str
    price: float
    status: SeatStatus
    held_by_me: bool = False


# ---------- Holds / booking ----------
class HoldRequest(BaseModel):
    show_id: int
    seat_labels: List[str]


class HoldOut(BaseModel):
    hold_token: str
    expires_at: datetime
    seat_labels: List[str]
    total_price: float


class BookingConfirmRequest(BaseModel):
    hold_token: str


class BookingOut(BaseModel):
    id: int
    booking_reference: str
    seat_labels: str
    total_price: float
    status: BookingStatus
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Waitlist ----------
class WaitlistJoinRequest(BaseModel):
    show_id: int
    category_name: str


class WaitlistOut(BaseModel):
    id: int
    status: WaitlistStatus
    created_at: datetime

    class Config:
        from_attributes = True
