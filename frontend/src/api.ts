import type { CalendarItem, DaySchedule, DemoClock, OptimizerOperation, PenaltyWeights, ProposalItemDraft, ProposalSet, SchedulePreview } from "./types.ts";
import { DEMO_TIME_ZONE } from "./types.ts";

export class ApiError extends Error {}

async function request<T = DaySchedule>(path: string, init?: RequestInit): Promise<T> {
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
  return body as T;
}

export const calendarApi = {
  startDemo: () => request<DemoClock>("/api/demo/start", { method: "POST" }),
  getClock: () => request<DemoClock>("/api/demo/clock"),
  setClock: (now: string) => request<DemoClock>("/api/demo/clock", { method: "PUT", body: JSON.stringify({ now }) }),
  getDay: (date: string) => request(`/api/day/${date}`),
  addItem: (item: CalendarItem) => request(`/api/items?timeZone=${encodeURIComponent(DEMO_TIME_ZONE)}`, { method: "POST", body: JSON.stringify(item) }),
  updateItem: (item: CalendarItem) => request(`/api/items/${encodeURIComponent(item.id)}`, { method: "PUT", body: JSON.stringify(item) }),
  setPin: (id: string, isPinned: boolean) => request(`/api/items/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ isPinned }) }),
  deleteItem: (id: string) => request(`/api/items/${encodeURIComponent(id)}`, { method: "DELETE" }),
  seedDay: (date: string) => request(`/api/day/${date}/seed`, { method: "POST" }),
  resetDebugSchedule: (date: string) => request(`/api/debug/reset?day=${encodeURIComponent(date)}`, { method: "POST" }),
  preview: (operation: OptimizerOperation, signal?: AbortSignal, penalties?: Partial<PenaltyWeights>) => request<SchedulePreview>("/api/optimizer/preview", {
    method: "POST", signal, body: JSON.stringify({ operation, timeZone: DEMO_TIME_ZONE, penalties }),
  }),
  commit: (previewToken: string) => request("/api/optimizer/commit", { method: "POST", body: JSON.stringify({ previewToken }) }),
  proposals: (item: ProposalItemDraft, candidateStartSlots?: number[]) => request<ProposalSet>("/api/optimizer/proposals", {
    method: "POST",
    body: JSON.stringify({ item, candidateStartSlots, timeZone: DEMO_TIME_ZONE }),
  }),
  acceptProposal: (proposalSetId: string, alternativeId: string) => request(`/api/optimizer/proposals/${encodeURIComponent(proposalSetId)}/accept`, {
    method: "POST", body: JSON.stringify({ alternativeId }),
  }),
  undo: (date: string) => request(`/api/day/${date}/undo`, { method: "POST" }),
};
