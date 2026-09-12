from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ortools.sat.python import cp_model

from .models import CalendarItem, FixedEvent, FlexibleTask, SLOTS_PER_DAY


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
    earliest_start_slot: int = 0,
    time_limit_seconds: float = 0.5,
) -> SolverResult:
    """Optimize one day without mutating the input.

    The integer objective is lexicographic by construction: defer count, moved
    count, total displacement, then deterministic scheduling preferences.
    """
    items = [item.model_copy(deep=True) for item in source]
    if len({item.id for item in items}) != len(items):
        raise ScheduleConflict("Each item must have a unique ID.")
    if len({item.date for item in items}) > 1:
        raise ScheduleConflict("Schedule one day at a time.")
    item_ids = {item.id for item in items}
    if (locked_ids | required_ids) - item_ids:
        raise ScheduleConflict("The selected item no longer exists.")
    if locked_ids & required_ids:
        raise ScheduleConflict("An item cannot be both locked and independently required.")
    if not 0 <= earliest_start_slot <= SLOTS_PER_DAY:
        raise ScheduleConflict("The earliest start must be within this day.")

    model = cp_model.CpModel()
    count = len(items)
    placement_vars: dict[str, list[tuple[int, cp_model.IntVar]]] = {}
    deferred_vars: dict[str, cp_model.IntVar] = {}
    occupancy: list[list[cp_model.IntVar]] = [[] for _ in range(SLOTS_PER_DAY)]

    # Bounds encode exact priority tiers in one integer objective.
    max_tie_per_item = (SLOTS_PER_DAY + 1) * (count + 1) + count
    max_tie = count * max_tie_per_item
    max_shift = count * (SLOTS_PER_DAY - 1)
    shift_weight = max_tie + 1
    move_weight = max_shift * shift_weight + max_tie + 1
    defer_weight = count * move_weight + max_shift * shift_weight + max_tie + 1
    objective_terms: list[cp_model.LinearExpr] = []

    for index, item in enumerate(items):
        protected = isinstance(item, FixedEvent) or item.is_pinned or item.id in locked_ids
        if protected:
            if item.start_slot is None:
                raise ScheduleConflict(f'“{item.title}” must be scheduled before it can be locked.')
            latest_end = item.deadline_slot if isinstance(item, FlexibleTask) else SLOTS_PER_DAY
            if item.start_slot + item.duration_slots > latest_end:
                raise ScheduleConflict(f'“{item.title}” would finish after {format_slot(latest_end)}.')
            candidate_starts = [item.start_slot]
        else:
            assert isinstance(item, FlexibleTask)
            excluded = (forbidden_starts or {}).get(item.id, frozenset())
            candidate_starts = [start for start in range(
                earliest_start_slot, item.deadline_slot - item.duration_slots + 1,
            ) if start not in excluded]

        candidates: list[tuple[int, cp_model.IntVar]] = []
        for start in candidate_starts:
            variable = model.new_bool_var(f"place_{index}_{start}")
            candidates.append((start, variable))
            for slot in range(start, start + item.duration_slots):
                occupancy[slot].append(variable)

            tie_cost = start * (count + 1) + index
            if isinstance(item, FlexibleTask) and item.start_slot is not None and start != item.start_slot:
                shift = abs(start - item.start_slot)
                objective_terms.append(variable * (move_weight + shift * shift_weight + tie_cost))
            else:
                objective_terms.append(variable * tie_cost)

        placement_vars[item.id] = candidates
        decisions = [variable for _, variable in candidates]
        if isinstance(item, FlexibleTask) and not protected and item.id not in required_ids:
            deferred = model.new_bool_var(f"defer_{index}")
            deferred_vars[item.id] = deferred
            decisions.append(deferred)
            # For final ties, defer later deadlines and newer tasks first.
            defer_tie = (SLOTS_PER_DAY - item.deadline_slot) * (count + 1) + (count - index)
            objective_terms.append(deferred * (defer_weight + defer_tie))
        model.add(sum(decisions) == 1)

    for variables in occupancy:
        if variables:
            model.add(sum(variables) <= 1)

    model.minimize(sum(objective_terms))

    # The saved schedule is a strong starting point for low-disruption search.
    for item in items:
        candidates = placement_vars[item.id]
        hinted = False
        if item.start_slot is not None:
            for start, variable in candidates:
                value = int(start == item.start_slot)
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
            item.start_slot = next(
                start for start, variable in placement_vars[item.id]
                if solver.boolean_value(variable)
            )

    return SolverResult(
        items=items,
        status="optimal" if status == cp_model.OPTIMAL else "feasible",
        objective_value=round(solver.objective_value),
    )
