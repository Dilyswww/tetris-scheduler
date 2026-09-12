from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from ortools.sat.python import cp_model

from .models import CalendarItem, FixedEvent, FlexibleTask, PenaltyWeights, SLOTS_PER_DAY


class ScheduleConflict(Exception):
    """Hard constraints conflict, so no schedule can be produced."""


class SolverUnavailable(Exception):
    """The solver stopped before finding a usable schedule."""


@dataclass(frozen=True)
class SolverResult:
    items: list[CalendarItem]
    status: str
    objective_value: int


def format_slot(slot: int) -> str:
    minutes = 8 * 60 + slot * 30
    hour = minutes // 60 % 24
    return f"{hour % 12 or 12}:{minutes % 60:02d} {'PM' if hour >= 12 else 'AM'}"


def schedule_items(
    source: Sequence[CalendarItem],
    *,
    locked_ids: frozenset[str] = frozenset(),
    required_ids: frozenset[str] = frozenset(),
    forbidden_starts: Mapping[str, frozenset[int]] | None = None,
    forbidden_placements: Mapping[str, frozenset[tuple[date, int]]] | None = None,
    earliest_start_slot: int = 0,
    days: Sequence[date] | None = None,
    earliest_starts: Mapping[date, int] | None = None,
    penalties: PenaltyWeights | None = None,
    time_limit_seconds: float = 0.5,
) -> SolverResult:
    """Minimize deferrals, then weighted movement, across the supplied days.

    Each Boolean selects a (day, start) interval entirely within one day.
    No task splitting or overnight intervals are allowed.
    """
    items = [item.model_copy(deep=True) for item in source]
    penalties = penalties if penalties is not None else PenaltyWeights()
    item_ids = {item.id for item in items}
    if len(item_ids) != len(items):
        raise ScheduleConflict("Each item must have a unique ID.")
    horizon = sorted(set(days if days is not None else [item.date for item in items]))
    if not horizon:
        return SolverResult(items=[], status="optimal", objective_value=0)
    if len(horizon) > 3:
        raise ScheduleConflict("Optimize at most three days at a time.")
    if {item.date for item in items} - set(horizon):
        raise ScheduleConflict("All items must belong to the optimization window.")
    if (locked_ids | required_ids) - item_ids:
        raise ScheduleConflict("The selected item no longer exists.")
    if locked_ids & required_ids:
        raise ScheduleConflict("An item cannot be both locked and independently required.")
    cutoffs = {day: (earliest_starts or {}).get(day, earliest_start_slot) for day in horizon}
    if any(not 0 <= cutoff <= SLOTS_PER_DAY for cutoff in cutoffs.values()):
        raise ScheduleConflict("The earliest start must be within this day.")

    model = cp_model.CpModel()
    count = len(items)
    placement_vars: dict[str, list[tuple[date, int, cp_model.IntVar]]] = {}
    deferred_vars: dict[str, cp_model.IntVar] = {}
    occupancy = {day: [[] for _ in range(SLOTS_PER_DAY)] for day in horizon}
    offsets = {day: index * SLOTS_PER_DAY for index, day in enumerate(horizon)}
    total_slots = len(horizon) * SLOTS_PER_DAY
    span_days = (horizon[-1] - horizon[0]).days
    max_shift = span_days * 48 + SLOTS_PER_DAY - 1
    max_tie = count * ((total_slots + 1) * (count + 1) + count)
    score_scale = max_tie + 1
    max_movement_score = count * (
        penalties.moved_task + max_shift * penalties.displacement_slot
        + span_days * penalties.day_change
    ) + max_shift * penalties.largest_displacement_slot
    defer_weight = max_movement_score * score_scale + max_tie + 1
    objective_terms = []
    displacements = []

    for index, item in enumerate(items):
        protected = isinstance(item, FixedEvent) or item.is_pinned or item.id in locked_ids
        if protected:
            if item.start_slot is None:
                raise ScheduleConflict(f'“{item.title}” must be scheduled before it can be locked.')
            latest_end = item.deadline_slot if isinstance(item, FlexibleTask) and item.date == item.deadline_date else SLOTS_PER_DAY
            if item.start_slot + item.duration_slots > latest_end:
                raise ScheduleConflict(f'“{item.title}” would finish after {format_slot(latest_end)}.')
            if isinstance(item, FlexibleTask) and not item.earliest_date <= item.date <= item.deadline_date:
                raise ScheduleConflict(f'“{item.title}” must stay between its earliest date and deadline.')
            candidate_starts = [(item.date, item.start_slot)]
        else:
            candidate_starts = []
            for day in horizon:
                if not item.earliest_date <= day <= item.deadline_date:
                    continue
                latest_end = item.deadline_slot if day == item.deadline_date else SLOTS_PER_DAY
                for start in range(cutoffs[day], latest_end - item.duration_slots + 1):
                    if day == item.date and start in (forbidden_starts or {}).get(item.id, frozenset()):
                        continue
                    if (day, start) in (forbidden_placements or {}).get(item.id, frozenset()):
                        continue
                    candidate_starts.append((day, start))

        candidates = []
        item_displacement = []
        for day, start in candidate_starts:
            variable = model.new_bool_var(f"place_{index}_{day}_{start}")
            candidates.append((day, start, variable))
            for slot in range(start, start + item.duration_slots):
                occupancy[day][slot].append(variable)
            tie_cost = (offsets[day] + start) * (count + 1) + index
            day_distance = abs((day - item.date).days)
            movement_cost = day_distance * penalties.day_change
            if isinstance(item, FlexibleTask) and item.start_slot is not None:
                shift = abs((day - item.date).days * 48 + start - item.start_slot)
                item_displacement.append(shift * variable)
                if shift:
                    movement_cost += penalties.moved_task + shift * penalties.displacement_slot
            objective_terms.append(variable * (movement_cost * score_scale + tie_cost))

        placement_vars[item.id] = candidates
        if item_displacement:
            displacements.append(sum(item_displacement))
        decisions = [variable for _, _, variable in candidates]
        if isinstance(item, FlexibleTask) and not protected and item.id not in required_ids:
            deferred = model.new_bool_var(f"defer_{index}")
            deferred_vars[item.id] = deferred
            decisions.append(deferred)
            deadline_offset = sum(SLOTS_PER_DAY for day in horizon if day < item.deadline_date) + item.deadline_slot
            defer_tie = max(0, total_slots - deadline_offset) * (count + 1) + count - index
            objective_terms.append(deferred * (defer_weight + defer_tie))
        model.add(sum(decisions) == 1)

    for slots in occupancy.values():
        for variables in slots:
            if variables:
                model.add(sum(variables) <= 1)
    largest = model.new_int_var(0, max_shift, "largest_displacement")
    model.add_max_equality(largest, displacements or [0])
    model.minimize(sum(objective_terms) + largest * penalties.largest_displacement_slot * score_scale)

    for item in items:
        hinted = False
        if item.start_slot is not None:
            for day, start, variable in placement_vars[item.id]:
                value = int((day, start) == (item.date, item.start_slot))
                model.add_hint(variable, value)
                hinted = hinted or bool(value)
        if item.id in deferred_vars:
            model.add_hint(deferred_vars[item.id], int(item.start_slot is None or not hinted))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 2026
    status = solver.solve(model)
    if status == cp_model.INFEASIBLE:
        raise ScheduleConflict("Fixed, pinned, started, or selected items overlap. Choose another time or extension.")
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SolverUnavailable("The optimizer did not find a schedule in time. Your calendar was not changed.")

    for item in items:
        if item.id in deferred_vars and solver.boolean_value(deferred_vars[item.id]):
            item.start_slot = None
        else:
            item.date, item.start_slot = next(
                (day, start) for day, start, variable in placement_vars[item.id] if solver.boolean_value(variable)
            )
    return SolverResult(items=items, status="optimal" if status == cp_model.OPTIMAL else "feasible",
                        objective_value=round(solver.objective_value))
