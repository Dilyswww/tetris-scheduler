import { DAY_START_HOUR, SLOT_MINUTES, SLOTS_PER_DAY } from "./types.ts";

export function formatSlot(slot: number) {
  const minutes = DAY_START_HOUR * 60 + slot * SLOT_MINUTES;
  const hour = Math.floor(minutes / 60) % 24;
  return `${hour % 12 || 12}:${String(minutes % 60).padStart(2, "0")} ${hour >= 12 ? "PM" : "AM"}`;
}

export function formatDuration(slots: number) {
  const minutes = slots * SLOT_MINUTES;
  const hours = Math.floor(minutes / 60);
  return [hours ? `${hours}h` : "", minutes % 60 ? `${minutes % 60}m` : ""].filter(Boolean).join(" ") || "0m";
}

export function localDateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function formatDate(date?: string | null) {
  return date ? new Date(`${date}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
}

export function earliestStartSlot(date: string, now = new Date()) {
  const today = localDateKey(now);
  if (date < today) return SLOTS_PER_DAY;
  if (date > today) return 0;
  const minutes = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60 + now.getMilliseconds() / 60_000;
  return Math.max(0, Math.min(SLOTS_PER_DAY, Math.ceil((minutes - DAY_START_HOUR * 60) / SLOT_MINUTES)));
}
