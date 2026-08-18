from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.observability import get_logger, log_context
from app.repositories import ExecutionRepository
from app.schemas import EventIngest, EventResponse, ExecutionCreate, ExecutionResponse
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
