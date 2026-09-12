from collections.abc import Sequence

from .models import CalendarItem, FixedEvent, FlexibleTask, SLOTS_PER_DAY


class ScheduleConflict(Exception):
    """The requested change cannot fit without violating protected intervals."""


def format_slot(slot: int) -> str:
    minutes = 8 * 60 + slot * 30
    hour = minutes // 60 % 24
    return f"{hour % 12 or 12}:{minutes % 60:02d} {'PM' if hour >= 12 else 'AM'}"


def schedule_items(source: Sequence[CalendarItem]) -> list[CalendarItem]:
    """Pure first-fit placeholder; preserve valid placements, never mutate input."""
    items = [item.model_copy(deep=True) for item in source]
    if len({item.id for item in items}) != len(items):
        raise ScheduleConflict("Each item must have a unique ID.")
    if len({item.date for item in items}) > 1:
        raise ScheduleConflict("Schedule one day at a time.")
    occupied: list[CalendarItem | None] = [None] * SLOTS_PER_DAY

    def fits(item: CalendarItem, start: int) -> bool:
        deadline = item.deadline_slot if isinstance(item, FlexibleTask) else SLOTS_PER_DAY
        return start >= 0 and start + item.duration_slots <= deadline and not any(
            occupied[start:start + item.duration_slots]
        )

    def reserve(item: CalendarItem, start: int) -> None:
        item.start_slot = start
        occupied[start:start + item.duration_slots] = [item] * item.duration_slots

    for item in items:
        if isinstance(item, FixedEvent) or item.is_pinned:
            assert item.start_slot is not None  # Guaranteed by input models.
            conflict = next((entry for entry in occupied[item.start_slot:item.start_slot + item.duration_slots] if entry), None)
            if conflict:
                raise ScheduleConflict(
                    f'“{item.title}” overlaps “{conflict.title}”, which is fixed or pinned. '
                    "Choose another time or unpin the task."
                )
            if not fits(item, item.start_slot):
                raise ScheduleConflict(f'“{item.title}” cannot fit at its protected time.')
            reserve(item, item.start_slot)

    pending: list[FlexibleTask] = []
    for item in items:
        if isinstance(item, FlexibleTask) and not item.is_pinned:
            if item.start_slot is not None and fits(item, item.start_slot):
                reserve(item, item.start_slot)
            else:
                pending.append(item)

    # Python's stable sort preserves insertion order for equal deadlines.
    for item in sorted(pending, key=lambda entry: entry.deadline_slot):
        start = next((slot for slot in range(SLOTS_PER_DAY) if fits(item, slot)), None)
        if start is None:
            raise ScheduleConflict(
                f'“{item.title}” has no continuous gap before {format_slot(item.deadline_slot)}. '
                "Try a shorter duration, a later deadline, or free some space."
            )
        reserve(item, start)
    return items
