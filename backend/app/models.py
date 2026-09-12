from datetime import date as LocalDate
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, TypeAdapter, model_validator
from pydantic.alias_generators import to_camel

SLOTS_PER_DAY = 32
StartSlot = Annotated[int, Field(strict=True, ge=0, lt=SLOTS_PER_DAY)]
SlotCount = Annotated[int, Field(strict=True, ge=1, le=SLOTS_PER_DAY)]


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True,
        extra="forbid", str_strip_whitespace=True,
    )


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


class PreviewRequest(ApiModel):
    operation: Operation
    time_zone: str = Field(min_length=1, max_length=100)


class CommitRequest(ApiModel):
    preview_token: str = Field(min_length=1, max_length=100)


class ScheduleChange(ApiModel):
    item_id: str
    title: str
    change_type: Literal["extended", "moved", "deferred", "scheduled", "restored"]
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
    schedule: DaySchedule
