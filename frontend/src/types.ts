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

export type ChangeType = "added" | "extended" | "moved" | "deferred" | "scheduled" | "restored";

export type ScheduleChange = {
  itemId: string;
  title: string;
  changeType: ChangeType;
  fromStartSlot: number | null;
  toStartSlot: number | null;
  fromDurationSlots: number | null;
  toDurationSlots: number | null;
  reason: string;
};

export type DaySchedule = {
  date: string;
  items: CalendarItem[];
  changes: ScheduleChange[];
  canUndo: boolean;
  solverStatus: "optimal" | "feasible" | null;
};

export type OptimizerOperation =
  | { type: "move"; itemId: string; targetStartSlot: number }
  | { type: "extend"; itemId: string; additionalSlots: number };

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
  | { kind: "flexible"; deadlineSlot: number }
);

export type ProposalMetrics = {
  movedTaskCount: number;
  totalShiftSlots: number;
  deferredTaskCount: number;
};

export type ProposalAlternative = {
  id: string;
  label: string;
  startSlot: number;
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
};
