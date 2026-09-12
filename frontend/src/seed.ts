import type { CalendarItem } from "./types.ts";

export function createSeedItems(date: string): CalendarItem[] {
  return [
    { id: "morning-focus", title: "Morning focus", date, startSlot: 0, durationSlots: 3, kind: "flexible", deadlineSlot: 8, isPinned: false, accent: "purple", note: "Deep work" },
    { id: "standup", title: "Team standup", date, startSlot: 4, durationSlots: 1, kind: "fixed", isPinned: false, accent: "blue", note: "Zoom" },
    { id: "slides", title: "Design slides", date, startSlot: 5, durationSlots: 3, kind: "flexible", deadlineSlot: 18, isPinned: false, accent: "orange" },
    { id: "lunch", title: "Lunch with Maya", date, startSlot: 9, durationSlots: 2, kind: "fixed", isPinned: false, accent: "green", note: "Sushi Kazu" },
    { id: "client-meeting", title: "Client meeting", date, startSlot: 12, durationSlots: 2, kind: "fixed", isPinned: false, accent: "blue", note: "Room 402" },
    { id: "email", title: "Email catch-up", date, startSlot: 15, durationSlots: 1, kind: "flexible", deadlineSlot: 20, isPinned: false, accent: "purple" },
    { id: "gym", title: "Gym", date, startSlot: 20, durationSlots: 2, kind: "flexible", deadlineSlot: 24, isPinned: true, accent: "orange" },
    { id: "read", title: "Read", date, startSlot: 24, durationSlots: 2, kind: "flexible", deadlineSlot: 32, isPinned: false, accent: "purple", note: "A chapter before bed" },
  ];
}
