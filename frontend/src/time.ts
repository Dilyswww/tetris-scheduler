import { DAY_START_HOUR, SLOT_MINUTES } from "./types.ts";

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
