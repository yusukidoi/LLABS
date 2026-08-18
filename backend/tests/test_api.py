"""Integration tests for Agent Trajectory Observatory."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@pytest.mark.asyncio
async def test_create_execution(client: AsyncClient, tenant_id):
    resp = await client.post(
        "/api/executions",
        json={"tenant_id": str(tenant_id), "workflow_name": "document_review"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["workflow_name"] == "document_review"


@pytest.mark.asyncio
async def test_ingest_events(client: AsyncClient, tenant_id):
    create = await client.post(
        "/api/executions",
        json={"tenant_id": str(tenant_id), "workflow_name": "document_review"},
    )
    execution_id = create.json()["id"]
    t0 = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)

    events = [
        {"event_id": str(uuid4()), "event_type": "execution.started", "timestamp": iso(t0)},
        {
            "event_id": str(uuid4()),
            "event_type": "step.started",
            "timestamp": iso(t0 + timedelta(seconds=1)),
            "sequence_number": 1,
            "step_name": "read_document",
            "step_type": "read_document",
        },
        {
            "event_id": str(uuid4()),
            "event_type": "attempt.started",
            "timestamp": iso(t0 + timedelta(seconds=2)),
            "sequence_number": 1,
            "step_name": "read_document",
            "step_type": "read_document",
            "attempt_number": 1,
            "idempotency_key": f"{execution_id}:read_document:1",
        },
        {
            "event_id": str(uuid4()),
            "event_type": "attempt.succeeded",
            "timestamp": iso(t0 + timedelta(seconds=3)),
            "sequence_number": 1,
            "step_name": "read_document",
            "step_type": "read_document",
            "attempt_number": 1,
            "idempotency_key": f"{execution_id}:read_document:1",
        },
        {
            "event_id": str(uuid4()),
            "event_type": "step.completed",
            "timestamp": iso(t0 + timedelta(seconds=4)),
            "sequence_number": 1,
            "step_name": "read_document",
            "step_type": "read_document",
        },
    ]

    for event in events:
        resp = await client.post(f"/api/executions/{execution_id}/events", json=event)
        assert resp.status_code == 200

    detail = await client.get(f"/api/executions/{execution_id}")
    assert detail.json()["status"] == "running"
    assert detail.json()["step_count"] == 1
    assert detail.json()["attempt_count"] == 1


@pytest.mark.asyncio
async def test_duplicate_event_ingestion(client: AsyncClient, tenant_id):
    create = await client.post(
        "/api/executions",
        json={"tenant_id": str(tenant_id), "workflow_name": "document_review"},
    )
    execution_id = create.json()["id"]
    event_id = str(uuid4())
    payload = {
        "event_id": event_id,
        "event_type": "execution.started",
        "timestamp": iso(datetime.now(timezone.utc)),
    }

    first = await client.post(f"/api/executions/{execution_id}/events", json=payload)
    second = await client.post(f"/api/executions/{execution_id}/events", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True

    events = await client.get(f"/api/executions/{execution_id}/events")
    assert len(events.json()) == 1


@pytest.mark.asyncio
async def test_retry_normalization(client: AsyncClient, tenant_id):
    create = await client.post(
        "/api/executions",
        json={"tenant_id": str(tenant_id), "workflow_name": "document_review"},
    )
    execution_id = create.json()["id"]
    t0 = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)

    await client.post(
        f"/api/executions/{execution_id}/events",
        json={"event_id": str(uuid4()), "event_type": "execution.started", "timestamp": iso(t0)},
    )

    step_events = [
        {
            "event_id": str(uuid4()),
            "event_type": "step.started",
            "timestamp": iso(t0 + timedelta(seconds=1)),
            "sequence_number": 2,
            "step_name": "extract_information",
            "step_type": "call_tool",
        },
        {
            "event_id": str(uuid4()),
            "event_type": "attempt.started",
            "timestamp": iso(t0 + timedelta(seconds=2)),
            "sequence_number": 2,
            "step_name": "extract_information",
            "step_type": "call_tool",
            "attempt_number": 1,
            "idempotency_key": f"{execution_id}:extract:1",
        },
        {
            "event_id": str(uuid4()),
            "event_type": "attempt.failed",
            "timestamp": iso(t0 + timedelta(seconds=3)),
            "sequence_number": 2,
            "step_name": "extract_information",
            "step_type": "call_tool",
            "attempt_number": 1,
            "idempotency_key": f"{execution_id}:extract:1",
            "payload": {"error_type": "timeout", "error_message": "tool timed out"},
        },
        {
            "event_id": str(uuid4()),
            "event_type": "attempt.retried",
            "timestamp": iso(t0 + timedelta(seconds=4)),
            "sequence_number": 2,
            "step_name": "extract_information",
            "step_type": "call_tool",
            "attempt_number": 2,
            "idempotency_key": f"{execution_id}:extract:2",
        },
        {
            "event_id": str(uuid4()),
            "event_type": "attempt.started",
            "timestamp": iso(t0 + timedelta(seconds=5)),
            "sequence_number": 2,
            "step_name": "extract_information",
            "step_type": "call_tool",
            "attempt_number": 2,
            "idempotency_key": f"{execution_id}:extract:2",
        },
        {
            "event_id": str(uuid4()),
            "event_type": "attempt.succeeded",
            "timestamp": iso(t0 + timedelta(seconds=6)),
            "sequence_number": 2,
            "step_name": "extract_information",
            "step_type": "call_tool",
            "attempt_number": 2,
            "idempotency_key": f"{execution_id}:extract:2",
        },
        {
            "event_id": str(uuid4()),
            "event_type": "step.completed",
            "timestamp": iso(t0 + timedelta(seconds=7)),
            "sequence_number": 2,
            "step_name": "extract_information",
            "step_type": "call_tool",
        },
    ]

    for event in step_events:
        resp = await client.post(f"/api/executions/{execution_id}/events", json=event)
        assert resp.status_code == 200

    timeline = await client.get(f"/api/executions/{execution_id}/timeline")
    steps = timeline.json()["steps"]
    extract = next(s for s in steps if s["name"] == "extract_information")
    assert len(extract["attempts"]) == 2
    assert extract["attempts"][0]["status"] == "failed"
    assert extract["attempts"][0]["error_type"] == "timeout"
    assert extract["attempts"][1]["status"] == "succeeded"
    assert extract["status"] == "completed"

    detail = await client.get(f"/api/executions/{execution_id}")
    assert detail.json()["retry_count"] == 1


@pytest.mark.asyncio
async def test_execution_completion(client: AsyncClient, tenant_id):
    create = await client.post(
        "/api/executions",
        json={"tenant_id": str(tenant_id), "workflow_name": "document_review"},
    )
    execution_id = create.json()["id"]
    t0 = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)

    await client.post(
        f"/api/executions/{execution_id}/events",
        json={"event_id": str(uuid4()), "event_type": "execution.started", "timestamp": iso(t0)},
    )
    await client.post(
        f"/api/executions/{execution_id}/events",
        json={
            "event_id": str(uuid4()),
            "event_type": "execution.completed",
            "timestamp": iso(t0 + timedelta(seconds=60)),
        },
    )

    detail = await client.get(f"/api/executions/{execution_id}")
    assert detail.json()["status"] == "completed"
    assert detail.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_failed_execution(client: AsyncClient, tenant_id):
    create = await client.post(
        "/api/executions",
        json={"tenant_id": str(tenant_id), "workflow_name": "document_review"},
    )
    execution_id = create.json()["id"]
    t0 = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)

    await client.post(
        f"/api/executions/{execution_id}/events",
        json={"event_id": str(uuid4()), "event_type": "execution.started", "timestamp": iso(t0)},
    )
    await client.post(
        f"/api/executions/{execution_id}/events",
        json={
            "event_id": str(uuid4()),
            "event_type": "execution.failed",
            "timestamp": iso(t0 + timedelta(seconds=10)),
            "payload": {"reason": "unrecoverable"},
        },
    )

    detail = await client.get(f"/api/executions/{execution_id}")
    assert detail.json()["status"] == "failed"

    # Cannot ingest non-feedback after terminal
    resp = await client.post(
        f"/api/executions/{execution_id}/events",
        json={"event_id": str(uuid4()), "event_type": "execution.started", "timestamp": iso(t0)},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_human_feedback(client: AsyncClient, tenant_id):
    create = await client.post(
        "/api/executions",
        json={"tenant_id": str(tenant_id), "workflow_name": "document_review"},
    )
    execution_id = create.json()["id"]

    feedback = await client.post(
        f"/api/executions/{execution_id}/feedback",
        json={"decision": "accepted", "comment": "Looks good"},
    )
    assert feedback.status_code == 201
    assert feedback.json()["decision"] == "accepted"

    events = await client.get(f"/api/executions/{execution_id}/events")
    assert any(e["event_type"] == "feedback.received" for e in events.json())


@pytest.mark.asyncio
async def test_timeline_ordering(client: AsyncClient, tenant_id):
    create = await client.post(
        "/api/executions",
        json={"tenant_id": str(tenant_id), "workflow_name": "document_review"},
    )
    execution_id = create.json()["id"]
    t0 = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)

    for seq, name in enumerate(["read_document", "validate_information"], start=1):
        await client.post(
            f"/api/executions/{execution_id}/events",
            json={
                "event_id": str(uuid4()),
                "event_type": "step.started",
                "timestamp": iso(t0 + timedelta(seconds=seq)),
                "sequence_number": seq,
                "step_name": name,
                "step_type": name,
            },
        )
        await client.post(
            f"/api/executions/{execution_id}/events",
            json={
                "event_id": str(uuid4()),
                "event_type": "step.completed",
                "timestamp": iso(t0 + timedelta(seconds=seq, milliseconds=500)),
                "sequence_number": seq,
                "step_name": name,
                "step_type": name,
            },
        )

    timeline = await client.get(f"/api/executions/{execution_id}/timeline")
    names = [s["name"] for s in timeline.json()["steps"]]
    assert names == ["read_document", "validate_information"]


@pytest.mark.asyncio
async def test_evaluation_calculation(client: AsyncClient, tenant_id):
    create = await client.post(
        "/api/executions",
        json={"tenant_id": str(tenant_id), "workflow_name": "document_review"},
    )
    execution_id = create.json()["id"]
    t0 = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)

    await client.post(
        f"/api/executions/{execution_id}/events",
        json={"event_id": str(uuid4()), "event_type": "execution.started", "timestamp": iso(t0)},
    )

    for seq in [1, 2]:
        await client.post(
            f"/api/executions/{execution_id}/events",
            json={
                "event_id": str(uuid4()),
                "event_type": "step.started",
                "timestamp": iso(t0 + timedelta(seconds=seq)),
                "sequence_number": seq,
                "step_name": f"step_{seq}",
                "step_type": "call_tool",
            },
        )
        await client.post(
            f"/api/executions/{execution_id}/events",
            json={
                "event_id": str(uuid4()),
                "event_type": "attempt.started",
                "timestamp": iso(t0 + timedelta(seconds=seq, milliseconds=100)),
                "sequence_number": seq,
                "step_name": f"step_{seq}",
                "step_type": "call_tool",
                "attempt_number": 1,
                "idempotency_key": f"{execution_id}:step_{seq}:1",
            },
        )
        await client.post(
            f"/api/executions/{execution_id}/events",
            json={
                "event_id": str(uuid4()),
                "event_type": "attempt.succeeded",
                "timestamp": iso(t0 + timedelta(seconds=seq, milliseconds=200)),
                "sequence_number": seq,
                "step_name": f"step_{seq}",
                "step_type": "call_tool",
                "attempt_number": 1,
                "idempotency_key": f"{execution_id}:step_{seq}:1",
            },
        )
        await client.post(
            f"/api/executions/{execution_id}/events",
            json={
                "event_id": str(uuid4()),
                "event_type": "step.completed",
                "timestamp": iso(t0 + timedelta(seconds=seq, milliseconds=300)),
                "sequence_number": seq,
                "step_name": f"step_{seq}",
                "step_type": "call_tool",
            },
        )

    await client.post(
        f"/api/executions/{execution_id}/events",
        json={
            "event_id": str(uuid4()),
            "event_type": "execution.completed",
            "timestamp": iso(t0 + timedelta(seconds=30)),
        },
    )
    await client.post(
        f"/api/executions/{execution_id}/feedback",
        json={"decision": "accepted"},
    )

    eval_resp = await client.get(f"/api/executions/{execution_id}/evaluation")
    data = eval_resp.json()
    assert data["successful"] is True
    assert data["total_steps"] == 2
    assert data["total_attempts"] == 2
    assert data["retry_count"] == 0
    assert data["human_review_status"] == "accepted"
    assert data["final_outcome"] == "completed"
    assert 0 <= data["reliability_score"] <= 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_event(client: AsyncClient, tenant_id):
    create = await client.post(
        "/api/executions",
        json={"tenant_id": str(tenant_id), "workflow_name": "document_review"},
    )
    execution_id = create.json()["id"]
    event_id = str(uuid4())
    payload = {
        "event_id": event_id,
        "event_type": "execution.started",
        "timestamp": iso(datetime.now(timezone.utc)),
    }

    import asyncio

    responses = await asyncio.gather(
        client.post(f"/api/executions/{execution_id}/events", json=payload),
        client.post(f"/api/executions/{execution_id}/events", json=payload),
    )
    assert all(r.status_code == 200 for r in responses)
    dedup_count = sum(1 for r in responses if r.json().get("deduplicated"))
    assert dedup_count >= 1

    events = await client.get(f"/api/executions/{execution_id}/events")
    assert len(events.json()) == 1
