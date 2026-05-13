from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ── Mirror of Alpha's table (read-only from Gamma's perspective) ─────────────

class JobConfiguration(Base):
    """
    Mirror of Alpha's job_configurations table.
    """
    __tablename__ = "job_configurations"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String, nullable=False)
    round_count = Column(Integer, nullable=False, default=5)
    local_epochs = Column(Integer, nullable=False, default=3)
    
    # --- ADD THIS LINE so Gamma knows how many clients make up 1 round ---
    expected_clients = Column(Integer, nullable=False, default=1) 
    
    status = Column(String, nullable=False, default="draft")
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Gamma-owned table ────────────────────────────────────────────────────────

class RoundMetric(Base):
    """
    Per-round metrics recorded by Gamma's aggregation engine.

    After each FedAvg round completes, the aggregation server writes
    accuracy, loss, and a snapshot of the global weight summary to
    this table. Alpha's React dashboard can query this to show
    real-time training progress.
    """
    __tablename__ = "round_metrics"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("job_configurations.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    accuracy = Column(Float, nullable=True)
    loss = Column(Float, nullable=True)
    num_clients = Column(Integer, nullable=True)
    total_samples = Column(Integer, nullable=True)
    global_weights_snapshot = Column(Text, nullable=True)  # JSON summary
    completed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ClientSubmission(Base):
    """
    Mirror of Alpha's client_submissions table.
    Gamma writes to this table so the React UI knows a client has participated,
    unlocking the privacy controls and populating the tables.
    """
    __tablename__ = "client_submissions"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    client_label = Column(String, nullable=False)
    round_number = Column(Integer, nullable=False)
    sample_count = Column(Integer, nullable=False)
    accuracy = Column(Float, nullable=True)
    loss = Column(Float, nullable=True)
    weights_json = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="aggregated")
    
    # --- FIX: Changed from completed_at to created_at to match Alpha's DB ---
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class JobAssignment(Base):
    """
    Mirror of Alpha's job_assignments table.
    Gamma reads this table before accepting a gRPC update so a valid client
    cannot submit to another client's job.
    """
    __tablename__ = "job_assignments"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("job_configurations.id"), nullable=False)
    user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
