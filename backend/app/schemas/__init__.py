from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExecutionCreate(BaseModel):
    tenant_id: UUID
    workflow_name: str


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    workflow_name: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    step_count: int = 0
    attempt_count: int = 0
    retry_count: int = 0


class ExecutionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    workflow_name: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    duration_ms: int | None = None
    retry_count: int = 0


class EventIngest(BaseModel):
    event_id: UUID
    event_type: str
    timestamp: datetime
    sequence_number: int | None = None
    step_name: str | None = None
    step_type: str | None = None
    attempt_number: int | None = None
    idempotency_key: str | None = None
    payload: dict | None = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    execution_id: UUID
    step_id: UUID | None
    attempt_id: UUID | None
    event_type: str
    timestamp: datetime
    payload: dict | None
    received_at: datetime
    deduplicated: bool = False


class AttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_number: int
    idempotency_key: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_type: str | None
    error_message: str | None
    metadata: dict | None = Field(default=None, validation_alias="metadata_")


class StepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    step_type: str
    sequence_number: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    attempts: list[AttemptResponse] = []


class TimelineResponse(BaseModel):
    execution_id: UUID
    steps: list[StepResponse]


class FeedbackCreate(BaseModel):
    decision: str
    comment: str | None = None


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    execution_id: UUID
    decision: str
    comment: str | None
    created_at: datetime


class EvaluationResponse(BaseModel):
    execution_id: UUID
    successful: bool
    total_steps: int
    total_attempts: int
    retry_count: int
    failed_step_count: int
    total_duration_ms: int | None
    human_review_status: str
    final_outcome: str
    reliability_score: float
