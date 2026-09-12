export const DAY_START_HOUR = 8;
export const SLOT_MINUTES = 30;
export const SLOTS_PER_DAY = 32;

export type Accent = "purple" | "orange" | "blue" | "green";

type ItemBase = {
  id: string;
  title: string;
  date: string; // Local calendar date, YYYY-MM-DD.
  durationSlots: number;
  isPinned: boolean;
  accent: Accent;
  note?: string;
};

export type FixedEvent = ItemBase & {
  kind: "fixed";
  startSlot: number;
};

export type FlexibleTask = ItemBase & {
  kind: "flexible";
  startSlot: number | null; // Null until the scheduler places the task.
  deadlineSlot: number; // Exclusive end boundary; 32 means midnight.
};

export type CalendarItem = FixedEvent | FlexibleTask;

export type ScheduleResult =
  | { ok: true; items: CalendarItem[] }
  | { ok: false; error: string };
