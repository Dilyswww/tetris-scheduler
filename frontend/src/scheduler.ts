import { SLOTS_PER_DAY } from "./types.ts";
import type { CalendarItem, ScheduleResult } from "./types.ts";
import { formatSlot } from "./time.ts";

/** Phase 1 placeholder. Inputs are never mutated; the caller commits only a successful result. */
export function scheduleItems(input: readonly CalendarItem[]): ScheduleResult {
  const items = input.map((item) => ({ ...item }));
  const ids = new Set<string>();
  const occupied: (CalendarItem | undefined)[] = Array(SLOTS_PER_DAY).fill(undefined);

  for (const item of items) {
    if (!item.id || ids.has(item.id)) return { ok: false, error: "Each item must have a unique ID." };
    ids.add(item.id);
    if (item.date !== items[0].date) return { ok: false, error: "Schedule one day at a time." };
    if (!item.title.trim()) return { ok: false, error: "Give the item a title." };
    if (!Number.isInteger(item.durationSlots) || item.durationSlots < 1 || item.durationSlots > SLOTS_PER_DAY) {
      return { ok: false, error: "Duration must be between 30 minutes and 16 hours, in 30-minute steps." };
    }
    if (item.startSlot !== null && (!Number.isInteger(item.startSlot) || item.startSlot < 0 || item.startSlot + item.durationSlots > SLOTS_PER_DAY)) {
      return { ok: false, error: `“${item.title}” must fit between 8:00 AM and midnight.` };
    }
    if (item.kind === "flexible" && (!Number.isInteger(item.deadlineSlot) || item.deadlineSlot < 1 || item.deadlineSlot > SLOTS_PER_DAY)) {
      return { ok: false, error: "Choose a deadline on the day's 30-minute grid." };
    }
    if (item.isPinned && item.startSlot === null) return { ok: false, error: "Schedule a task before pinning it." };
  }

  const fits = (item: CalendarItem, start: number) =>
    start >= 0 && start + item.durationSlots <= (item.kind === "flexible" ? item.deadlineSlot : SLOTS_PER_DAY) &&
    occupied.slice(start, start + item.durationSlots).every((slot) => !slot);

  const reserve = (item: CalendarItem, start: number) => {
    item.startSlot = start;
    occupied.fill(item, start, start + item.durationSlots);
  };

  // Reserve every protected interval before considering flexible work.
  for (const item of items.filter((entry) => entry.kind === "fixed" || entry.isPinned)) {
    const start = item.startSlot!;
    const conflict = occupied.slice(start, start + item.durationSlots).find(Boolean);
    if (conflict) return { ok: false, error: `“${item.title}” overlaps “${conflict.title}”, which is fixed or pinned. Choose another time or unpin the task.` };
    if (!fits(item, start)) return { ok: false, error: `“${item.title}” is pinned after its deadline. Unpin it first.` };
    reserve(item, start);
  }

  const pending: CalendarItem[] = [];
  for (const item of items.filter((entry) => entry.kind === "flexible" && !entry.isPinned)) {
    if (item.startSlot !== null && fits(item, item.startSlot)) reserve(item, item.startSlot);
    else pending.push(item);
  }

  // Earliest deadlines first; stable array order breaks ties.
  pending.sort((a, b) => (a.kind === "flexible" ? a.deadlineSlot : SLOTS_PER_DAY) - (b.kind === "flexible" ? b.deadlineSlot : SLOTS_PER_DAY));
  for (const item of pending) {
    const start = Array.from({ length: SLOTS_PER_DAY }, (_, slot) => slot).find((slot) => fits(item, slot));
    if (start === undefined) {
      const deadline = item.kind === "flexible" ? item.deadlineSlot : SLOTS_PER_DAY;
      return { ok: false, error: `“${item.title}” has no continuous gap before ${formatSlot(deadline)}. Try a shorter duration, a later deadline, or free some space.` };
    }
    reserve(item, start);
  }

  return { ok: true, items };
}
