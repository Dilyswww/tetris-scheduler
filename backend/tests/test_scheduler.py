from datetime import date

import pytest

from app.models import FixedEvent, FlexibleTask
from app.scheduler import ScheduleConflict, schedule_items

DAY = date(2026, 9, 12)


def fixed(item_id: str, start: int, duration: int) -> FixedEvent:
    return FixedEvent(id=item_id, title=item_id, date=DAY, kind="fixed", start_slot=start, duration_slots=duration)


def task(item_id: str, duration: int, deadline: int = 32, start: int | None = None, pinned: bool = False) -> FlexibleTask:
    return FlexibleTask(id=item_id, title=item_id, date=DAY, kind="flexible", start_slot=start, duration_slots=duration, deadline_slot=deadline, is_pinned=pinned)


def by_id(items, item_id):
    return next(item for item in items if item.id == item_id)


def test_preserves_valid_placements_and_does_not_mutate_input():
    items = [fixed("meeting", 0, 2), task("work", 2, start=3), task("gym", 2, start=6, pinned=True)]
    output = schedule_items(items)
    assert [item.start_slot for item in output] == [0, 3, 6]
    assert output[1] is not items[1]


def test_relocates_only_flexible_conflict():
    output = schedule_items([task("work", 2, 12, 0), task("keep", 2, 12, 4), fixed("meeting", 0, 2)])
    assert by_id(output, "work").start_slot == 2
    assert by_id(output, "keep").start_slot == 4


def test_protected_conflict_is_rejected():
    with pytest.raises(ScheduleConflict, match="fixed or pinned"):
        schedule_items([task("gym", 2, start=0, pinned=True), fixed("meeting", 0, 2)])


def test_fragmented_gap_and_impossible_deadline_are_rejected():
    with pytest.raises(ScheduleConflict, match="no continuous gap"):
        schedule_items([fixed("a", 1, 1), fixed("b", 3, 1), task("work", 2, 4)])
    with pytest.raises(ScheduleConflict, match="no continuous gap"):
        schedule_items([task("work", 2, 1)])


def test_pending_tasks_use_deadline_order():
    output = schedule_items([task("later", 2, 6), task("urgent", 2, 2)])
    assert by_id(output, "urgent").start_slot == 0
    assert by_id(output, "later").start_slot == 2
