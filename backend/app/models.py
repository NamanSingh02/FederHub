from sqlalchemy import Column, Float, Integer, String, DateTime, ForeignKey, Text
from datetime import datetime , timezone
from app.db import Base

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    # created_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="ml_engineer")
    status = Column(String, nullable=False, default="active")
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    # created_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class JobConfiguration(Base):
    __tablename__ = "job_configurations"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    round_count = Column(Integer, nullable=False, default=5)
    local_epochs = Column(Integer, nullable=False, default=3)
    expected_clients = Column(Integer, nullable=False, default=1)
    current_round = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="draft")
    results_published = Column(Integer, nullable=False, default=0)
    published_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    # created_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ClientSubmission(Base):
    __tablename__ = "client_submissions"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("job_configurations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    client_label = Column(String, nullable=False)
    round_number = Column(Integer, nullable=False)
    sample_count = Column(Integer, nullable=False)
    accuracy = Column(Float, nullable=True)
    loss = Column(Float, nullable=True)
    weights_json = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="accepted")
    # created_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class JobAssignment(Base):
    __tablename__ = "job_assignments"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("job_configurations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class RoundMetric(Base):
    __tablename__ = "round_metrics"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("job_configurations.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    accuracy = Column(Float, nullable=True)
    loss = Column(Float, nullable=True)
    num_clients = Column(Integer, nullable=True)
    total_samples = Column(Integer, nullable=True)
    global_weights_snapshot = Column(Text, nullable=True)
    completed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
