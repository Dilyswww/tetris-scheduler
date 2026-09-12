import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from .models import CalendarItem, CommitRequest, DaySchedule, PinUpdate, PreviewRequest, RescheduleRequest, SchedulePreview
from .repository import ItemNotFound, Repository, UndoUnavailable
from .scheduler import ScheduleConflict, SolverUnavailable

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

    @app.exception_handler(UndoUnavailable)
    async def undo_unavailable(request: Request, exc: UndoUnavailable):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(SolverUnavailable)
    async def solver_unavailable(request: Request, exc: SolverUnavailable):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/day/{day}", response_model=DaySchedule)
    def get_day(day: date):
        return repository.get_day(day)

    @app.post("/api/items", response_model=DaySchedule, status_code=201)
    def add_item(item: CalendarItem, time_zone: str = Query(default="UTC", alias="timeZone", min_length=1, max_length=100)):
        return repository.add(item, time_zone)

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

    @app.post("/api/optimizer/preview", response_model=SchedulePreview)
    def preview(update: PreviewRequest):
        return repository.preview(update)

    @app.post("/api/optimizer/commit", response_model=DaySchedule)
    def commit(update: CommitRequest):
        return repository.commit(update.preview_token)

    @app.post("/api/reschedule", response_model=DaySchedule, deprecated=True)
    def reschedule(update: RescheduleRequest):
        return repository.reschedule(update.item_id, update.additional_slots, update.time_zone)

    @app.post("/api/day/{day}/undo", response_model=DaySchedule)
    def undo(day: date):
        return repository.undo(day)

    return app


app = create_app()
