import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .models import CalendarItem, DaySchedule, PinUpdate
from .repository import ItemNotFound, Repository
from .scheduler import ScheduleConflict

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "tetris.sqlite3"


def create_app(db_path: Path | None = None) -> FastAPI:
    repository = Repository(db_path if db_path is not None else Path(os.environ.get("TETRIS_DB_PATH", str(DEFAULT_DB))))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.initialize()
        yield

    app = FastAPI(title="Tetris API", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(ScheduleConflict)
    async def schedule_conflict(request: Request, exc: ScheduleConflict):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ItemNotFound)
    async def not_found(request: Request, exc: ItemNotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/day/{day}", response_model=DaySchedule)
    def get_day(day: date):
        return repository.get_day(day)

    @app.post("/api/items", response_model=DaySchedule, status_code=201)
    def add_item(item: CalendarItem):
        return repository.add(item)

    @app.patch("/api/items/{item_id}", response_model=DaySchedule)
    def pin_item(item_id: str, update: PinUpdate):
        return repository.pin(item_id, update.is_pinned)

    @app.put("/api/items/{item_id}", response_model=DaySchedule)
    def update_item(item_id: str, item: CalendarItem):
        return repository.update(item_id, item)

    @app.delete("/api/items/{item_id}", response_model=DaySchedule)
    def delete_item(item_id: str):
        return repository.delete(item_id)

    @app.post("/api/day/{day}/seed", response_model=DaySchedule, status_code=201)
    def seed_day(day: date):
        return repository.seed(day)

    return app


app = create_app()
