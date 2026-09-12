import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from .models import CalendarItem, DaySchedule, item_adapter
from .scheduler import ScheduleConflict, schedule_items
from .seed import create_seed_items


class ItemNotFound(Exception):
    pass


class Repository:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY,
                    day TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS items_by_day ON items(day, position)")

    @contextmanager
    def connection(self, *, write: bool = False):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            if write:
                # Lock before reading so concurrent changes schedule against the latest day.
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _read(db: sqlite3.Connection, day: date) -> list[CalendarItem]:
        rows = db.execute("SELECT payload FROM items WHERE day = ? ORDER BY position", (day.isoformat(),)).fetchall()
        return [item_adapter.validate_json(row[0]) for row in rows]

    @staticmethod
    def _save(db: sqlite3.Connection, day: date, items: list[CalendarItem]) -> DaySchedule:
        # Rewrite only this day, within the same transaction as validation/scheduling.
        db.execute("DELETE FROM items WHERE day = ?", (day.isoformat(),))
        db.executemany("INSERT INTO items(id, day, position, payload) VALUES (?, ?, ?, ?)", [
            (item.id, day.isoformat(), position, item.model_dump_json(by_alias=True))
            for position, item in enumerate(items)
        ])
        return DaySchedule(date=day, items=items)

    @staticmethod
    def _find(db: sqlite3.Connection, item_id: str) -> CalendarItem:
        row = db.execute("SELECT payload FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise ItemNotFound("This item no longer exists. Reload your calendar.")
        return item_adapter.validate_json(row[0])

    def get_day(self, day: date) -> DaySchedule:
        with self.connection() as db:
            return DaySchedule(date=day, items=self._read(db, day))

    def add(self, item: CalendarItem) -> DaySchedule:
        with self.connection(write=True) as db:
            if db.execute("SELECT 1 FROM items WHERE id = ?", (item.id,)).fetchone():
                raise ScheduleConflict("An item with this ID already exists. Reload your calendar.")
            placed = schedule_items([*self._read(db, item.date), item])
            return self._save(db, item.date, placed)

    def pin(self, item_id: str, is_pinned: bool) -> DaySchedule:
        with self.connection(write=True) as db:
            item = self._find(db, item_id)
            items = self._read(db, item.date)
            for entry in items:
                if entry.id == item_id:
                    entry.is_pinned = is_pinned
            return self._save(db, item.date, schedule_items(items))

    def update(self, item_id: str, replacement: CalendarItem) -> DaySchedule:
        with self.connection(write=True) as db:
            current = self._find(db, item_id)
            if replacement.id != item_id:
                raise ScheduleConflict("The item ID cannot be changed.")
            if replacement.date != current.date:
                raise ScheduleConflict("Move items between days by deleting and recreating them.")
            items = [replacement if entry.id == item_id else entry for entry in self._read(db, current.date)]
            return self._save(db, current.date, schedule_items(items))

    def delete(self, item_id: str) -> DaySchedule:
        with self.connection(write=True) as db:
            item = self._find(db, item_id)
            db.execute("DELETE FROM items WHERE id = ?", (item_id,))
            return DaySchedule(date=item.date, items=self._read(db, item.date))

    def seed(self, day: date) -> DaySchedule:
        with self.connection(write=True) as db:
            if self._read(db, day):
                raise ScheduleConflict("Load a sample only into an empty day.")
            return self._save(db, day, schedule_items(create_seed_items(day)))
