import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from models import Base, JobConfiguration, RoundMetric, ClientSubmission, JobAssignment

SERVICE_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = SERVICE_ROOT.parent / "backend"
DEFAULT_LOCAL_DB_PATH = BACKEND_ROOT / "federhub_local.db"

load_dotenv(SERVICE_ROOT / ".env")

def _get_database_url(database_url: str | None = None):
    """Resolve the database URL with explicit override first, then env, then local fallback."""
    url = (database_url or os.environ.get("DATABASE_URL", "")).strip()

    if url.startswith("postgresql"):
        print("[DB-ROUTER] Production PostgreSQL URL detected. Connecting to AWS...")
        return url
    if url.startswith("sqlite"):
        print("[DB-ROUTER] SQLite URL detected. Connecting to local development database...")
        return url

    final_url = f"sqlite:///{DEFAULT_LOCAL_DB_PATH.as_posix()}"
    print("[DB-ROUTER] No DATABASE_URL provided. Falling back to local SQLite database.")
    return final_url

def create_db_session(database_url: str = None):
    url = _get_database_url(database_url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    else:
        RoundMetric.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return Session(), engine

def fetch_job_config(session, job_id: int) -> dict:
    job = session.query(JobConfiguration).filter(JobConfiguration.id == job_id).first()
    if not job:
        raise ValueError(f"Job with id={job_id} not found in the database.")
    return {
        "id": job.id,
        "job_name": job.job_name,
        "round_count": job.round_count,
        "local_epochs": job.local_epochs,
        "expected_clients": job.expected_clients, 
        "status": job.status,
        "created_at": job.created_at,
    }

def validate_job_assignment(session, job_id: int, user_id: int) -> bool:
    """Return True only when the authenticated client is assigned to the job."""
    assignment = (
        session.query(JobAssignment)
        .filter(
            JobAssignment.job_id == job_id,
            JobAssignment.user_id == user_id,
        )
        .first()
    )
    return assignment is not None

VALID_STATUSES = {"draft", "scheduled", "running", "completed", "failed"}

def update_job_status(session, job_id: int, new_status: str) -> dict:
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{new_status}'.")

    job = session.query(JobConfiguration).filter(JobConfiguration.id == job_id).first()
    if not job:
        raise ValueError(f"Job with id={job_id} not found in the database.")

    job.status = new_status
    session.commit()
    session.refresh(job)
    return {
        "id": job.id,
        "job_name": job.job_name,
        "status": job.status,
    }

def record_round_metric(
    session,
    job_id: int,
    round_number: int,
    accuracy: float = None,
    loss: float = None,
    num_clients: int = None,
    total_samples: int = None,
    global_weights_snapshot: dict = None,
) -> RoundMetric:
    snapshot_json = None
    if global_weights_snapshot is not None:
        snapshot_json = json.dumps(global_weights_snapshot)

    metric = RoundMetric(
        job_id=job_id,
        round_number=round_number,
        accuracy=accuracy,
        loss=loss,
        num_clients=num_clients,
        total_samples=total_samples,
        global_weights_snapshot=snapshot_json,
        completed_at=datetime.now(timezone.utc),
    )
    session.add(metric)
    
    job = session.query(JobConfiguration).filter(JobConfiguration.id == job_id).first()
    if job:
        expected_clients = job.expected_clients or 1
        round_has_all_expected_clients = (
            num_clients is None or num_clients >= expected_clients
        )
        if round_has_all_expected_clients:
            job.current_round = round_number + 1
        else:
            job.current_round = round_number

        if round_number >= job.round_count and round_has_all_expected_clients:
            job.status = "completed"
        elif job.status != "failed":
            job.status = "running"

    session.commit()
    session.refresh(metric)
    return metric

def fetch_latest_round_metric(session, job_id: int):
    """Return the most recent RoundMetric row for a job, or None."""
    return (
        session.query(RoundMetric)
        .filter(RoundMetric.job_id == job_id)
        .order_by(RoundMetric.round_number.desc(), RoundMetric.completed_at.desc())
        .first()
    )


def get_round_metrics(session, job_id: int) -> list:
    metrics = (
        session.query(RoundMetric)
        .filter(RoundMetric.job_id == job_id)
        .order_by(RoundMetric.round_number)
        .all()
    )

    return [
        {
            "id": m.id,
            "job_id": m.job_id,
            "round_number": m.round_number,
            "accuracy": m.accuracy,
            "loss": m.loss,
            "num_clients": m.num_clients,
            "total_samples": m.total_samples,
            "global_weights_snapshot": (
                json.loads(m.global_weights_snapshot)
                if m.global_weights_snapshot
                else None
            ),
            "completed_at": m.completed_at,
        }
        for m in metrics
    ]

def record_client_submission(session, job_id: int, client_id_str: str, round_number: int, sample_count: int, state_dict: dict, accuracy: float = None, loss: float = None, user_id: int = None):
    """Logs the gRPC submission so FastAPI unlocks the UI graphs for this client."""
    try:
        label = client_id_str
        if user_id is None:
            if not client_id_str.startswith("client_id_"):
                raise ValueError(
                    f"Cannot record submission: client_id '{client_id_str}' is not in the expected "
                    f"'client_id_<int>' format and no explicit user_id was provided."
                )
            try:
                user_id = int(client_id_str.replace("client_id_", ""))
            except ValueError:
                raise ValueError(
                    f"Cannot record submission: could not parse integer user_id from '{client_id_str}'."
                )

        flat_weights = []
        for layer in state_dict.values():
            flat_weights.extend(layer["data"])

        submission = ClientSubmission(
            job_id=job_id,
            user_id=user_id,
            client_label=label,
            round_number=round_number,
            sample_count=sample_count,
            accuracy=accuracy,
            loss=loss,
            weights_json=json.dumps(flat_weights),
            status="aggregated"
        )
        session.add(submission)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[DB-CONNECTOR WARNING] Could not log client submission: {e}")
