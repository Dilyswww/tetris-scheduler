export const DAY_START_HOUR = 8;
export const SLOT_MINUTES = 30;
export const SLOTS_PER_DAY = 32;
export const DEMO_DATES = ["2026-09-11", "2026-09-12", "2026-09-13"] as const;
export const DEMO_TIME_ZONE = "America/New_York";

export type DemoClock = {
  now: string;
  revision: number;
  timeZone: string;
  startDate: string;
  endDate: string;
};

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
  earliestDate?: string;
  deadlineDate?: string;
};

export type CalendarItem = FixedEvent | FlexibleTask;

export type ChangeType = "added" | "edited" | "extended" | "moved" | "deferred" | "scheduled" | "restored";

export type ScheduleChange = {
  itemId: string;
  title: string;
  changeType: ChangeType;
  fromStartSlot: number | null;
  toStartSlot: number | null;
  fromDurationSlots: number | null;
  toDurationSlots: number | null;
  fromDate?: string | null;
  toDate?: string | null;
  reason: string;
};

export type DaySchedule = {
  date: string;
  items: CalendarItem[];
  changes: ScheduleChange[];
  canUndo: boolean;
  solverStatus: "optimal" | "feasible" | null;
  days?: { date: string; items: CalendarItem[] }[];
};

export type OptimizerOperation =
  | { type: "move"; itemId: string; targetStartSlot: number; targetDate?: string }
  | { type: "extend"; itemId: string; additionalSlots: number }
  | { type: "edit"; item: CalendarItem };

export type SchedulePreview = {
  previewToken: string;
  expiresInSeconds: number;
  operation: OptimizerOperation;
  earliestStartSlot: number;
  penalties: PenaltyWeights;
  schedule: DaySchedule;
};

type ProposalDraftBase = {
  id: string;
  title: string;
  date: string;
  durationSlots: number;
  accent: Accent;
  note: string;
};

export type ProposalItemDraft = ProposalDraftBase & (
  | { kind: "fixed" }
  | { kind: "flexible"; deadlineSlot: number; earliestDate?: string; deadlineDate?: string }
);

export type ProposalMetrics = {
  movedTaskCount: number;
  totalShiftSlots: number;
  deferredTaskCount: number;
  dayChangeCount: number;
};

export type ProposalAlternative = {
  id: string;
  label: string;
  startSlot: number;
  date: string;
  schedule: DaySchedule;
  metrics: ProposalMetrics;
};

export type ProposalSet = {
  proposalSetId: string;
  expiresInSeconds: number;
  date: string;
  alternatives: ProposalAlternative[];
};

export type PenaltyWeights = {
  movedTask: number;
  displacementSlot: number;
  largestDisplacementSlot: number;
  dayChange: number;
};

export function scheduleItems(schedule: DaySchedule): CalendarItem[] {
  return schedule.days?.length ? schedule.days.flatMap((day) => day.items) : schedule.items;
}
