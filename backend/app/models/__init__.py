from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


EXECUTION_STATUSES = ("pending", "running", "waiting", "completed", "failed", "cancelled")
STEP_STATUSES = ("pending", "running", "waiting", "completed", "failed", "cancelled")
ATTEMPT_STATUSES = ("pending", "running", "succeeded", "failed", "cancelled")


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in EXECUTION_STATUSES)})",
            name="ck_executions_status",
        ),
        Index("ix_executions_status", "status"),
        Index("ix_executions_started_at", "started_at"),
        Index("ix_executions_workflow_name", "workflow_name"),
        Index("ix_executions_tenant_started", "tenant_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    workflow_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    steps: Mapped[list["Step"]] = relationship(back_populates="execution", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(back_populates="execution", cascade="all, delete-orphan")
    feedback_entries: Mapped[list["Feedback"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )


class Step(Base):
    __tablename__ = "steps"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in STEP_STATUSES)})",
            name="ck_steps_status",
        ),
        UniqueConstraint("execution_id", "sequence_number", name="uq_steps_execution_sequence"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False
    )
    parent_step_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("steps.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    execution: Mapped["Execution"] = relationship(back_populates="steps")
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="step",
        cascade="all, delete-orphan",
        order_by="Attempt.attempt_number",
    )
    events: Mapped[list["Event"]] = relationship(back_populates="step")


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in ATTEMPT_STATUSES)})",
            name="ck_attempts_status",
        ),
        UniqueConstraint("step_id", "attempt_number", name="uq_attempts_step_number"),
        UniqueConstraint("idempotency_key", name="uq_attempts_idempotency_key"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    step_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("steps.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    step: Mapped["Step"] = relationship(back_populates="attempts")
    events: Mapped[list["Event"]] = relationship(back_populates="attempt")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_execution_timestamp", "execution_id", "timestamp"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("steps.id", ondelete="SET NULL"), nullable=True
    )
    attempt_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attempts.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    execution: Mapped["Execution"] = relationship(back_populates="events")
    step: Mapped["Step | None"] = relationship(back_populates="events")
    attempt: Mapped["Attempt | None"] = relationship(back_populates="events")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    execution: Mapped["Execution"] = relationship(back_populates="feedback_entries")
