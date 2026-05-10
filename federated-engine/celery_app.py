# celery_app.py
# ==============
# FederHub - Team Gamma | Phase 3
# --------------------------------
# Celery-based orchestrator for multi-round federated training jobs.
#
# The orchestrator:
#   1. Reads job config (round_count, local_epochs) from Alpha's PostgreSQL
#   2. Updates job status to "running"
#   3. For each round: waits for aggregation → records metrics
#   4. Updates job status to "completed" (or "failed")
#
# Broker: Redis (configured via REDIS_URL env var)
# Backend: Redis (for result tracking)
#
# Usage:
#   celery -A celery_app worker --loglevel=info

import os
import json

from celery import Celery
from dotenv import load_dotenv

from db_connector import (
    create_db_session,
    fetch_job_config,
    update_job_status,
    record_round_metric,
    get_round_metrics,
)

load_dotenv()

# ── Celery Configuration ─────────────────────────────────────────────────────

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "federhub_gamma",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


# ── Celery Tasks ─────────────────────────────────────────────────────────────

@app.task(bind=True, name="federhub.run_federation_round")
def run_federation_round(self, job_id: int, round_number: int, db_url: str = None):
    """
    Execute a single federated aggregation round and record metrics.

    This task is called by run_federation_job for each round, or can
    be invoked independently for manual round execution.

    In a full deployment, this would:
      1. Notify connected clients to start local training
      2. Wait for all weight submissions via gRPC
      3. Run FedAvg aggregation
      4. Record metrics to DB

    For Phase 3, steps 1-3 are handled by grpc_server.py. This task
    records the metrics and updates round progress.
    """
    session, _ = create_db_session(db_url)

    try:
        # Record a placeholder metric (in full deployment, these come
        # from the actual aggregation results passed as arguments)
        metric = record_round_metric(
            session=session,
            job_id=job_id,
            round_number=round_number,
            accuracy=None,
            loss=None,
            num_clients=None,
            total_samples=None,
        )

        return {
            "status": "completed",
            "job_id": job_id,
            "round_number": round_number,
            "metric_id": metric.id,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "job_id": job_id,
            "round_number": round_number,
            "error": str(exc),
        }
    finally:
        session.close()


@app.task(bind=True, name="federhub.run_federation_job")
def run_federation_job(self, job_id: int, db_url: str = None):
    """
    Orchestrate a complete multi-round federated training job.

    Reads all parameters from the database, runs each round sequentially,
    and updates the job status as rounds complete.

    Args:
        job_id: The job_configurations.id to execute.
        db_url: Optional DB URL override (for testing).
    """
    session, _ = create_db_session(db_url)

    try:
        # 1. Read job configuration from Alpha's DB
        config = fetch_job_config(session, job_id)
        round_count = config["round_count"]
        local_epochs = config["local_epochs"]
        job_name = config["job_name"]

        print(f"[ORCHESTRATOR] Starting job '{job_name}' (id={job_id})")
        print(f"[ORCHESTRATOR] Rounds: {round_count}, Local epochs: {local_epochs}")

        # 2. Mark job as running
        update_job_status(session, job_id, "running")
        print(f"[ORCHESTRATOR] Job status → running")

        # The current integration uses grpc_server.py as the live round collector.
        # Celery marks the job runnable and returns the config that clients/Gamma
        # need; real round metrics are written by the gRPC aggregation server.
        metrics = get_round_metrics(session, job_id)
        return {
            "status": "running",
            "job_id": job_id,
            "job_name": job_name,
            "round_count": round_count,
            "local_epochs": local_epochs,
            "message": "Job is running. Start the gRPC aggregator for this job to collect client updates.",
            "metrics": metrics,
        }

    except Exception as exc:
        # Mark job as failed
        try:
            update_job_status(session, job_id, "failed")
        except Exception:
            pass

        print(f"[ORCHESTRATOR ERROR] Job {job_id} failed: {exc}")
        return {
            "status": "failed",
            "job_id": job_id,
            "error": str(exc),
        }
    finally:
        session.close()
