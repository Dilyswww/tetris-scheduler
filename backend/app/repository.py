import sqlite3
import math
import secrets
import time
from collections import OrderedDict
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import (
    CalendarItem,
    DEMO_START,
    DEMO_END,
    DEMO_TIME_ZONE,
    DemoClock,
    DemoClockUpdate,
    DaySchedule,
    EditOperation,
    FlexibleTask,
    FlexibleTaskDraft,
    FixedEventDraft,
    ExtendOperation,
    MoveOperation,
    Operation,
    PenaltyWeights,
    PreviewRequest,
    ProposalAlternative,
    ProposalMetrics,
    ProposalOptionsRequest,
    ProposalSet,
    SchedulePreview,
    ScheduleDay,
    ScheduleChange,
    FixedEvent,
    item_adapter,
)
from .scheduler import ScheduleConflict, SolverResult, format_slot, schedule_items
from .seed import create_debug_schedule, create_seed_items


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ItemNotFound(Exception):
    pass


class UndoUnavailable(Exception):
    pass


class Repository:
    def __init__(self, path: Path):
        self.path = path
        # Ephemeral proposals are bounded and never write to SQLite.
        self._previews: OrderedDict[str, tuple[float, dict[date, int], str, SchedulePreview, int, dict[date, int]]] = OrderedDict()
        self._proposal_sets: OrderedDict[str, tuple[float, dict[date, int], str, dict[date, int], ProposalSet, int]] = OrderedDict()
        self._preview_lock = Lock()

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
            db.execute("CREATE TABLE IF NOT EXISTS day_revisions (day TEXT PRIMARY KEY, revision INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS demo_clock (id INTEGER PRIMARY KEY CHECK (id = 1), now TEXT NOT NULL, revision INTEGER NOT NULL)")
            db.execute("""
                CREATE TABLE IF NOT EXISTS schedule_snapshots (
                    day TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

    @contextmanager
    def connection(self, *, write: bool = False):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            if write:
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
    def _has_snapshot(db: sqlite3.Connection, day: date) -> bool:
        return db.execute("SELECT 1 FROM schedule_snapshots WHERE day = ?", (day.isoformat(),)).fetchone() is not None

    @staticmethod
    def _revision(db: sqlite3.Connection, day: date) -> int:
        row = db.execute("SELECT revision FROM day_revisions WHERE day = ?", (day.isoformat(),)).fetchone()
        return row[0] if row else 0

    @staticmethod
    def _clock(db: sqlite3.Connection) -> DemoClock:
        row = db.execute("SELECT now, revision FROM demo_clock WHERE id = 1").fetchone()
        return DemoClock(now=datetime.fromisoformat(row[0]) if row else datetime(2026, 9, 11, 8), revision=row[1] if row else 0)

    def get_clock(self) -> DemoClock:
        with self.connection() as db:
            return self._clock(db)

    def start_demo(self) -> DemoClock:
        with self.connection(write=True) as db:
            db.execute("INSERT OR IGNORE INTO demo_clock(id, now, revision) VALUES (1, '2026-09-11T08:00:00', 1)")
            return self._clock(db)

    def set_clock(self, update: DemoClockUpdate) -> DemoClock:
        with self.connection(write=True) as db:
            current = self._clock(db)
            if current.revision and current.now == update.now:
                return current
            db.execute("""INSERT INTO demo_clock(id, now, revision) VALUES (1, ?, 1)
                ON CONFLICT(id) DO UPDATE SET now = excluded.now, revision = revision + 1""", (update.now.isoformat(),))
            return self._clock(db)

    @classmethod
    def _save(
        cls,
        db: sqlite3.Connection,
        day: date,
        items: list[CalendarItem],
        *,
        changes: list[ScheduleChange] | None = None,
        solver_status: str | None = None,
    ) -> DaySchedule:
        db.execute("DELETE FROM items WHERE day = ?", (day.isoformat(),))
        db.executemany("INSERT INTO items(id, day, position, payload) VALUES (?, ?, ?, ?)", [
            (item.id, day.isoformat(), position, item.model_dump_json(by_alias=True))
            for position, item in enumerate(items)
        ])
        db.execute("""INSERT INTO day_revisions(day, revision) VALUES (?, 1)
                   ON CONFLICT(day) DO UPDATE SET revision = revision + 1""", (day.isoformat(),))
        return DaySchedule(
            date=day,
            items=items,
            changes=changes or [],
            can_undo=cls._has_snapshot(db, day),
            solver_status=solver_status,
        )

    @staticmethod
    def _find(items: list[CalendarItem], item_id: str) -> CalendarItem:
        item = next((entry for entry in items if entry.id == item_id), None)
        if item is None:
            raise ItemNotFound("This item no longer exists. Reload your calendar.")
        return item

    @staticmethod
    def _clear_snapshot(db: sqlite3.Connection, day: date) -> None:
        db.execute("DELETE FROM schedule_snapshots WHERE day = ?", (day.isoformat(),))

    @staticmethod
    def _scope(day: date) -> list[date]:
        return [DEMO_START + timedelta(days=i) for i in range(3)] if DEMO_START <= day <= DEMO_END else [day]

    def _window(self, db: sqlite3.Connection, day: date, time_zone: str = DEMO_TIME_ZONE):
        days = self._scope(day)
        items = [item for current in days for item in self._read(db, current)]
        revisions = {current: self._revision(db, current) for current in days}
        cutoffs = {current: self._cutoff(current, time_zone, db, allow_past=True) for current in days}
        return days, items, revisions, cutoffs

    @staticmethod
    def _locked(items: list[CalendarItem], cutoffs: dict[date, int]) -> frozenset[str]:
        return frozenset(item.id for item in items if item.start_slot is not None and item.start_slot < cutoffs[item.date])

    @staticmethod
    def _response(day: date, days: list[date], items: list[CalendarItem], *, changes=None, can_undo=False, solver_status=None) -> DaySchedule:
        return DaySchedule(date=day, items=[item for item in items if item.date == day], changes=changes or [],
            can_undo=can_undo, solver_status=solver_status,
            days=[ScheduleDay(date=current, items=[item for item in items if item.date == current]) for current in days])

    def _clear_window_snapshots(self, db: sqlite3.Connection, days: list[date]) -> None:
        for current in days:
            self._clear_snapshot(db, current)

    def _save_window(self, db: sqlite3.Connection, day: date, days: list[date], items: list[CalendarItem], *, changes=None, solver_status=None) -> DaySchedule:
        # Delete all source rows before inserting destinations: IDs are global,
        # and tasks may swap days in the same transaction.
        for current in days:
            db.execute("DELETE FROM items WHERE day = ?", (current.isoformat(),))
        for current in days:
            self._save(db, current, [item for item in items if item.date == current])
        return self._response(day, days, items, changes=changes, solver_status=solver_status, can_undo=self._has_snapshot(db, day))

    def _snapshot_window(self, db: sqlite3.Connection, day: date, days: list[date]) -> None:
        before = [item for current in days for item in self._read(db, current)]
        payload = self._response(day, days, before).model_dump_json(by_alias=True)
        for current in days:
            db.execute("INSERT OR REPLACE INTO schedule_snapshots(day, payload) VALUES (?, ?)", (current.isoformat(), payload))

    @staticmethod
    def _duration(slots: int) -> str:
        minutes = slots * 30
        return f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 and minutes % 60 else f"{minutes // 60}h" if minutes >= 60 else f"{minutes}m"

    @classmethod
    def _reschedule_changes(
        cls,
        before: list[CalendarItem],
        result: SolverResult,
        target_id: str,
        operation: Operation,
    ) -> list[ScheduleChange]:
        old_by_id = {item.id: item for item in before}
        new_by_id = {item.id: item for item in result.items}
        target_before = old_by_id[target_id]
        target_after = new_by_id[target_id]
        target_change_type = "extended" if isinstance(operation, ExtendOperation) else "edited" if isinstance(operation, EditOperation) else "moved"
        target_reason = (
            f"Extended by {cls._duration(operation.additional_slots)} because you reported running late."
            if isinstance(operation, ExtendOperation)
            else "Updated this item's details and re-optimized the eligible schedule."
            if isinstance(operation, EditOperation)
            else "Moved to the time you selected."
        )
        changes = [ScheduleChange(
            item_id=target_id,
            title=target_after.title,
            change_type=target_change_type,
            from_start_slot=target_before.start_slot,
            to_start_slot=target_after.start_slot,
            from_duration_slots=target_before.duration_slots,
            to_duration_slots=target_after.duration_slots,
            from_date=target_before.date, to_date=target_after.date,
            reason=target_reason,
        )]
        for old in before:
            if old.id == target_id:
                continue
            new = new_by_id[old.id]
            if (old.date, old.start_slot) == (new.date, new.start_slot):
                continue
            if new.start_slot is None:
                assert isinstance(new, FlexibleTask)
                change_type = "deferred"
                reason = (
                    f"Left unscheduled in this proposal to respect protected time and the "
                    f"{new.deadline_date} {format_slot(new.deadline_slot)} deadline while prioritizing fewer deferrals."
                )
            elif old.start_slot is None:
                change_type = "scheduled"
                reason = f"A valid gap became available at {format_slot(new.start_slot)}."
            else:
                change_type = "moved"
                reason = (
                    f"Moved as part of making room for {target_before.title} "
                    "while protecting fixed, pinned, and started items and minimizing other changes."
                )
            changes.append(ScheduleChange(
                item_id=old.id,
                title=old.title,
                change_type=change_type,
                from_start_slot=old.start_slot,
                to_start_slot=new.start_slot,
                from_duration_slots=old.duration_slots,
                to_duration_slots=new.duration_slots,
                from_date=old.date, to_date=new.date,
                reason=reason,
            ))
        return changes

    @classmethod
    def _addition_changes(
        cls, before: list[CalendarItem], result: SolverResult, added: CalendarItem,
    ) -> list[ScheduleChange]:
        new_by_id = {item.id: item for item in result.items}
        changes = [ScheduleChange(
            item_id=added.id, title=added.title, change_type="added" if added.start_slot is not None else "deferred",
            from_start_slot=None, to_start_slot=added.start_slot,
            from_duration_slots=None, to_duration_slots=added.duration_slots,
            to_date=added.date,
            reason=(f"Added on {added.date} at {format_slot(added.start_slot)} in this proposal." if added.start_slot is not None else "Left unscheduled in this plan because a continuous placement within one day could not be assigned before the deadline."),
        )]
        for old in before:
            new = new_by_id[old.id]
            if (old.date, old.start_slot) == (new.date, new.start_slot):
                continue
            if new.start_slot is None:
                change_type = "deferred"
                reason = f"Deferred to make room for {added.title} while respecting its deadline."
            elif old.start_slot is None:
                change_type = "scheduled"
                reason = f"A valid gap became available at {format_slot(new.start_slot)}."
            else:
                change_type = "moved"
                reason = f"Moved to make room for {added.title} while minimizing disruption."
            changes.append(ScheduleChange(
                item_id=old.id, title=old.title, change_type=change_type,
                from_start_slot=old.start_slot, to_start_slot=new.start_slot,
                from_duration_slots=old.duration_slots, to_duration_slots=new.duration_slots,
                from_date=old.date, to_date=new.date,
                reason=reason,
            ))
        return changes

    @staticmethod
    def _proposal_metrics(before: list[CalendarItem], result: SolverResult) -> ProposalMetrics:
        old_by_id = {item.id: item for item in before}
        moved = 0
        shift = 0
        deferred = 0
        day_changes = 0
        for item in result.items:
            old = old_by_id.get(item.id)
            if old is None:
                continue
            if item.start_slot is None and old.start_slot is not None:
                deferred += 1
            elif old.start_slot is not None and item.start_slot is not None and (old.date, old.start_slot) != (item.date, item.start_slot):
                moved += 1
                shift += abs((item.date - old.date).days * 48 + item.start_slot - old.start_slot)
                day_changes += int(item.date != old.date)
        return ProposalMetrics(moved_task_count=moved, total_shift_slots=shift, deferred_task_count=deferred, day_change_count=day_changes)

    def get_day(self, day: date) -> DaySchedule:
        with self.connection() as db:
            return DaySchedule(date=day, items=self._read(db, day), can_undo=self._has_snapshot(db, day))

    def _mutate_existing(self, db: sqlite3.Connection, day: date, items: list[CalendarItem]) -> DaySchedule:
        days, _, _, cutoffs = self._window(db, day)
        result = schedule_items(items, days=days, earliest_starts=cutoffs, locked_ids=self._locked(items, cutoffs))
        # Direct mutations (edit, pin/unpin, and delete) use the same one-level
        # Undo contract as optimizer commits. Take the snapshot only after the
        # solver succeeds, so a rejected mutation leaves the existing Undo
        # checkpoint untouched. The surrounding transaction also makes the
        # snapshot and the schedule write atomic.
        self._snapshot_window(db, day, days)
        return self._save_window(db, day, days, result.items, solver_status=result.status)

    def add(self, item: CalendarItem, time_zone: str = "UTC") -> DaySchedule:
        with self.connection(write=True) as db:
            days, existing, _, cutoffs = self._window(db, item.date, time_zone)
            if db.execute("SELECT 1 FROM items WHERE id = ?", (item.id,)).fetchone():
                raise ScheduleConflict("An item with this ID already exists. Reload your calendar.")
            cutoff = self._cutoff(item.date, time_zone, db)
            if (item.kind == "fixed" or item.is_pinned) and item.start_slot is not None and item.start_slot < cutoff:
                raise ScheduleConflict("New fixed or pinned items must start at a time that has not elapsed.")
            result = schedule_items([*existing, item], days=days, earliest_starts=cutoffs, locked_ids=self._locked(existing, cutoffs))
            added = self._find(result.items, item.id)
            self._clear_window_snapshots(db, days)
            return self._save_window(db, item.date, days, result.items,
                changes=self._addition_changes(existing, result, added), solver_status=result.status)

    def pin(self, item_id: str, is_pinned: bool) -> DaySchedule:
        with self.connection(write=True) as db:
            row = db.execute("SELECT day FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                raise ItemNotFound("This item no longer exists. Reload your calendar.")
            day = date.fromisoformat(row[0])
            _, items, _, _ = self._window(db, day)
            item = self._find(items, item_id)
            if is_pinned and item.start_slot is None:
                raise ScheduleConflict("A deferred task must be scheduled before it can be pinned.")
            item.is_pinned = is_pinned
            return self._mutate_existing(db, day, items)

    def update(self, item_id: str, replacement: CalendarItem) -> DaySchedule:
        with self.connection(write=True) as db:
            row = db.execute("SELECT day FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                raise ItemNotFound("This item no longer exists. Reload your calendar.")
            day = date.fromisoformat(row[0])
            _, current_items, _, _ = self._window(db, day)
            if replacement.id != item_id:
                raise ScheduleConflict("The item ID cannot be changed.")
            if replacement.date != day:
                raise ScheduleConflict("Use Move task to preview a change of day.")
            items = [replacement if entry.id == item_id else entry for entry in current_items]
            return self._mutate_existing(db, day, items)

    def delete(self, item_id: str) -> DaySchedule:
        with self.connection(write=True) as db:
            row = db.execute("SELECT day FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                raise ItemNotFound("This item no longer exists. Reload your calendar.")
            day = date.fromisoformat(row[0])
            _, items, _, _ = self._window(db, day)
            return self._mutate_existing(db, day, [item for item in items if item.id != item_id])

    def seed(self, day: date) -> DaySchedule:
        with self.connection(write=True) as db:
            if self._read(db, day):
                raise ScheduleConflict("Load a sample only into an empty day.")
            result = schedule_items(create_seed_items(day))
            self._clear_window_snapshots(db, self._scope(day))
            return self._save(db, day, result.items, solver_status=result.status)

    def reset_debug_schedule(self, day: date) -> DaySchedule:
        if not DEMO_START <= day <= DEMO_END:
            raise ScheduleConflict("The debug schedule covers September 11–13, 2026.")
        days = self._scope(day)
        items = create_debug_schedule()
        with self.connection(write=True) as db:
            self._clear_window_snapshots(db, days)
            return self._save_window(db, day, days, items)

    def _cutoff(self, day: date, time_zone: str, db: sqlite3.Connection | None = None, *, allow_past: bool = False) -> int:
        if db is None:
            with self.connection() as connection:
                return self._cutoff(day, time_zone, connection, allow_past=allow_past)
        try:
            requested_zone = ZoneInfo(time_zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ScheduleConflict("Choose a valid IANA time zone, such as America/New_York.")
        clock = self._clock(db)
        if clock.revision:
            if not DEMO_START <= day <= DEMO_END:
                raise ScheduleConflict("The demo calendar covers September 11–13, 2026.")
            now = clock.now.replace(tzinfo=ZoneInfo(DEMO_TIME_ZONE))
        else:
            now = utc_now().astimezone(requested_zone)
        if day < now.date():
            if allow_past:
                return 32
            raise ScheduleConflict("Past days cannot be rescheduled.")
        if day > now.date():
            return 0
        minutes = now.hour * 60 + now.minute + now.second / 60 + now.microsecond / 60_000_000
        return min(32, max(0, math.ceil((minutes - 8 * 60) / 30)))

    def preview(self, request: PreviewRequest) -> SchedulePreview:
        operation = request.operation
        item_id = operation.item.id if isinstance(operation, EditOperation) else operation.item_id
        with self.connection() as db:
            # Keep items and revision in the same read snapshot.
            db.execute("BEGIN")
            row = db.execute("SELECT day FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                raise ItemNotFound("This item no longer exists. Reload your calendar.")
            day = date.fromisoformat(row[0])
            days, before, revisions, cutoffs = self._window(db, day, request.time_zone)
            can_undo = self._has_snapshot(db, day)
            target_day = (operation.target_date or day) if isinstance(operation, MoveOperation) else day
            if target_day not in days:
                raise ScheduleConflict("Choose a day in the three-day demo window.")
            cutoff = cutoffs[target_day] if isinstance(operation, EditOperation) else self._cutoff(target_day, request.time_zone, db)
            clock_revision = self._clock(db).revision
        proposed = [item.model_copy(deep=True) for item in before]
        target = self._find(proposed, item_id)
        # There is no completion tracking yet: preserve elapsed work unless the
        # user explicitly moves that flexible task to a future slot.
        locked = set(self._locked(before, cutoffs))
        if isinstance(operation, MoveOperation):
            if not isinstance(target, FlexibleTask) or target.is_pinned:
                raise ScheduleConflict("Only unpinned flexible tasks can be dragged.")
            if (target.date, target.start_slot) == (target_day, operation.target_start_slot):
                raise ScheduleConflict("This task is already at that time. Choose a different slot.")
            if operation.target_start_slot < cutoff:
                raise ScheduleConflict("Choose a time that has not elapsed.")
            locked.discard(target.id)
            target.start_slot = operation.target_start_slot
            target.date = target_day
        elif isinstance(operation, ExtendOperation):
            if target.start_slot is None:
                raise ScheduleConflict("A deferred task cannot run late because it is not on the calendar.")
            target.duration_slots += operation.additional_slots
            if target.start_slot + target.duration_slots < cutoff:
                raise ScheduleConflict("The extension must reach the current time or later.")
        else:
            replacement = operation.item.model_copy(deep=True)
            if replacement.date != day:
                raise ScheduleConflict("Use Move task to preview a change of day.")
            proposed = [replacement if item.id == item_id else item for item in proposed]
            target = replacement
            # Match the direct-edit rules: completed/started work remains fixed,
            # while future unpinned flexible work may be re-optimized.
            locked = set(self._locked(proposed, cutoffs))
        if not isinstance(operation, EditOperation):
            assert target.start_slot is not None
            latest_end = target.deadline_slot if isinstance(target, FlexibleTask) and target.date == target.deadline_date else 32
            if target.start_slot + target.duration_slots > latest_end:
                raise ScheduleConflict(f'“{target.title}” would finish after {format_slot(latest_end)}.')
            locked.add(target.id)
        penalties = (
            PenaltyWeights(moved_task=8, displacement_slot=2, largest_displacement_slot=0)
            if isinstance(operation, (ExtendOperation, EditOperation)) else PenaltyWeights()
        )
        if request.penalties is not None:
            penalties = penalties.model_copy(update=request.penalties.model_dump(exclude_unset=True))
        result = schedule_items(proposed, days=days, locked_ids=frozenset(locked), earliest_starts=cutoffs, penalties=penalties)
        preview = SchedulePreview(
            preview_token=secrets.token_urlsafe(32), expires_in_seconds=120,
            operation=operation, earliest_start_slot=cutoff, penalties=penalties,
            schedule=self._response(day, days, result.items,
                changes=self._reschedule_changes(before, result, target.id, operation),
                can_undo=can_undo, solver_status=result.status),
        )
        with self._preview_lock:
            self._previews[preview.preview_token] = (time.monotonic() + 120, revisions, request.time_zone, preview, clock_revision, cutoffs)
            while len(self._previews) > 256:
                self._previews.popitem(last=False)
        return preview

    def commit(self, token: str) -> DaySchedule:
        with self._preview_lock:
            cached = self._previews.get(token)
        if cached is None or cached[0] <= time.monotonic():
            raise ScheduleConflict("This preview expired. Preview the adjustment again.")
        expires, revisions, time_zone, preview, clock_revision, cutoffs = cached
        day = preview.schedule.date
        with self.connection(write=True) as db:
            if expires <= time.monotonic():
                raise ScheduleConflict("This preview expired. Preview the adjustment again.")
            if any(self._revision(db, current) != revision for current, revision in revisions.items()):
                raise ScheduleConflict("Your calendar changed. Reload it and preview the adjustment again.")
            if self._clock(db).revision != clock_revision:
                raise ScheduleConflict("The demo clock changed. Preview the adjustment again.")
            if any(self._cutoff(current, time_zone, db, allow_past=True) != cutoff for current, cutoff in cutoffs.items()):
                raise ScheduleConflict("Time has advanced. Preview the adjustment again.")
            days = list(revisions)
            self._snapshot_window(db, day, days)
            saved = self._save_window(db, day, days, [item for plan in preview.schedule.days for item in plan.items],
                               changes=preview.schedule.changes, solver_status=preview.schedule.solver_status)
        with self._preview_lock:
            self._previews.pop(token, None)
        return saved

    def proposals(self, request: ProposalOptionsRequest) -> ProposalSet:
        draft = request.item
        with self.connection() as db:
            db.execute("BEGIN")
            days, before, revisions, cutoffs = self._window(db, draft.date, request.time_zone)
            can_undo = self._has_snapshot(db, draft.date)
            cutoff = self._cutoff(draft.date, request.time_zone, db)
            clock_revision = self._clock(db).revision
        if any(item.id == draft.id for item in before):
            raise ScheduleConflict("An item with this ID already exists. Reload your calendar.")
        locked = self._locked(before, cutoffs)
        solved: list[tuple[SolverResult, CalendarItem]] = []
        if isinstance(draft, FixedEventDraft):
            for start in request.candidate_start_slots or []:
                if start < cutoff or start + draft.duration_slots > 32:
                    continue
                added = FixedEvent(
                    id=draft.id, title=draft.title, date=draft.date, kind="fixed",
                    start_slot=start, duration_slots=draft.duration_slots,
                    is_pinned=False, accent=draft.accent, note=draft.note,
                )
                try:
                    result = schedule_items([*before, added], days=days, locked_ids=locked, earliest_starts=cutoffs)
                except ScheduleConflict:
                    continue
                solved.append((result, added))
        else:
            assert isinstance(draft, FlexibleTaskDraft)
            added = FlexibleTask(
                id=draft.id, title=draft.title, date=draft.date, kind="flexible",
                start_slot=None, duration_slots=draft.duration_slots,
                deadline_slot=draft.deadline_slot, is_pinned=False,
                earliest_date=draft.earliest_date, deadline_date=draft.deadline_date,
                accent=draft.accent, note=draft.note,
            )
            try:
                first = schedule_items(
                    [*before, added], days=days, locked_ids=locked,
                    required_ids=frozenset({added.id}), earliest_starts=cutoffs,
                )
            except ScheduleConflict:
                first = None
            if first is not None:
                first_added = next(item for item in first.items if item.id == added.id)
                assert first_added.start_slot is not None
                solved.append((first, first_added))
                try:
                    second = schedule_items(
                        [*before, added], days=days, locked_ids=locked,
                        required_ids=frozenset({added.id}),
                        forbidden_placements={added.id: frozenset({(first_added.date, first_added.start_slot)})},
                        earliest_starts=cutoffs,
                    )
                except ScheduleConflict:
                    second = None
                if second is not None:
                    second_added = next(item for item in second.items if item.id == added.id)
                    solved.append((second, second_added))

        alternatives: list[ProposalAlternative] = []
        for result, added in sorted(solved, key=lambda option: option[0].objective_value):
            assert added.start_slot is not None
            metrics = self._proposal_metrics(before, result)
            changes = self._addition_changes(before, result, added)
            alternatives.append(ProposalAlternative(
                id=secrets.token_urlsafe(12), label="Alternative",
                start_slot=added.start_slot, date=added.date, metrics=metrics,
                schedule=self._response(
                    draft.date, days, result.items, changes=changes,
                    can_undo=can_undo, solver_status=result.status,
                ),
            ))
        if not alternatives:
            raise ScheduleConflict("No schedule option can place this item without moving protected items.")
        for index, alternative in enumerate(alternatives):
            alternative.label = "Recommended" if index == 0 else f"Alternative on {alternative.date} at {format_slot(alternative.start_slot)}"
        proposal_set = ProposalSet(
            proposal_set_id=secrets.token_urlsafe(24), expires_in_seconds=120,
            date=draft.date, alternatives=alternatives,
        )
        with self._preview_lock:
            self._proposal_sets[proposal_set.proposal_set_id] = (
                time.monotonic() + 120, revisions, request.time_zone, cutoffs, proposal_set, clock_revision,
            )
            while len(self._proposal_sets) > 256:
                self._proposal_sets.popitem(last=False)
        return proposal_set

    def accept_proposal(self, proposal_set_id: str, alternative_id: str) -> DaySchedule:
        with self._preview_lock:
            cached = self._proposal_sets.get(proposal_set_id)
        if cached is None or cached[0] <= time.monotonic():
            raise ScheduleConflict("These schedule options expired. Generate new options.")
        expires, revisions, time_zone, cutoffs, proposal_set, clock_revision = cached
        alternative = next((item for item in proposal_set.alternatives if item.id == alternative_id), None)
        if alternative is None:
            raise ScheduleConflict("Choose an option from this proposal set.")
        with self.connection(write=True) as db:
            if expires <= time.monotonic():
                raise ScheduleConflict("These schedule options expired. Generate new options.")
            if any(self._revision(db, current) != revision for current, revision in revisions.items()):
                raise ScheduleConflict("Your calendar changed. Reload it and generate new options.")
            if self._clock(db).revision != clock_revision:
                raise ScheduleConflict("The demo clock changed. Generate new options again.")
            if any(self._cutoff(current, time_zone, db, allow_past=True) != cutoff for current, cutoff in cutoffs.items()):
                raise ScheduleConflict("Time has advanced. Generate new options again.")
            days = list(revisions)
            self._snapshot_window(db, proposal_set.date, days)
            saved = self._save_window(
                db, proposal_set.date, days, [item for plan in alternative.schedule.days for item in plan.items],
                changes=alternative.schedule.changes,
                solver_status=alternative.schedule.solver_status,
            )
        with self._preview_lock:
            self._proposal_sets.pop(proposal_set_id, None)
        return saved

    def reschedule(self, item_id: str, additional_slots: int, time_zone: str = "UTC") -> DaySchedule:
        """Compatibility endpoint; the UI uses explicit preview/commit instead."""
        preview = self.preview(PreviewRequest(time_zone=time_zone,
            operation=ExtendOperation(type="extend", item_id=item_id, additional_slots=additional_slots)))
        return self.commit(preview.preview_token)

    def undo(self, day: date) -> DaySchedule:
        with self.connection(write=True) as db:
            row = db.execute("SELECT payload FROM schedule_snapshots WHERE day = ?", (day.isoformat(),)).fetchone()
            if row is None:
                raise UndoUnavailable("There is no reschedule to undo for this day.")
            snapshot_plan = DaySchedule.model_validate_json(row[0])
            days = [plan.date for plan in snapshot_plan.days] or [day]
            current = [item for current_day in days for item in self._read(db, current_day)]
            snapshot = [item for plan in snapshot_plan.days for item in plan.items] if snapshot_plan.days else snapshot_plan.items
            old_by_id = {item.id: item for item in current}
            changes = [ScheduleChange(
                item_id=item.id,
                title=item.title,
                change_type="restored",
                from_start_slot=old_by_id[item.id].start_slot,
                to_start_slot=item.start_slot,
                from_duration_slots=old_by_id[item.id].duration_slots,
                to_duration_slots=item.duration_slots,
                from_date=old_by_id[item.id].date, to_date=item.date,
                reason="Restored the schedule from before the last adjustment across the affected days.",
            ) for item in snapshot if item.id in old_by_id and old_by_id[item.id] != item]
            self._clear_window_snapshots(db, days)
            return self._save_window(db, day, days, snapshot, changes=changes)
