from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Attempt, Event, Execution, Feedback, Step


class ExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, execution: Execution) -> Execution:
        self.session.add(execution)
        await self.session.flush()
        return execution

    async def get_by_id(self, execution_id: UUID, *, for_update: bool = False) -> Execution | None:
        stmt = select(Execution).where(Execution.id == execution_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_counts(self, execution_id: UUID) -> Execution | None:
        stmt = (
            select(Execution)
            .where(Execution.id == execution_id)
            .options(
                selectinload(Execution.steps).selectinload(Step.attempts),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_executions(
        self,
        *,
        status: str | None = None,
        workflow_name: str | None = None,
        started_after=None,
        started_before=None,
    ) -> list[Execution]:
        stmt = select(Execution).options(
            selectinload(Execution.steps).selectinload(Step.attempts),
        )
        if status:
            stmt = stmt.where(Execution.status == status)
        if workflow_name:
            stmt = stmt.where(Execution.workflow_name == workflow_name)
        if started_after:
            stmt = stmt.where(Execution.started_at >= started_after)
        if started_before:
            stmt = stmt.where(Execution.started_at <= started_before)
        stmt = stmt.order_by(Execution.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())


class StepRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_execution_and_sequence(
        self, execution_id: UUID, sequence_number: int
    ) -> Step | None:
        stmt = select(Step).where(
            Step.execution_id == execution_id,
            Step.sequence_number == sequence_number,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_timeline(self, execution_id: UUID) -> list[Step]:
        stmt = (
            select(Step)
            .where(Step.execution_id == execution_id)
            .options(selectinload(Step.attempts))
            .order_by(Step.sequence_number)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())


class AttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_step_and_number(self, step_id: UUID, attempt_number: int) -> Attempt | None:
        stmt = select(Attempt).where(
            Attempt.step_id == step_id,
            Attempt.attempt_number == attempt_number,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Attempt | None:
        stmt = select(Attempt).where(Attempt.idempotency_key == idempotency_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, event_id: UUID) -> Event | None:
        stmt = select(Event).where(Event.id == event_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_execution(self, execution_id: UUID) -> list[Event]:
        stmt = (
            select(Event)
            .where(Event.execution_id == execution_id)
            .order_by(Event.timestamp, Event.received_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def insert_if_absent(self, event: Event) -> tuple[Event, bool]:
        from sqlalchemy.dialects.postgresql import insert

        stmt = (
            insert(Event)
            .values(
                id=event.id,
                execution_id=event.execution_id,
                step_id=event.step_id,
                attempt_id=event.attempt_id,
                event_type=event.event_type,
                timestamp=event.timestamp,
                payload=event.payload,
            )
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(Event.id)
        )
        result = await self.session.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is None:
            existing = await self.get_by_id(event.id)
            if existing is None:
                raise RuntimeError("Event conflict but row not found")
            return existing, False
        stored = await self.get_by_id(event.id)
        if stored is None:
            raise RuntimeError("Inserted event not found")
        return stored, True


class FeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, feedback: Feedback) -> Feedback:
        self.session.add(feedback)
        await self.session.flush()
        return feedback

    async def get_latest(self, execution_id: UUID) -> Feedback | None:
        stmt = (
            select(Feedback)
            .where(Feedback.execution_id == execution_id)
            .order_by(Feedback.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
