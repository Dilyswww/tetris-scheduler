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
    return next(item for item in items.items if item.id == item_id)


def test_preserves_valid_placements_and_does_not_mutate_input():
    items = [fixed("meeting", 0, 2), task("work", 2, start=3), task("gym", 2, start=6, pinned=True)]
    output = schedule_items(items)
    assert [item.start_slot for item in output.items] == [0, 3, 6]
    assert output.items[1] is not items[1]
    assert output.status == "optimal"


def test_relocates_only_flexible_conflict():
    output = schedule_items([task("work", 2, 12, 0), task("keep", 2, 12, 4), fixed("meeting", 0, 2)])
    assert by_id(output, "work").start_slot == 2
    assert by_id(output, "keep").start_slot == 4


def test_protected_conflict_is_rejected():
    with pytest.raises(ScheduleConflict, match="Fixed, pinned"):
        schedule_items([task("gym", 2, start=0, pinned=True), fixed("meeting", 0, 2)])


def test_fragmented_gap_and_impossible_deadline_are_deferred():
    fragmented = schedule_items([fixed("a", 1, 1), fixed("b", 3, 1), task("work", 2, 4)])
    impossible = schedule_items([task("work", 2, 1)])
    assert by_id(fragmented, "work").start_slot is None
    assert by_id(impossible, "work").start_slot is None


def test_pending_tasks_use_deadline_order():
    output = schedule_items([task("later", 2, 6), task("urgent", 2, 2)])
    assert by_id(output, "urgent").start_slot == 0
    assert by_id(output, "later").start_slot == 2


def test_minimizes_moved_tasks_before_total_displacement():
    output = schedule_items([
        fixed("extended", 0, 4),
        task("displaced", 2, start=2),
        task("unchanged", 2, start=4),
    ])
    assert by_id(output, "unchanged").start_slot == 4
    assert by_id(output, "displaced").start_slot == 6


def test_minimizes_displacement_and_is_deterministic():
    items = [fixed("block", 3, 1), task("displaced", 1, start=3)]
    first = schedule_items(items)
    second = schedule_items(items)
    assert by_id(first, "displaced").start_slot == 2
    assert [item.start_slot for item in first.items] == [item.start_slot for item in second.items]


def test_locked_item_cannot_move_and_optional_work_can_defer():
    result = schedule_items([
        task("current", 4, deadline=8, start=0),
        task("other", 4, deadline=8, start=4),
        fixed("new-block", 4, 4),
    ], locked_ids=frozenset({"current"}))
    assert by_id(result, "current").start_slot == 0
    assert by_id(result, "other").start_slot is None
