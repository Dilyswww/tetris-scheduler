import sqlite3
import math
import secrets
import time
from collections import OrderedDict
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import (
    CalendarItem,
    DaySchedule,
    FlexibleTask,
    FlexibleTaskDraft,
    FixedEventDraft,
    ExtendOperation,
    MoveOperation,
    Operation,
    PreviewRequest,
    ProposalAlternative,
    ProposalMetrics,
    ProposalOptionsRequest,
    ProposalSet,
    SchedulePreview,
    ScheduleChange,
    FixedEvent,
    item_adapter,
)
from .scheduler import ScheduleConflict, SolverResult, format_slot, schedule_items
from .seed import create_seed_items


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
        self._previews: OrderedDict[str, tuple[float, int, str, SchedulePreview]] = OrderedDict()
        self._proposal_sets: OrderedDict[str, tuple[float, int, str, int, ProposalSet]] = OrderedDict()
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
    def _store_snapshot(db: sqlite3.Connection, day: date, items: list[CalendarItem]) -> None:
        payload = DaySchedule(date=day, items=items).model_dump_json(by_alias=True)
        db.execute(
            "INSERT OR REPLACE INTO schedule_snapshots(day, payload) VALUES (?, ?)",
            (day.isoformat(), payload),
        )

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
        changes = [ScheduleChange(
            item_id=target_id,
            title=target_before.title,
            change_type="extended" if isinstance(operation, ExtendOperation) else "moved",
            from_start_slot=target_before.start_slot,
            to_start_slot=target_after.start_slot,
            from_duration_slots=target_before.duration_slots,
            to_duration_slots=target_after.duration_slots,
            reason=(f"Extended by {cls._duration(operation.additional_slots)} because you reported running late."
                    if isinstance(operation, ExtendOperation) else "Moved to the time you selected."),
        )]
        for old in before:
            if old.id == target_id:
                continue
            new = new_by_id[old.id]
            if old.start_slot == new.start_slot:
                continue
            if new.start_slot is None:
                assert isinstance(new, FlexibleTask)
                change_type = "deferred"
                reason = (
                    f"Left unscheduled in this proposal to respect protected time and the "
                    f"{format_slot(new.deadline_slot)} deadline while prioritizing fewer deferrals."
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
                reason=reason,
            ))
        return changes

    @classmethod
    def _addition_changes(
        cls, before: list[CalendarItem], result: SolverResult, added: CalendarItem,
    ) -> list[ScheduleChange]:
        assert added.start_slot is not None
        new_by_id = {item.id: item for item in result.items}
        changes = [ScheduleChange(
            item_id=added.id, title=added.title, change_type="added",
            from_start_slot=None, to_start_slot=added.start_slot,
            from_duration_slots=None, to_duration_slots=added.duration_slots,
            reason=f"Added at {format_slot(added.start_slot)} in this proposal.",
        )]
        for old in before:
            new = new_by_id[old.id]
            if old.start_slot == new.start_slot:
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
                reason=reason,
            ))
        return changes

    @staticmethod
    def _proposal_metrics(before: list[CalendarItem], result: SolverResult) -> ProposalMetrics:
        old_by_id = {item.id: item for item in before}
        moved = 0
        shift = 0
        deferred = 0
        for item in result.items:
            old = old_by_id.get(item.id)
            if old is None:
                continue
            if item.start_slot is None and old.start_slot is not None:
                deferred += 1
            elif old.start_slot is not None and item.start_slot is not None and old.start_slot != item.start_slot:
                moved += 1
                shift += abs(item.start_slot - old.start_slot)
        return ProposalMetrics(moved_task_count=moved, total_shift_slots=shift, deferred_task_count=deferred)

    def get_day(self, day: date) -> DaySchedule:
        with self.connection() as db:
            return DaySchedule(date=day, items=self._read(db, day), can_undo=self._has_snapshot(db, day))

    def add(self, item: CalendarItem, time_zone: str = "UTC") -> DaySchedule:
        with self.connection(write=True) as db:
            existing = self._read(db, item.date)
            if any(entry.id == item.id for entry in existing):
                raise ScheduleConflict("An item with this ID already exists. Reload your calendar.")
            cutoff = self._cutoff(item.date, time_zone)
            if (item.kind == "fixed" or item.is_pinned) and item.start_slot is not None and item.start_slot < cutoff:
                raise ScheduleConflict("New fixed or pinned items must start at a time that has not elapsed.")
            locked = frozenset(entry.id for entry in existing if entry.start_slot is not None and entry.start_slot < cutoff)
            result = schedule_items([*existing, item], locked_ids=locked, earliest_start_slot=cutoff)
            self._clear_snapshot(db, item.date)
            return self._save(db, item.date, result.items, solver_status=result.status)

    def pin(self, item_id: str, is_pinned: bool) -> DaySchedule:
        with self.connection(write=True) as db:
            row = db.execute("SELECT day FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                raise ItemNotFound("This item no longer exists. Reload your calendar.")
            day = date.fromisoformat(row[0])
            items = self._read(db, day)
            item = self._find(items, item_id)
            if is_pinned and item.start_slot is None:
                raise ScheduleConflict("A deferred task must be scheduled before it can be pinned.")
            item.is_pinned = is_pinned
            result = schedule_items(items)
            self._clear_snapshot(db, day)
            return self._save(db, day, result.items, solver_status=result.status)

    def update(self, item_id: str, replacement: CalendarItem) -> DaySchedule:
        with self.connection(write=True) as db:
            row = db.execute("SELECT day FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                raise ItemNotFound("This item no longer exists. Reload your calendar.")
            day = date.fromisoformat(row[0])
            current_items = self._read(db, day)
            current = self._find(current_items, item_id)
            if replacement.id != item_id:
                raise ScheduleConflict("The item ID cannot be changed.")
            if replacement.date != current.date:
                raise ScheduleConflict("Move items between days by deleting and recreating them.")
            items = [replacement if entry.id == item_id else entry for entry in current_items]
            result = schedule_items(items)
            self._clear_snapshot(db, day)
            return self._save(db, day, result.items, solver_status=result.status)

    def delete(self, item_id: str) -> DaySchedule:
        with self.connection(write=True) as db:
            row = db.execute("SELECT day FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                raise ItemNotFound("This item no longer exists. Reload your calendar.")
            day = date.fromisoformat(row[0])
            remaining = [item for item in self._read(db, day) if item.id != item_id]
            result = schedule_items(remaining)
            self._clear_snapshot(db, day)
            return self._save(db, day, result.items, solver_status=result.status)

    def seed(self, day: date) -> DaySchedule:
        with self.connection(write=True) as db:
            if self._read(db, day):
                raise ScheduleConflict("Load a sample only into an empty day.")
            result = schedule_items(create_seed_items(day))
            self._clear_snapshot(db, day)
            return self._save(db, day, result.items, solver_status=result.status)

    @staticmethod
    def _cutoff(day: date, time_zone: str) -> int:
        try:
            now = utc_now().astimezone(ZoneInfo(time_zone))
        except (ZoneInfoNotFoundError, ValueError):
            raise ScheduleConflict("Choose a valid IANA time zone, such as America/New_York.")
        if day < now.date():
            raise ScheduleConflict("Past days cannot be rescheduled.")
        if day > now.date():
            return 0
        minutes = now.hour * 60 + now.minute + now.second / 60 + now.microsecond / 60_000_000
        return min(32, max(0, math.ceil((minutes - 8 * 60) / 30)))

    def preview(self, request: PreviewRequest) -> SchedulePreview:
        operation = request.operation
        with self.connection() as db:
            # Keep items and revision in the same read snapshot.
            db.execute("BEGIN")
            row = db.execute("SELECT day FROM items WHERE id = ?", (operation.item_id,)).fetchone()
            if row is None:
                raise ItemNotFound("This item no longer exists. Reload your calendar.")
            day = date.fromisoformat(row[0])
            before = self._read(db, day)
            revision = self._revision(db, day)
            can_undo = self._has_snapshot(db, day)
        cutoff = self._cutoff(day, request.time_zone)
        proposed = [item.model_copy(deep=True) for item in before]
        target = self._find(proposed, operation.item_id)
        # There is no completion tracking yet: preserve elapsed work unless the
        # user explicitly moves that flexible task to a future slot.
        locked = {item.id for item in before if item.start_slot is not None and item.start_slot < cutoff}
        if isinstance(operation, MoveOperation):
            if not isinstance(target, FlexibleTask) or target.is_pinned:
                raise ScheduleConflict("Only unpinned flexible tasks can be dragged.")
            if target.start_slot == operation.target_start_slot:
                raise ScheduleConflict("This task is already at that time. Choose a different slot.")
            if operation.target_start_slot < cutoff:
                raise ScheduleConflict("Choose a time that has not elapsed.")
            locked.discard(target.id)
            target.start_slot = operation.target_start_slot
        else:
            if target.start_slot is None:
                raise ScheduleConflict("A deferred task cannot run late because it is not on the calendar.")
            target.duration_slots += operation.additional_slots
            if target.start_slot + target.duration_slots < cutoff:
                raise ScheduleConflict("The extension must reach the current time or later.")
        latest_end = target.deadline_slot if isinstance(target, FlexibleTask) else 32
        if target.start_slot + target.duration_slots > latest_end:
            raise ScheduleConflict(f'“{target.title}” would finish after {format_slot(latest_end)}.')
        locked.add(target.id)
        result = schedule_items(proposed, locked_ids=frozenset(locked), earliest_start_slot=cutoff)
        preview = SchedulePreview(
            preview_token=secrets.token_urlsafe(32), expires_in_seconds=120,
            operation=operation, earliest_start_slot=cutoff,
            schedule=DaySchedule(date=day, items=result.items,
                changes=self._reschedule_changes(before, result, target.id, operation),
                can_undo=can_undo, solver_status=result.status),
        )
        with self._preview_lock:
            self._previews[preview.preview_token] = (time.monotonic() + 120, revision, request.time_zone, preview)
            while len(self._previews) > 256:
                self._previews.popitem(last=False)
        return preview

    def commit(self, token: str) -> DaySchedule:
        with self._preview_lock:
            cached = self._previews.get(token)
        if cached is None or cached[0] <= time.monotonic():
            raise ScheduleConflict("This preview expired. Preview the adjustment again.")
        expires, revision, time_zone, preview = cached
        day = preview.schedule.date
        with self.connection(write=True) as db:
            if expires <= time.monotonic():
                raise ScheduleConflict("This preview expired. Preview the adjustment again.")
            if self._revision(db, day) != revision:
                raise ScheduleConflict("Your calendar changed. Reload it and preview the adjustment again.")
            if self._cutoff(day, time_zone) != preview.earliest_start_slot:
                raise ScheduleConflict("Time has advanced. Preview the adjustment again.")
            self._store_snapshot(db, day, self._read(db, day))
            saved = self._save(db, day, preview.schedule.items,
                               changes=preview.schedule.changes, solver_status=preview.schedule.solver_status)
        with self._preview_lock:
            self._previews.pop(token, None)
        return saved

    def proposals(self, request: ProposalOptionsRequest) -> ProposalSet:
        draft = request.item
        with self.connection() as db:
            db.execute("BEGIN")
            before = self._read(db, draft.date)
            revision = self._revision(db, draft.date)
            can_undo = self._has_snapshot(db, draft.date)
        if any(item.id == draft.id for item in before):
            raise ScheduleConflict("An item with this ID already exists. Reload your calendar.")
        cutoff = self._cutoff(draft.date, request.time_zone)
        locked = frozenset(item.id for item in before if item.start_slot is not None and item.start_slot < cutoff)
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
                    result = schedule_items([*before, added], locked_ids=locked, earliest_start_slot=cutoff)
                except ScheduleConflict:
                    continue
                solved.append((result, added))
        else:
            assert isinstance(draft, FlexibleTaskDraft)
            added = FlexibleTask(
                id=draft.id, title=draft.title, date=draft.date, kind="flexible",
                start_slot=None, duration_slots=draft.duration_slots,
                deadline_slot=draft.deadline_slot, is_pinned=False,
                accent=draft.accent, note=draft.note,
            )
            try:
                first = schedule_items(
                    [*before, added], locked_ids=locked,
                    required_ids=frozenset({added.id}), earliest_start_slot=cutoff,
                )
            except ScheduleConflict:
                first = None
            if first is not None:
                first_added = next(item for item in first.items if item.id == added.id)
                assert first_added.start_slot is not None
                solved.append((first, first_added))
                try:
                    second = schedule_items(
                        [*before, added], locked_ids=locked,
                        required_ids=frozenset({added.id}),
                        forbidden_starts={added.id: frozenset({first_added.start_slot})},
                        earliest_start_slot=cutoff,
                    )
                except ScheduleConflict:
                    second = None
                if second is not None:
                    second_added = next(item for item in second.items if item.id == added.id)
                    solved.append((second, second_added))

        alternatives: list[ProposalAlternative] = []
        for result, added in solved:
            assert added.start_slot is not None
            metrics = self._proposal_metrics(before, result)
            changes = self._addition_changes(before, result, added)
            alternatives.append(ProposalAlternative(
                id=secrets.token_urlsafe(12), label="Alternative",
                start_slot=added.start_slot, metrics=metrics,
                schedule=DaySchedule(
                    date=draft.date, items=result.items, changes=changes,
                    can_undo=can_undo, solver_status=result.status,
                ),
            ))
        if not alternatives:
            raise ScheduleConflict("No schedule option can place this item without moving protected items.")
        alternatives.sort(key=lambda option: (
            option.metrics.deferred_task_count,
            option.metrics.moved_task_count,
            option.metrics.total_shift_slots,
            option.start_slot,
        ))
        for index, alternative in enumerate(alternatives):
            alternative.label = "Fewest changes" if index == 0 else f"Alternative at {format_slot(alternative.start_slot)}"
        proposal_set = ProposalSet(
            proposal_set_id=secrets.token_urlsafe(24), expires_in_seconds=120,
            date=draft.date, alternatives=alternatives,
        )
        with self._preview_lock:
            self._proposal_sets[proposal_set.proposal_set_id] = (
                time.monotonic() + 120, revision, request.time_zone, cutoff, proposal_set,
            )
            while len(self._proposal_sets) > 256:
                self._proposal_sets.popitem(last=False)
        return proposal_set

    def accept_proposal(self, proposal_set_id: str, alternative_id: str) -> DaySchedule:
        with self._preview_lock:
            cached = self._proposal_sets.get(proposal_set_id)
        if cached is None or cached[0] <= time.monotonic():
            raise ScheduleConflict("These schedule options expired. Generate new options.")
        expires, revision, time_zone, cutoff, proposal_set = cached
        alternative = next((item for item in proposal_set.alternatives if item.id == alternative_id), None)
        if alternative is None:
            raise ScheduleConflict("Choose an option from this proposal set.")
        with self.connection(write=True) as db:
            if expires <= time.monotonic():
                raise ScheduleConflict("These schedule options expired. Generate new options.")
            if self._revision(db, proposal_set.date) != revision:
                raise ScheduleConflict("Your calendar changed. Reload it and generate new options.")
            if self._cutoff(proposal_set.date, time_zone) != cutoff:
                raise ScheduleConflict("Time has advanced. Generate new options again.")
            self._store_snapshot(db, proposal_set.date, self._read(db, proposal_set.date))
            saved = self._save(
                db, proposal_set.date, alternative.schedule.items,
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
            current = self._read(db, day)
            snapshot = DaySchedule.model_validate_json(row[0]).items
            old_by_id = {item.id: item for item in current}
            changes = [ScheduleChange(
                item_id=item.id,
                title=item.title,
                change_type="restored",
                from_start_slot=old_by_id[item.id].start_slot,
                to_start_slot=item.start_slot,
                from_duration_slots=old_by_id[item.id].duration_slots,
                to_duration_slots=item.duration_slots,
                reason="Restored the schedule from before the last running-late change.",
            ) for item in snapshot if item.id in old_by_id and (
                old_by_id[item.id].start_slot != item.start_slot
                or old_by_id[item.id].duration_slots != item.duration_slots
            )]
            self._clear_snapshot(db, day)
            return self._save(db, day, snapshot, changes=changes)
