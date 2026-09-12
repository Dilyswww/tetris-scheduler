import type { CalendarItem } from "./types.ts";

type DaySchedule = { date: string; items: CalendarItem[] };

export class ApiError extends Error {}

async function request(path: string, init?: RequestInit): Promise<DaySchedule> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
    });
  } catch {
    throw new ApiError("The calendar service is unavailable. Start the backend and try again.");
  }
  const body = await response.json().catch(() => null) as { detail?: string } | null;
  if (!response.ok) {
    const detail = body?.detail;
    throw new ApiError(typeof detail === "string" ? detail : "The calendar service could not complete that request.");
  }
  return body as DaySchedule;
}

export const calendarApi = {
  getDay: (date: string) => request(`/api/day/${date}`),
  addItem: (item: CalendarItem) => request("/api/items", { method: "POST", body: JSON.stringify(item) }),
  setPin: (id: string, isPinned: boolean) => request(`/api/items/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ isPinned }) }),
  deleteItem: (id: string) => request(`/api/items/${encodeURIComponent(id)}`, { method: "DELETE" }),
  seedDay: (date: string) => request(`/api/day/${date}/seed`, { method: "POST" }),
};
