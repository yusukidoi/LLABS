from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ATTEMPT_STATUSES,
    EXECUTION_STATUSES,
    STEP_STATUSES,
    Attempt,
    Event,
    Execution,
    Step,
)
from app.repositories import AttemptRepository, EventRepository, ExecutionRepository, StepRepository
from app.schemas import EventIngest, EventResponse

TERMINAL_EXECUTION = {"completed", "failed", "cancelled"}
TERMINAL_STEP = {"completed", "failed", "cancelled"}

STEP_EVENT_TYPES = {
    "step.started",
    "step.completed",
    "step.failed",
    "step.waiting",
}
ATTEMPT_EVENT_TYPES = {
    "attempt.started",
    "attempt.succeeded",
    "attempt.failed",
    "attempt.retried",
    "attempt.cancelled",
}
EXECUTION_EVENT_TYPES = {
    "execution.started",
    "execution.completed",
    "execution.failed",
    "execution.cancelled",
    "execution.waiting",
    "feedback.received",
}


class IngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.executions = ExecutionRepository(session)
        self.steps = StepRepository(session)
        self.attempts = AttemptRepository(session)
        self.events = EventRepository(session)

    async def ingest(self, execution_id: UUID, data: EventIngest) -> EventResponse:
        execution = await self.executions.get_by_id(execution_id)
        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

        existing = await self.events.get_by_id(data.event_id)
        if existing:
            return EventResponse.model_validate(existing, from_attributes=True).model_copy(
                update={"deduplicated": True}
            )

        if execution.status in TERMINAL_EXECUTION and data.event_type != "feedback.received":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Execution is terminal ({execution.status}); cannot ingest {data.event_type}",
            )

        event = Event(
            id=data.event_id,
            execution_id=execution_id,
            event_type=data.event_type,
            timestamp=data.timestamp,
            payload=data.payload,
        )

        _, is_new = await self.events.insert_if_absent(event)
        if not is_new:
            existing = await self.events.get_by_id(data.event_id)
            assert existing is not None
            return EventResponse.model_validate(existing, from_attributes=True).model_copy(
                update={"deduplicated": True}
            )

        locked = await self.executions.get_by_id(execution_id, for_update=True)
        if locked is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

        step: Step | None = None
        attempt: Attempt | None = None

        if data.event_type in STEP_EVENT_TYPES or data.event_type in ATTEMPT_EVENT_TYPES:
            step, attempt = await self._resolve_step_and_attempt(locked, data)

        stored = await self.events.get_by_id(data.event_id)
        assert stored is not None
        stored.step_id = step.id if step else None
        stored.attempt_id = attempt.id if attempt else None

        await self._apply_reducer(locked, step, attempt, data)
        await self.session.commit()
        await self.session.refresh(stored)

        return EventResponse.model_validate(stored, from_attributes=True)

    async def _resolve_step_and_attempt(
        self, execution: Execution, data: EventIngest
    ) -> tuple[Step, Attempt | None]:
        if data.sequence_number is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="sequence_number is required for step/attempt events",
            )
        if data.step_name is None or data.step_type is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="step_name and step_type are required for step/attempt events",
            )

        step = await self.steps.get_by_execution_and_sequence(execution.id, data.sequence_number)
        if step is None:
            step = Step(
                execution_id=execution.id,
                name=data.step_name,
                step_type=data.step_type,
                sequence_number=data.sequence_number,
                status="pending",
            )
            self.session.add(step)
            await self.session.flush()
        elif step.name != data.step_name:
            pass  # tolerate name drift on retry

        attempt: Attempt | None = None
        if data.event_type in ATTEMPT_EVENT_TYPES or data.attempt_number is not None:
            if data.attempt_number is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="attempt_number is required for attempt events",
                )
            if data.idempotency_key is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="idempotency_key is required for attempt events",
                )

            existing_key = await self.attempts.get_by_idempotency_key(data.idempotency_key)
            attempt = await self.attempts.get_by_step_and_number(step.id, data.attempt_number)

            if existing_key and attempt and existing_key.id != attempt.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="idempotency_key already used by a different attempt",
                )
            if existing_key and attempt is None:
                if existing_key.step_id != step.id or existing_key.attempt_number != data.attempt_number:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="idempotency_key already used by a different attempt",
                    )
                attempt = existing_key
            elif attempt is None:
                attempt = Attempt(
                    step_id=step.id,
                    attempt_number=data.attempt_number,
                    idempotency_key=data.idempotency_key,
                    status="pending",
                )
                self.session.add(attempt)
                await self.session.flush()
            elif attempt.idempotency_key != data.idempotency_key:
                key_owner = await self.attempts.get_by_idempotency_key(data.idempotency_key)
                if key_owner and key_owner.id != attempt.id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="idempotency_key already used by a different attempt",
                    )

        return step, attempt

    async def _apply_reducer(
        self,
        execution: Execution,
        step: Step | None,
        attempt: Attempt | None,
        data: EventIngest,
    ) -> None:
        event_type = data.event_type
        ts = data.timestamp

        if event_type == "execution.started":
            execution.status = "running"
            execution.started_at = execution.started_at or ts
        elif event_type == "execution.waiting":
            execution.status = "waiting"
        elif event_type == "execution.completed":
            self._set_terminal_execution(execution, "completed", ts)
        elif event_type == "execution.failed":
            self._set_terminal_execution(execution, "failed", ts)
        elif event_type == "execution.cancelled":
            self._set_terminal_execution(execution, "cancelled", ts)

        if step is None:
            return

        if step.status in TERMINAL_STEP and event_type.startswith("attempt."):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Step is terminal ({step.status}); cannot apply {event_type}",
            )

        if event_type == "step.started":
            step.status = "running"
            step.started_at = step.started_at or ts
        elif event_type == "step.waiting":
            step.status = "waiting"
        elif event_type == "step.completed":
            step.status = "completed"
            step.completed_at = ts
        elif event_type == "step.failed":
            step.status = "failed"
            step.completed_at = ts

        if attempt is None:
            return

        payload = data.payload or {}

        if event_type == "attempt.started":
            attempt.status = "running"
            attempt.started_at = attempt.started_at or ts
        elif event_type == "attempt.retried":
            pass  # informational; next attempt.started drives state
        elif event_type == "attempt.succeeded":
            attempt.status = "succeeded"
            attempt.completed_at = ts
            if payload.get("decision"):
                attempt.metadata_ = {**(attempt.metadata_ or {}), "decision": payload["decision"]}
        elif event_type == "attempt.failed":
            attempt.status = "failed"
            attempt.completed_at = ts
            attempt.error_type = payload.get("error_type")
            attempt.error_message = payload.get("error_message")
        elif event_type == "attempt.cancelled":
            attempt.status = "cancelled"
            attempt.completed_at = ts

    def _set_terminal_execution(self, execution: Execution, new_status: str, ts: datetime) -> None:
        if execution.status in TERMINAL_EXECUTION and execution.status != new_status:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Conflicting terminal status: {execution.status} -> {new_status}",
            )
        execution.status = new_status
        execution.completed_at = execution.completed_at or ts


class ExecutionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.executions = ExecutionRepository(session)

    async def create(self, tenant_id: UUID, workflow_name: str) -> Execution:
        execution = Execution(
            tenant_id=tenant_id,
            workflow_name=workflow_name,
            status="pending",
        )
        await self.executions.create(execution)
        await self.session.commit()
        await self.session.refresh(execution)
        return execution

    @staticmethod
    def counts(execution: Execution) -> tuple[int, int, int]:
        steps = execution.steps
        step_count = len(steps)
        attempt_count = sum(len(s.attempts) for s in steps)
        retry_count = max(0, attempt_count - step_count)
        return step_count, attempt_count, retry_count

    @staticmethod
    def duration_ms(execution: Execution) -> int | None:
        if execution.started_at and execution.completed_at:
            delta = execution.completed_at - execution.started_at
            return int(delta.total_seconds() * 1000)
        if execution.started_at:
            now = datetime.now(timezone.utc)
            return int((now - execution.started_at).total_seconds() * 1000)
        return None
