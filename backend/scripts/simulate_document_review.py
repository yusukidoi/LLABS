#!/usr/bin/env python3
"""Simulate the document_review demo trajectory."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx

API_URL = os.getenv("API_URL", "http://localhost:8000")
TENANT_ID = UUID(os.getenv("TENANT_ID", str(uuid4())))


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


async def post_event(client: httpx.AsyncClient, execution_id: str, **kwargs) -> None:
    resp = await client.post(f"/api/executions/{execution_id}/events", json=kwargs)
    resp.raise_for_status()
    data = resp.json()
    label = " (dedup)" if data.get("deduplicated") else ""
    print(f"  + {kwargs['event_type']}{label}")


async def run() -> None:
    t0 = datetime.now(timezone.utc)

    async with httpx.AsyncClient(base_url=API_URL, timeout=30.0) as client:
        health = await client.get("/api/health")
        health.raise_for_status()

        create = await client.post(
            "/api/executions",
            json={"tenant_id": str(TENANT_ID), "workflow_name": "document_review"},
        )
        create.raise_for_status()
        execution_id = create.json()["id"]
        print(f"Created execution {execution_id}")

        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="execution.started",
            timestamp=iso(t0),
        )

        # Step 1: read_document - attempt 1 success
        seq = 1
        name = "read_document"
        key = f"{execution_id}:{name}:1"
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="step.started",
            timestamp=iso(t0 + timedelta(seconds=1)),
            sequence_number=seq,
            step_name=name,
            step_type="read_document",
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="attempt.started",
            timestamp=iso(t0 + timedelta(seconds=2)),
            sequence_number=seq,
            step_name=name,
            step_type="read_document",
            attempt_number=1,
            idempotency_key=key,
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="attempt.succeeded",
            timestamp=iso(t0 + timedelta(seconds=3)),
            sequence_number=seq,
            step_name=name,
            step_type="read_document",
            attempt_number=1,
            idempotency_key=key,
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="step.completed",
            timestamp=iso(t0 + timedelta(seconds=4)),
            sequence_number=seq,
            step_name=name,
            step_type="read_document",
        )

        # Step 2: extract_information - attempt 1 timeout, attempt 2 success
        seq = 2
        name = "extract_information"
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="step.started",
            timestamp=iso(t0 + timedelta(seconds=5)),
            sequence_number=seq,
            step_name=name,
            step_type="call_tool",
        )
        key1 = f"{execution_id}:{name}:1"
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="attempt.started",
            timestamp=iso(t0 + timedelta(seconds=6)),
            sequence_number=seq,
            step_name=name,
            step_type="call_tool",
            attempt_number=1,
            idempotency_key=key1,
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="attempt.failed",
            timestamp=iso(t0 + timedelta(seconds=16)),
            sequence_number=seq,
            step_name=name,
            step_type="call_tool",
            attempt_number=1,
            idempotency_key=key1,
            payload={"error_type": "timeout", "error_message": "Tool call exceeded 10s limit"},
        )
        key2 = f"{execution_id}:{name}:2"
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="attempt.retried",
            timestamp=iso(t0 + timedelta(seconds=17)),
            sequence_number=seq,
            step_name=name,
            step_type="call_tool",
            attempt_number=2,
            idempotency_key=key2,
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="attempt.started",
            timestamp=iso(t0 + timedelta(seconds=18)),
            sequence_number=seq,
            step_name=name,
            step_type="call_tool",
            attempt_number=2,
            idempotency_key=key2,
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="attempt.succeeded",
            timestamp=iso(t0 + timedelta(seconds=22)),
            sequence_number=seq,
            step_name=name,
            step_type="call_tool",
            attempt_number=2,
            idempotency_key=key2,
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="step.completed",
            timestamp=iso(t0 + timedelta(seconds=23)),
            sequence_number=seq,
            step_name=name,
            step_type="call_tool",
        )

        # Step 3: validate_information
        seq = 3
        name = "validate_information"
        key = f"{execution_id}:{name}:1"
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="step.started",
            timestamp=iso(t0 + timedelta(seconds=24)),
            sequence_number=seq,
            step_name=name,
            step_type="validate_result",
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="attempt.started",
            timestamp=iso(t0 + timedelta(seconds=25)),
            sequence_number=seq,
            step_name=name,
            step_type="validate_result",
            attempt_number=1,
            idempotency_key=key,
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="attempt.succeeded",
            timestamp=iso(t0 + timedelta(seconds=26)),
            sequence_number=seq,
            step_name=name,
            step_type="validate_result",
            attempt_number=1,
            idempotency_key=key,
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="step.completed",
            timestamp=iso(t0 + timedelta(seconds=27)),
            sequence_number=seq,
            step_name=name,
            step_type="validate_result",
        )

        # Step 4: human_review
        seq = 4
        name = "human_review"
        key = f"{execution_id}:{name}:1"
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="step.started",
            timestamp=iso(t0 + timedelta(seconds=28)),
            sequence_number=seq,
            step_name=name,
            step_type="wait_for_human",
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="attempt.started",
            timestamp=iso(t0 + timedelta(seconds=29)),
            sequence_number=seq,
            step_name=name,
            step_type="wait_for_human",
            attempt_number=1,
            idempotency_key=key,
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="attempt.succeeded",
            timestamp=iso(t0 + timedelta(seconds=35)),
            sequence_number=seq,
            step_name=name,
            step_type="wait_for_human",
            attempt_number=1,
            idempotency_key=key,
            payload={"decision": "accepted"},
        )
        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="step.completed",
            timestamp=iso(t0 + timedelta(seconds=36)),
            sequence_number=seq,
            step_name=name,
            step_type="wait_for_human",
        )

        await post_event(
            client,
            execution_id,
            event_id=str(uuid4()),
            event_type="execution.completed",
            timestamp=iso(t0 + timedelta(seconds=40)),
        )

        feedback = await client.post(
            f"/api/executions/{execution_id}/feedback",
            json={"decision": "accepted", "comment": "Document review approved"},
        )
        feedback.raise_for_status()

        evaluation = await client.get(f"/api/executions/{execution_id}/evaluation")
        evaluation.raise_for_status()
        print("\nEvaluation:", evaluation.json())
        print(f"\nView at http://localhost:3000/executions/{execution_id}")


if __name__ == "__main__":
    asyncio.run(run())
