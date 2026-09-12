from datetime import date as LocalDate, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, StrictBool, TypeAdapter, model_validator
from pydantic.alias_generators import to_camel

SLOTS_PER_DAY = 32
DEMO_START = LocalDate(2026, 9, 11)
DEMO_END = LocalDate(2026, 9, 13)
DEMO_TIME_ZONE = "America/New_York"
StartSlot = Annotated[int, Field(strict=True, ge=0, lt=SLOTS_PER_DAY)]
SlotCount = Annotated[int, Field(strict=True, ge=1, le=SLOTS_PER_DAY)]


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True,
        extra="forbid", str_strip_whitespace=True,
    )


class DemoClockUpdate(ApiModel):
    now: NaiveDatetime

    @model_validator(mode="after")
    def within_demo(self) -> Self:
        if not DEMO_START <= self.now.date() <= DEMO_END:
            raise ValueError("Choose a demo time from September 11–13, 2026.")
        return self


class DemoClock(ApiModel):
    now: datetime
    revision: int
    time_zone: str = DEMO_TIME_ZONE
    start_date: LocalDate = DEMO_START
    end_date: LocalDate = DEMO_END


class ItemBase(ApiModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=120)
    date: LocalDate
    duration_slots: SlotCount
    is_pinned: StrictBool = False
    accent: Literal["purple", "orange", "blue", "green"] = "purple"
    note: str = Field(default="", max_length=240)


class FixedEvent(ItemBase):
    kind: Literal["fixed"]
    start_slot: StartSlot

    @model_validator(mode="after")
    def within_day(self) -> Self:
        if self.start_slot + self.duration_slots > SLOTS_PER_DAY:
            raise ValueError("The event must end by midnight.")
        return self


class FlexibleTask(ItemBase):
    kind: Literal["flexible"]
    start_slot: StartSlot | None = None
    deadline_slot: SlotCount

    @model_validator(mode="after")
    def valid_placement(self) -> Self:
        if self.start_slot is not None and self.start_slot + self.duration_slots > SLOTS_PER_DAY:
            raise ValueError("The task must end by midnight.")
        if self.is_pinned:
            if self.start_slot is None:
                raise ValueError("Schedule a task before pinning it.")
            if self.start_slot + self.duration_slots > self.deadline_slot:
                raise ValueError("A pinned task must finish by its deadline.")
        return self


CalendarItem = Annotated[FixedEvent | FlexibleTask, Field(discriminator="kind")]
item_adapter = TypeAdapter(CalendarItem)


class PinUpdate(ApiModel):
    is_pinned: StrictBool


class RescheduleRequest(ApiModel):
    item_id: str = Field(min_length=1, max_length=80)
    additional_slots: Annotated[int, Field(strict=True, ge=1, le=4)]
    time_zone: str = "UTC"


class MoveOperation(ApiModel):
    type: Literal["move"]
    item_id: str = Field(min_length=1, max_length=80)
    target_start_slot: StartSlot


class ExtendOperation(ApiModel):
    type: Literal["extend"]
    item_id: str = Field(min_length=1, max_length=80)
    additional_slots: Annotated[int, Field(strict=True, ge=1, le=4)]


Operation = Annotated[MoveOperation | ExtendOperation, Field(discriminator="type")]


class PenaltyWeights(ApiModel):
    moved_task: Annotated[int, Field(strict=True, ge=0, le=1000)] = 1
    displacement_slot: Annotated[int, Field(strict=True, ge=0, le=1000)] = 2
    largest_displacement_slot: Annotated[int, Field(strict=True, ge=0, le=1000)] = 4


class PreviewRequest(ApiModel):
    operation: Operation
    time_zone: str = Field(min_length=1, max_length=100)
    penalties: PenaltyWeights | None = None


class CommitRequest(ApiModel):
    preview_token: str = Field(min_length=1, max_length=100)


class FixedEventDraft(ApiModel):
    kind: Literal["fixed"]
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=120)
    date: LocalDate
    duration_slots: SlotCount
    accent: Literal["purple", "orange", "blue", "green"] = "blue"
    note: str = Field(default="", max_length=240)


class FlexibleTaskDraft(ApiModel):
    kind: Literal["flexible"]
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=120)
    date: LocalDate
    duration_slots: SlotCount
    deadline_slot: SlotCount
    accent: Literal["purple", "orange", "blue", "green"] = "purple"
    note: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def can_fit_before_deadline(self) -> Self:
        if self.duration_slots > self.deadline_slot:
            raise ValueError("The task duration must fit before its deadline.")
        return self


ProposalItemDraft = Annotated[FixedEventDraft | FlexibleTaskDraft, Field(discriminator="kind")]


class ProposalOptionsRequest(ApiModel):
    item: ProposalItemDraft
    candidate_start_slots: list[StartSlot] | None = Field(default=None, min_length=1, max_length=4)
    time_zone: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid_candidates(self) -> Self:
        if isinstance(self.item, FixedEventDraft) and self.candidate_start_slots is None:
            raise ValueError("Choose a start time for a fixed event.")
        if isinstance(self.item, FlexibleTaskDraft) and self.candidate_start_slots is not None:
            raise ValueError("Flexible task alternatives are selected by the optimizer.")
        if self.candidate_start_slots is not None and len(set(self.candidate_start_slots)) != len(self.candidate_start_slots):
            raise ValueError("Choose different candidate start times.")
        return self


class AcceptProposalRequest(ApiModel):
    alternative_id: str = Field(min_length=1, max_length=100)


class ScheduleChange(ApiModel):
    item_id: str
    title: str
    change_type: Literal["added", "extended", "moved", "deferred", "scheduled", "restored"]
    from_start_slot: int | None = None
    to_start_slot: int | None = None
    from_duration_slots: int | None = None
    to_duration_slots: int | None = None
    reason: str


class DaySchedule(ApiModel):
    date: LocalDate
    items: list[CalendarItem]
    changes: list[ScheduleChange] = Field(default_factory=list)
    can_undo: bool = False
    solver_status: Literal["optimal", "feasible"] | None = None


class SchedulePreview(ApiModel):
    preview_token: str
    expires_in_seconds: int
    operation: Operation
    earliest_start_slot: int
    penalties: PenaltyWeights
    schedule: DaySchedule


class ProposalMetrics(ApiModel):
    moved_task_count: int
    total_shift_slots: int
    deferred_task_count: int


class ProposalAlternative(ApiModel):
    id: str
    label: str
    start_slot: StartSlot
    schedule: DaySchedule
    metrics: ProposalMetrics


class ProposalSet(ApiModel):
    proposal_set_id: str
    expires_in_seconds: int
    date: LocalDate
    alternatives: list[ProposalAlternative]
