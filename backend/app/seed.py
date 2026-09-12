from datetime import date
from uuid import NAMESPACE_URL, uuid5

from .models import CalendarItem, item_adapter


def create_seed_items(day: date) -> list[CalendarItem]:
    entries = [
        dict(title="Morning focus", kind="flexible", startSlot=0, durationSlots=3, deadlineSlot=8, accent="purple", note="Deep work"),
        dict(title="Team standup", kind="fixed", startSlot=4, durationSlots=1, accent="blue", note="Zoom"),
        dict(title="Design slides", kind="flexible", startSlot=5, durationSlots=3, deadlineSlot=18, accent="orange"),
        dict(title="Lunch with Maya", kind="fixed", startSlot=9, durationSlots=2, accent="green", note="Sushi Kazu"),
        dict(title="Client meeting", kind="fixed", startSlot=12, durationSlots=2, accent="blue", note="Room 402"),
        dict(title="Email catch-up", kind="flexible", startSlot=15, durationSlots=1, deadlineSlot=20, accent="purple"),
        dict(title="Gym", kind="flexible", startSlot=20, durationSlots=2, deadlineSlot=24, isPinned=True, accent="orange"),
        dict(title="Read", kind="flexible", startSlot=24, durationSlots=2, deadlineSlot=32, accent="purple", note="A chapter before bed"),
    ]
    return [item_adapter.validate_python({**entry, "date": day, "id": str(uuid5(NAMESPACE_URL, f"tetris/{day}/{entry['title']}"))}) for entry in entries]
