import test from "node:test";
import assert from "node:assert/strict";
import { scheduleItems } from "../src/scheduler.ts";
import { createSeedItems } from "../src/seed.ts";
import { formatSlot } from "../src/time.ts";

const base = { date: "2026-09-12", isPinned: false, accent: "purple" };
const fixed = (id, startSlot, durationSlots) => ({ ...base, id, title: id, kind: "fixed", startSlot, durationSlots });
const task = (id, durationSlots, deadlineSlot = 32, startSlot = null, isPinned = false) => ({ ...base, id, title: id, kind: "flexible", durationSlots, deadlineSlot, startSlot, isPinned });
function scheduled(input) {
  const result = scheduleItems(input);
  assert.equal(result.ok, true, result.error);
  for (const item of result.items) {
    assert.ok(Number.isInteger(item.startSlot));
    assert.ok(item.startSlot >= 0);
    assert.ok(item.startSlot + item.durationSlots <= (item.deadlineSlot ?? 32));
    for (const other of result.items.filter((entry) => entry.id !== item.id)) {
      assert.ok(item.startSlot + item.durationSlots <= other.startSlot || other.startSlot + other.durationSlots <= item.startSlot, `${item.id} overlaps ${other.id}`);
    }
  }
  return result.items;
}

test("preserves the seeded day and does not mutate its inputs", () => {
  const input = createSeedItems(base.date);
  const before = structuredClone(input);
  input.forEach(Object.freeze);
  const output = scheduled(Object.freeze(input));
  assert.deepEqual(output, before);
  assert.notEqual(output[0], input[0]);
});

test("first-fit finds a contiguous gap around fixed and pinned intervals", () => {
  const output = scheduled([fixed("meeting", 0, 2), task("gym", 2, 32, 3, true), task("work", 2)]);
  assert.equal(output.find((item) => item.id === "work").startSlot, 5);
  assert.equal(output.find((item) => item.id === "gym").startSlot, 3);
});

test("adding a fixed event relocates its conflicting flexible task only", () => {
  const output = scheduled([task("work", 2, 12, 0), task("keep", 2, 12, 4), fixed("meeting", 0, 2)]);
  assert.equal(output.find((item) => item.id === "work").startSlot, 2);
  assert.equal(output.find((item) => item.id === "keep").startSlot, 4);
});

test("a fixed event cannot displace a pinned task; unpinning allows placement", () => {
  const pinned = task("gym", 2, 32, 0, true);
  const event = fixed("meeting", 0, 2);
  assert.equal(scheduleItems([pinned, event]).ok, false);
  const output = scheduled([{ ...pinned, isPinned: false }, event]);
  assert.equal(output[0].startSlot, 2);
});

test("fixed events cannot overlap, but adjacent events are valid", () => {
  assert.equal(scheduleItems([fixed("a", 0, 2), fixed("b", 1, 2)]).ok, false);
  assert.equal(scheduled([fixed("a", 0, 2), fixed("b", 2, 2)]).length, 2);
});

test("rejects a fragmented gap and an impossible deadline without changing input", () => {
  const input = [fixed("a", 1, 1), fixed("b", 3, 1), task("work", 2, 4)];
  const before = structuredClone(input);
  assert.equal(scheduleItems(input).ok, false);
  assert.deepEqual(input, before);
  assert.equal(scheduleItems([task("work", 2, 1)]).ok, false);
});

test("deleting a blocking item makes its slots available", () => {
  const event = fixed("all-day", 0, 32);
  assert.equal(scheduleItems([event, task("work", 1)]).ok, false);
  assert.equal(scheduled([event].filter((item) => item.id !== event.id).concat(task("work", 1)))[0].startSlot, 0);
});

test("finishing at the deadline or midnight is valid; going past midnight is not", () => {
  assert.equal(scheduled([task("work", 2, 2)])[0].startSlot, 0);
  assert.equal(scheduled([fixed("day", 0, 31), task("last-slot", 1)])[1].startSlot, 31);
  assert.equal(formatSlot(32), "12:00 AM");
  assert.equal(scheduleItems([fixed("too-late", 31, 2)]).ok, false);
});

test("places pending tasks in deadline order", () => {
  const output = scheduled([task("later", 2, 6), task("urgent", 2, 2)]);
  assert.equal(output[0].startSlot, 2);
  assert.equal(output[1].startSlot, 0);
});

test("rejects invalid durations, boundaries, pin state, and duplicate IDs", () => {
  for (const duration of [0, -1, 0.5, 33, NaN]) assert.equal(scheduleItems([task("bad", duration)]).ok, false);
  for (const deadline of [0, 1.5, 33]) assert.equal(scheduleItems([task("bad", 1, deadline)]).ok, false);
  assert.equal(scheduleItems([task("bad", 1, 32, null, true)]).ok, false);
  assert.equal(scheduleItems([task("bad", 2, 2, 2, true)]).ok, false);
  assert.equal(scheduleItems([fixed("bad", -1, 1)]).ok, false);
  assert.equal(scheduleItems([task("same", 1), task("same", 1)]).ok, false);
  assert.equal(scheduleItems([task(" ", 1)]).ok, false);
  assert.equal(scheduleItems([task("a", 1), { ...task("b", 1), date: "2026-09-13" }]).ok, false);
  assert.deepEqual(scheduled([]), []);
});
