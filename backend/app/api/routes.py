from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.observability import get_logger, log_context
from app.repositories import EventRepository, ExecutionRepository, StepRepository
from app.schemas import (
    EvaluationResponse,
    EventIngest,
    EventResponse,
    ExecutionCreate,
    ExecutionListItem,
    ExecutionResponse,
    FeedbackCreate,
    FeedbackResponse,
    StepResponse,
    TimelineResponse,
)
from app.services.evaluation import EvaluationService, FeedbackService
from app.services.ingestion import ExecutionService, IngestionService

router = APIRouter()
logger = get_logger(__name__)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/executions", response_model=ExecutionResponse, status_code=status.HTTP_201_CREATED)
async def create_execution(
    body: ExecutionCreate,
    session: AsyncSession = Depends(get_session),
) -> ExecutionResponse:
    with log_context(operation="create_execution", workflow_name=body.workflow_name):
        service = ExecutionService(session)
        execution = await service.create(body.tenant_id, body.workflow_name)
        logger.info("execution created", extra={"extra_fields": {"status": execution.status}})
        return ExecutionResponse.model_validate(execution)


@router.post("/executions/{execution_id}/events", response_model=EventResponse)
async def ingest_event(
    execution_id: UUID,
    body: EventIngest,
    session: AsyncSession = Depends(get_session),
) -> EventResponse:
    with log_context(
        operation="ingest_event",
        execution_id=execution_id,
        event_id=body.event_id,
        event_type=body.event_type,
    ):
        service = IngestionService(session)
        result = await service.ingest(execution_id, body)
        logger.info(
            "event ingested",
            extra={
                "extra_fields": {
                    "deduplicated": result.deduplicated,
                    "step_id": result.step_id,
                    "attempt_id": result.attempt_id,
                }
            },
        )
        return result


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ExecutionResponse:
    with log_context(operation="get_execution", execution_id=execution_id):
        repo = ExecutionRepository(session)
        execution = await repo.get_with_counts(execution_id)
        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
        step_count, attempt_count, retry_count = ExecutionService.counts(execution)
        resp = ExecutionResponse.model_validate(execution)
        return resp.model_copy(
            update={
                "step_count": step_count,
                "attempt_count": attempt_count,
                "retry_count": retry_count,
            }
        )


@router.get("/executions/{execution_id}/timeline", response_model=TimelineResponse)
async def get_timeline(
    execution_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> TimelineResponse:
    with log_context(operation="get_timeline", execution_id=execution_id):
        exec_repo = ExecutionRepository(session)
        execution = await exec_repo.get_by_id(execution_id)
        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

        step_repo = StepRepository(session)
        steps = await step_repo.get_timeline(execution_id)
        return TimelineResponse(
            execution_id=execution_id,
            steps=[StepResponse.model_validate(s) for s in steps],
        )


@router.get("/executions/{execution_id}/events", response_model=list[EventResponse])
async def list_events(
    execution_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[EventResponse]:
    with log_context(operation="list_events", execution_id=execution_id):
        exec_repo = ExecutionRepository(session)
        execution = await exec_repo.get_by_id(execution_id)
        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
        event_repo = EventRepository(session)
        events = await event_repo.list_by_execution(execution_id)
        return [EventResponse.model_validate(e) for e in events]


@router.post(
    "/executions/{execution_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    execution_id: UUID,
    body: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    with log_context(operation="submit_feedback", execution_id=execution_id):
        service = FeedbackService(session)
        return await service.submit(execution_id, body)


@router.get("/executions/{execution_id}/evaluation", response_model=EvaluationResponse)
async def get_evaluation(
    execution_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> EvaluationResponse:
    with log_context(operation="get_evaluation", execution_id=execution_id):
        service = EvaluationService(session)
        return await service.evaluate(execution_id)


@router.get("/executions", response_model=list[ExecutionListItem])
async def list_executions(
    status_filter: str | None = Query(None, alias="status"),
    workflow_name: str | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ExecutionListItem]:
    if started_after and started_before and started_after > started_before:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="started_after must be before started_before",
        )

    with log_context(operation="list_executions", status=status_filter):
        repo = ExecutionRepository(session)
        executions = await repo.list_executions(
            status=status_filter,
            workflow_name=workflow_name,
            started_after=started_after,
            started_before=started_before,
        )
        items: list[ExecutionListItem] = []
        for ex in executions:
            _, attempt_count, retry_count = ExecutionService.counts(ex)
            items.append(
                ExecutionListItem(
                    id=ex.id,
                    tenant_id=ex.tenant_id,
                    workflow_name=ex.workflow_name,
                    status=ex.status,
                    started_at=ex.started_at,
                    completed_at=ex.completed_at,
                    created_at=ex.created_at,
                    duration_ms=ExecutionService.duration_ms(ex),
                    retry_count=retry_count,
                )
            )
        return items
