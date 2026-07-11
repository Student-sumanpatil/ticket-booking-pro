from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.scheduler import start_scheduler
from app.routers import auth_routes, admin_routes, organiser_routes, customer_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    start_scheduler()
    yield


app = FastAPI(
    title="CineBook Ticket Booking API",
    description=(
        "Movie/concert ticket booking system with visual seat maps, "
        "TTL-based seat holds, concurrency-safe booking, and automatic "
        "waitlist reassignment. See /docs for interactive API docs."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(organiser_routes.router)
app.include_router(customer_routes.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse("app/static/index.html")
