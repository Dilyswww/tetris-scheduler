from datetime import date
from uuid import NAMESPACE_URL, uuid5

from .models import CalendarItem, DEMO_END, DEMO_START, item_adapter


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


def create_debug_schedule() -> list[CalendarItem]:
    """A deterministic three-day schedule that exercises the demo's main paths."""
    day_one = DEMO_START
    day_two = date(2026, 9, 12)
    day_three = DEMO_END
    entries = [
        # Sep 11 is intentionally full. Extending Client review by one hour must
        # send eligible flexible work to a later date.
        dict(id="debug-morning-focus", title="Morning focus", date=day_one, kind="flexible", startSlot=0, durationSlots=3, deadlineSlot=4, accent="purple", note="Same-day deadline"),
        dict(id="debug-standup", title="Team standup", date=day_one, kind="fixed", startSlot=3, durationSlots=1, accent="blue", note="Fixed event"),
        dict(id="debug-pitch-draft", title="Pitch draft", date=day_one, kind="flexible", startSlot=4, durationSlots=4, earliestDate=day_one, deadlineDate=day_two, deadlineSlot=8, accent="orange", note="Can move to Sep 12"),
        dict(id="debug-lunch", title="Lunch with team", date=day_one, kind="fixed", startSlot=8, durationSlots=2, accent="green"),
        dict(id="debug-admin", title="Admin sweep", date=day_one, kind="flexible", startSlot=10, durationSlots=2, deadlineSlot=12, accent="purple"),
        dict(id="debug-client-review", title="Client review", date=day_one, kind="fixed", startSlot=12, durationSlots=2, accent="blue", note="Extend this by 60 minutes"),
        dict(id="debug-slide-polish", title="Slide polish", date=day_one, kind="flexible", startSlot=14, durationSlots=3, earliestDate=day_one, deadlineDate=day_two, deadlineSlot=10, accent="orange", note="Cross-day running-late example"),
        dict(id="debug-sponsor-hours", title="Sponsor office hours", date=day_one, kind="fixed", startSlot=17, durationSlots=3, accent="blue"),
        dict(id="debug-gym", title="Gym", date=day_one, kind="flexible", startSlot=20, durationSlots=2, deadlineSlot=22, isPinned=True, accent="orange", note="Pinned task"),
        dict(id="debug-commute", title="Commute", date=day_one, kind="fixed", startSlot=22, durationSlots=2, accent="green"),
        dict(id="debug-rehearsal", title="Demo rehearsal", date=day_one, kind="flexible", startSlot=24, durationSlots=3, earliestDate=day_one, deadlineDate=day_two, deadlineSlot=14, accent="purple"),
        dict(id="debug-dinner", title="Team dinner", date=day_one, kind="fixed", startSlot=27, durationSlots=3, accent="green"),
        dict(id="debug-read", title="Read and decompress", date=day_one, kind="flexible", startSlot=30, durationSlots=2, earliestDate=day_one, deadlineDate=day_three, deadlineSlot=28, accent="purple", note="Long deadline window"),

        # Sep 12 has fixed blockers, movable work, a pin, useful gaps, and a task
        # that cannot fit before its same-day deadline.
        dict(id="debug-conference", title="Morning conference", date=day_two, kind="fixed", startSlot=0, durationSlots=6, accent="blue"),
        dict(id="debug-travel-form", title="Submit travel form", date=day_two, kind="flexible", startSlot=None, durationSlots=2, deadlineSlot=6, accent="orange", note="Intentionally deferred"),
        dict(id="debug-research", title="User research", date=day_two, kind="flexible", startSlot=6, durationSlots=4, earliestDate=day_two, deadlineDate=day_three, deadlineSlot=8, accent="purple"),
        dict(id="debug-workshop", title="Design workshop", date=day_two, kind="fixed", startSlot=10, durationSlots=4, accent="blue"),
        dict(id="debug-mentor-notes", title="Mentor feedback", date=day_two, kind="flexible", startSlot=14, durationSlots=2, deadlineSlot=18, accent="orange"),
        dict(id="debug-dentist", title="Dentist", date=day_two, kind="fixed", startSlot=18, durationSlots=2, accent="green"),
        dict(id="debug-groceries", title="Groceries", date=day_two, kind="flexible", startSlot=20, durationSlots=2, deadlineSlot=24, isPinned=True, accent="orange", note="Pinned task"),
        dict(id="debug-dinner-two", title="Dinner reservation", date=day_two, kind="fixed", startSlot=24, durationSlots=4, accent="green"),

        # Sep 13 includes final-day deadlines and a deliberately impossible long task.
        dict(id="debug-breakfast", title="Breakfast", date=day_three, kind="fixed", startSlot=0, durationSlots=2, accent="green"),
        dict(id="debug-final-polish", title="Final pitch polish", date=day_three, kind="flexible", startSlot=2, durationSlots=4, earliestDate=day_two, deadlineDate=day_three, deadlineSlot=8, accent="purple"),
        dict(id="debug-keynote", title="Hackathon keynote", date=day_three, kind="fixed", startSlot=8, durationSlots=4, accent="blue"),
        dict(id="debug-followups", title="Send follow-ups", date=day_three, kind="flexible", startSlot=12, durationSlots=2, deadlineSlot=18, accent="orange"),
        dict(id="debug-flight", title="Airport shuttle", date=day_three, kind="fixed", startSlot=20, durationSlots=4, accent="blue"),
        dict(id="debug-pack", title="Pack equipment", date=day_three, kind="flexible", startSlot=24, durationSlots=2, deadlineSlot=28, isPinned=True, accent="orange"),
        dict(id="debug-long-report", title="Write long report", date=day_three, kind="flexible", startSlot=None, durationSlots=7, deadlineSlot=8, accent="purple", note="Intentionally deferred on the final day"),
    ]
    return [item_adapter.validate_python(entry) for entry in entries]
