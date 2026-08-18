# Agent Trajectory Observatory

A small, production-minded prototype for observing long-running agent executions. It captures raw events, maintains normalized execution/step/attempt state, supports idempotent ingestion, and exposes query/evaluation APIs plus a trace explorer UI.

Built as an interview project demonstrating practical engineering around agent observability—not a causal-learning system.

## 1. Problem

Agent runtimes emit noisy, at-least-once telemetry: retries, partial failures, human-in-the-loop pauses, and duplicate deliveries. Product queries ("show me this run's timeline", "how many retries?", "did a human accept it?") need normalized state. Debugging and future learning need the immutable raw history.

This prototype provides the **observability and execution-data foundation** a future learning system could consume.

## 2. Architecture

```
Agent / Simulator
       |
       v
FastAPI Event Ingestion
       |
       +--> Raw Event Persistence (append-only)
       |
       +--> Execution / Step / Attempt State (normalized)
       |
       +--> Retry Normalization
       |
       v
   PostgreSQL
       |
       v
Query + Evaluation APIs
       |
       v
Next.js Trace Explorer
```

**Components:**
- **Backend** (`backend/`): FastAPI + SQLAlchemy 2 async + Alembic
- **Frontend** (`frontend/`): Next.js 14 + TypeScript + Tailwind
- **Database**: PostgreSQL 16 with JSONB for flexible payloads
- **Infra**: Docker Compose (postgres, api, web)

## 3. Data model

| Entity | Purpose |
|--------|---------|
| **Execution** | One logical agent task (workflow run) |
| **Step** | One logical operation within an execution |
| **Attempt** | One try at a step—retries create new attempts, not new steps |
| **Event** | Append-only raw telemetry from producers |
| **Feedback** | Human review decisions (also emitted as `feedback.received` event) |

### Status values

- **Execution/Step:** `pending`, `running`, `waiting`, `completed`, `failed`, `cancelled`
- **Attempt:** `pending`, `running`, `succeeded`, `failed`, `cancelled`
- Timeouts are `attempt.status=failed` + `error_type=timeout`

## 4. Why execution, step, attempt, and event are separate

- **Event** = what the agent *said happened* (immutable audit log)
- **Attempt** = one physical try (retries are first-class)
- **Step** = the logical unit of work (stable across retries)
- **Execution** = the whole task rollup

Separating them lets you query "how many retries on extract_information?" without parsing raw JSON, while still reconstructing exact delivery order from events when debugging.

## 5. Retry semantics

A retry **never** creates a new Step. It creates a new Attempt under the same `(execution_id, sequence_number)`.

Example (`extract_information`):
```
Attempt 1 → timeout (failed)
Attempt 2 → success
Step status → completed (rollup)
```

The timeline API nests attempts under their step so retries are visually obvious.

## 6. Idempotency strategy

`POST /api/executions/{id}/events` accepts a producer-generated `event_id`.

- Same `event_id` submitted twice → **200 OK**, `deduplicated: true`, no state change
- Enforced by `PRIMARY KEY` on `events.id`
- Protects against at-least-once delivery and client retries

**We do not claim exactly-once processing.** We assume at-least-once delivery and make ingestion idempotent. Concurrent duplicate inserts are resolved by the unique constraint; one writer wins, the other returns the existing event.

Attempt-level idempotency uses a separate `idempotency_key` with a global unique constraint.

## 7. Raw versus normalized data

| | Raw events | Normalized state |
|---|-----------|------------------|
| **Storage** | `events` table, append-only | `executions`, `steps`, `attempts` |
| **Purpose** | Debugging, reconstruction, future ML | Product queries, evaluation, UI |
| **Updates** | Never updated/deleted | Updated by ingestion reducer |
| **Consistency** | Written in same transaction as reducer | Derived from events on ingest |

If the reducer rejects an event (e.g. conflicting terminal status), the transaction rolls back and the event is not persisted.

## 8. Evaluation approach

Rule-based, computed on read (`GET /evaluation`):

- `successful` = execution.status == completed
- `retry_count` = total_attempts - total_steps
- `reliability_score` = `1 - retry_count / max(total_attempts, 1)` (clamped 0–1)

This is **illustrative**, not production ML evaluation. The formula is explicit so you can discuss tradeoffs in an interview.

## 9. Running locally

### Docker Compose (recommended)

```bash
docker compose up --build
```

- API: http://localhost:8000
- UI: http://localhost:3000
- API docs: http://localhost:8000/docs

### Seed the demo trajectory

```bash
cd backend
pip install -r requirements.txt
python scripts/simulate_document_review.py
```

Then open http://localhost:3000 and click the execution. The `extract_information` step shows attempt 1 timeout → attempt 2 success.

### Host development (faster iteration)

```bash
# Terminal 1: database only
docker compose up postgres

# Terminal 2: API
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Terminal 3: frontend
cd frontend
npm install
npm run dev
```

Set `DATABASE_URL=postgresql+asyncpg://trajectory:trajectory@localhost:5432/trajectory` if needed.

## 10. Testing

```bash
cd backend
pip install -r requirements.txt

# Requires Postgres with trajectory_test database
# (created automatically by docker-compose init script)
pytest -v
```

Tests cover:
1. Creating an execution
2. Ingesting events
3. Duplicate event ingestion (idempotency)
4. Retry normalization (two attempts, one step)
5. Execution completion
6. Failed execution + terminal guard
7. Human feedback
8. Timeline ordering
9. Evaluation calculation
10. Concurrent duplicate event ingestion

## 11. Known limitations

- PostgreSQL stores both transactional state and event history (no separate cold archive)
- Very large telemetry volumes would need partitioned raw storage or an object store
- No message broker—agents call the API directly
- No distributed tracing backend (structured JSON logs only; OpenTelemetry-ready hook exists)
- No production tenant authorization (`tenant_id` is stored but not enforced)
- No semantic or causal trajectory retrieval
- Evaluation is rule-based, not learned
- Long-running workflow orchestration is *represented* but not implemented as a durable workflow engine (Temporal/Cadence)
- Single-process ingestion reducer (no horizontal fan-out)

## 12. How I would scale this in production

```
Agent Runtime
      |
      v
  Event Bus (Kafka/SQS/Pulsar)
      |
      +------------------------+
      |                        |
      v                        v
Operational Store          Raw Event Archive
(Postgres/Cockroach)       (S3 + Parquet/Iceberg)
      |
      v
Trajectory Processor (stream or batch)
      |
      +------------------------+
      |                        |
      v                        v
Evaluation Layer           Experience Representation
      |
      v
Retrieval / Learning
```

Possible evolution paths (options, not requirements):
- **Event bus** for decoupled ingestion at agent scale
- **Separate raw archive** for cheap long-retention telemetry
- **Stream processor** for normalized state updates (Flink, Materialize, or custom)
- **OpenTelemetry** export replacing the no-op span wrapper
- **Workflow engine** for durable orchestration; this service remains the observability sink
- **Column promotion** for high-value metadata fields instead of indexing arbitrary JSONB

---

## API summary

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/executions` | Create execution |
| POST | `/api/executions/{id}/events` | Ingest event (idempotent) |
| GET | `/api/executions/{id}` | Normalized execution state |
| GET | `/api/executions/{id}/timeline` | Steps + attempts timeline |
| GET | `/api/executions/{id}/events` | Raw events |
| POST | `/api/executions/{id}/feedback` | Human feedback |
| GET | `/api/executions/{id}/evaluation` | Rule-based evaluation |
| GET | `/api/executions` | List with filters |

## Observability

Structured JSON logs include `execution_id`, `step_id`, `attempt_id`, `event_id`, `operation`, and `status` when available. See `app/observability.py` for a no-op `trace_span` context manager that could be swapped for OpenTelemetry later.

## License

MIT (prototype / interview project)
