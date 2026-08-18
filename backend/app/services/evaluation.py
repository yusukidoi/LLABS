from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, Feedback
from app.repositories import EventRepository, ExecutionRepository, FeedbackRepository, StepRepository
from app.schemas import EvaluationResponse, FeedbackCreate, FeedbackResponse
from app.services.ingestion import ExecutionService


class EvaluationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.executions = ExecutionRepository(session)
        self.feedback = FeedbackRepository(session)

    async def evaluate(self, execution_id: UUID) -> EvaluationResponse:
        execution = await self.executions.get_with_counts(execution_id)
        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

        step_count, attempt_count, retry_count = ExecutionService.counts(execution)
        failed_step_count = sum(1 for s in execution.steps if s.status == "failed")
        duration_ms = ExecutionService.duration_ms(execution)
        latest_feedback = await self.feedback.get_latest(execution_id)

        human_review_status = latest_feedback.decision if latest_feedback else "none"
        reliability_score = max(0.0, min(1.0, 1.0 - retry_count / max(attempt_count, 1)))

        return EvaluationResponse(
            execution_id=execution.id,
            successful=execution.status == "completed",
            total_steps=step_count,
            total_attempts=attempt_count,
            retry_count=retry_count,
            failed_step_count=failed_step_count,
            total_duration_ms=duration_ms,
            human_review_status=human_review_status,
            final_outcome=execution.status,
            reliability_score=round(reliability_score, 4),
        )


class FeedbackService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.executions = ExecutionRepository(session)
        self.feedback_repo = FeedbackRepository(session)
        self.events = EventRepository(session)

    async def submit(self, execution_id: UUID, data: FeedbackCreate) -> FeedbackResponse:
        execution = await self.executions.get_by_id(execution_id, for_update=True)
        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

        feedback = Feedback(
            execution_id=execution_id,
            decision=data.decision,
            comment=data.comment,
        )
        await self.feedback_repo.create(feedback)
        await self.session.flush()

        event = Event(
            id=uuid4(),
            execution_id=execution_id,
            event_type="feedback.received",
            timestamp=datetime.now(timezone.utc),
            payload={"decision": data.decision, "comment": data.comment},
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(feedback)

        return FeedbackResponse.model_validate(feedback)
