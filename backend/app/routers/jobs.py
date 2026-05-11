import io
import json
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from typing import List

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from app import models
from app.schemas import (
    AssignClientsRequest,
    ClientSubmissionCreate,
    ClientSubmissionDetail,
    ClientSubmissionOut,
    JobDetailsOut,
    JobCreate,
    JobOut,
    JobStartResponse,
    JobStatusUpdate,
    PublishResponse,
    RoundMetricDetail,
    RoundMetricOut,
    SubmissionResponse,
)
from app.auth import get_db, get_current_user, require_role
from app.limiter import limiter

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def get_assigned_user_ids(db: Session, job_id: int) -> list[int]:
    rows = db.query(models.JobAssignment.user_id).filter(
        models.JobAssignment.job_id == job_id
    ).all()
    return [r.user_id for r in rows]


def job_to_out(job: models.JobConfiguration, creator_email: str | None = None, assigned_user_ids: list[int] | None = None) -> JobOut:
    return JobOut(
        id=job.id,
        job_name=job.job_name,
        description=job.description,
        round_count=job.round_count,
        local_epochs=job.local_epochs,
        expected_clients=job.expected_clients,
        current_round=job.current_round,
        status=job.status,
        results_published=bool(job.results_published),
        published_at=job.published_at,
        created_by=job.created_by,
        creator_email=creator_email,
        created_at=job.created_at,
        assigned_user_ids=assigned_user_ids or [],
    )


def check_job_access(db: Session, job: models.JobConfiguration, current_user: models.User) -> None:
    """Raises 403 if the user does not have access to this job."""
    if current_user.role == "platform_admin":
        return
    if current_user.role == "ml_engineer":
        if job.created_by != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this job.")
        return
    # client_operator: must be assigned
    assigned = db.query(models.JobAssignment).filter(
        models.JobAssignment.job_id == job.id,
        models.JobAssignment.user_id == current_user.id,
    ).first()
    if not assigned:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this job.")


def require_published_for_client(job: models.JobConfiguration, current_user: models.User) -> None:
    if current_user.role == "client_operator" and not job.results_published:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Results are not published yet. The live dashboard and model details are visible to client operators only after the ML Engineer publishes final results.",
        )


def weighted_average(values: list[float | None], sample_counts: list[int]) -> float | None:
    pairs = [(value, count) for value, count in zip(values, sample_counts) if value is not None]
    if not pairs:
        return None
    total = sum(count for _, count in pairs)
    if total <= 0:
        return None
    return sum(value * count for value, count in pairs) / total


def aggregate_round_if_ready(db: Session, job: models.JobConfiguration) -> tuple[bool, str]:
    round_number = job.current_round or 1
    submissions = (
        db.query(models.ClientSubmission)
        .filter(
            models.ClientSubmission.job_id == job.id,
            models.ClientSubmission.round_number == round_number,
            models.ClientSubmission.status == "accepted",
        )
        .order_by(models.ClientSubmission.created_at.asc())
        .all()
    )

    if len(submissions) < job.expected_clients:
        remaining = job.expected_clients - len(submissions)
        return False, f"Update accepted for round {round_number}. Waiting for {remaining} more client update(s)."

    parsed_weights = []
    sample_counts = []
    for submission in submissions:
        try:
            weights = json.loads(submission.weights_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Submission {submission.id} has invalid weights.",
            ) from exc

        if not isinstance(weights, list) or not weights:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Submission {submission.id} has empty weights.",
            )

        coerced = [float(value) for value in weights]
        for idx, value in enumerate(coerced):
            if not math.isfinite(value):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Submission {submission.id} contains a non-finite weight at index {idx}.",
                )
            if abs(value) > 1e6:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Submission {submission.id} contains an extreme weight value at index {idx}.",
                )
        parsed_weights.append(coerced)
        sample_counts.append(submission.sample_count)

    lengths = {len(weights) for weights in parsed_weights}
    if len(lengths) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All client updates for a round must use the same weight vector length.",
        )

    total_samples = sum(sample_counts)
    if total_samples <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Total sample count must be greater than zero.",
        )

    global_weights = [0.0] * len(parsed_weights[0])
    for weights, count in zip(parsed_weights, sample_counts):
        contribution = count / total_samples
        for index, value in enumerate(weights):
            global_weights[index] += contribution * value

    snapshot = {
        "algorithm": "FedAvg",
        "round_number": round_number,
        "global_weights": [round(value, 8) for value in global_weights],
        "weights_preview": [round(value, 6) for value in global_weights[:8]],
        "client_labels": [submission.client_label for submission in submissions],
    }

    metric = models.RoundMetric(
        job_id=job.id,
        round_number=round_number,
        accuracy=weighted_average([s.accuracy for s in submissions], sample_counts),
        loss=weighted_average([s.loss for s in submissions], sample_counts),
        num_clients=len(submissions),
        total_samples=total_samples,
        global_weights_snapshot=json.dumps(snapshot),
    )
    db.add(metric)

    for submission in submissions:
        submission.status = "aggregated"

    if round_number >= job.round_count:
        job.status = "completed"
    else:
        job.current_round = round_number + 1
        job.status = "running"

    db.commit()
    db.refresh(job)
    return True, f"Round {round_number} aggregated with FedAvg using {len(submissions)} client update(s)."


def parse_weights(weights_json: str | None) -> list[float]:
    if not weights_json:
        return []
    try:
        values = json.loads(weights_json)
    except json.JSONDecodeError as e:
        import logging
        logging.getLogger(__name__).error("parse_weights: invalid JSON in weights_json: %s", e)
        return []
    if not isinstance(values, list):
        return []
    return [float(value) for value in values]


def parse_snapshot(snapshot_json: str | None) -> dict:
    if not snapshot_json:
        return {}
    try:
        snapshot = json.loads(snapshot_json)
    except json.JSONDecodeError as e:
        import logging
        logging.getLogger(__name__).error("parse_snapshot: invalid JSON in global_weights_snapshot: %s", e)
        return {}
    return snapshot if isinstance(snapshot, dict) else {}


def metric_to_detail(metric: models.RoundMetric) -> RoundMetricDetail:
    snapshot = parse_snapshot(metric.global_weights_snapshot)
    global_weights = snapshot.get("global_weights") or snapshot.get("weights_preview") or []
    return RoundMetricDetail(
        id=metric.id,
        job_id=metric.job_id,
        round_number=metric.round_number,
        accuracy=metric.accuracy,
        loss=metric.loss,
        num_clients=metric.num_clients,
        total_samples=metric.total_samples,
        global_weights=[float(value) for value in global_weights],
        global_weights_snapshot=snapshot or None,
        completed_at=metric.completed_at,
    )


def build_job_details(
    db: Session,
    job: models.JobConfiguration,
    creator_email: str | None,
    visible_to_clients: bool,
) -> JobDetailsOut:
    submission_rows = (
        db.query(models.ClientSubmission, models.User.email)
        .outerjoin(models.User, models.ClientSubmission.user_id == models.User.id)
        .filter(models.ClientSubmission.job_id == job.id)
        .order_by(
            models.ClientSubmission.round_number.asc(),
            models.ClientSubmission.created_at.asc(),
        )
        .all()
    )
    submissions = [
        ClientSubmissionDetail(
            id=submission.id,
            job_id=submission.job_id,
            user_id=submission.user_id,
            client_email=email,
            client_label=submission.client_label,
            round_number=submission.round_number,
            sample_count=submission.sample_count,
            accuracy=submission.accuracy,
            loss=submission.loss,
            weights=parse_weights(submission.weights_json),
            status=submission.status,
            created_at=submission.created_at,
        )
        for submission, email in submission_rows
    ]

    metric_rows = (
        db.query(models.RoundMetric)
        .filter(models.RoundMetric.job_id == job.id)
        .order_by(models.RoundMetric.round_number.asc())
        .all()
    )
    metrics = [metric_to_detail(metric) for metric in metric_rows]
    final_metric = metrics[-1] if metrics else None

    return JobDetailsOut(
        job=job_to_out(job, creator_email, get_assigned_user_ids(db, job.id)),
        submissions=submissions,
        metrics=metrics,
        final_metric=final_metric,
        final_weights=final_metric.global_weights if final_metric else [],
        visible_to_clients=visible_to_clients,
    )


@router.post("/", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role("platform_admin", "ml_engineer")
    ),
):
    """Create a new federated training job. Requires ml_engineer or platform_admin role."""
    job = models.JobConfiguration(
        job_name=payload.job_name,
        description=payload.description,
        round_count=payload.round_count,
        local_epochs=payload.local_epochs,
        expected_clients=payload.expected_clients,
        current_round=0,
        status="draft",
        created_by=current_user.id,
    )
    db.add(job)
    db.flush()  # get job.id without committing

    for user_id in payload.assigned_user_ids:
        db.add(models.JobAssignment(job_id=job.id, user_id=user_id))

    db.commit()
    db.refresh(job)
    assigned = get_assigned_user_ids(db, job.id)
    return job_to_out(job, current_user.email, assigned)


@router.get("/", response_model=List[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List jobs. Admins see all; ML engineers see their own; clients see assigned jobs."""
    query = (
        db.query(models.JobConfiguration, models.User.email)
        .outerjoin(models.User, models.JobConfiguration.created_by == models.User.id)
    )
    if current_user.role == "ml_engineer":
        query = query.filter(models.JobConfiguration.created_by == current_user.id)
    elif current_user.role == "client_operator":
        assigned_job_ids = db.query(models.JobAssignment.job_id).filter(
            models.JobAssignment.user_id == current_user.id
        ).subquery()
        query = query.filter(models.JobConfiguration.id.in_(assigned_job_ids))

    rows = query.order_by(models.JobConfiguration.created_at.desc()).all()
    return [
        job_to_out(job, creator_email, get_assigned_user_ids(db, job.id))
        for job, creator_email in rows
    ]


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Get a single job by ID."""
    job = db.query(models.JobConfiguration).filter(
        models.JobConfiguration.id == job_id
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)
    creator_email = None
    if job.created_by:
        creator = db.query(models.User).filter(models.User.id == job.created_by).first()
        creator_email = creator.email if creator else None
    return job_to_out(job, creator_email, get_assigned_user_ids(db, job.id))


@router.get("/{job_id}/details", response_model=JobDetailsOut)
def get_job_details(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Detailed per-job view with client-specific visibility logic."""
    job = db.query(models.JobConfiguration).filter(
        models.JobConfiguration.id == job_id
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)

    is_manager = current_user.role in {"platform_admin", "ml_engineer"}
    if not is_manager:
        require_published_for_client(job, current_user)
    
    # Check if this specific user has ever contributed to this job
    user_has_contributed = db.query(models.ClientSubmission).filter(
        models.ClientSubmission.job_id == job_id,
        models.ClientSubmission.user_id == current_user.id
    ).first() is not None

    creator_email = None
    if job.created_by:
        creator = db.query(models.User).filter(models.User.id == job.created_by).first()
        creator_email = creator.email if creator else None

    # Build the full details object
    details = build_job_details(db, job, creator_email, bool(job.results_published))

    # --- PRIVACY LOGIC ---
    if not is_manager:
        # 1. Only show them THEIR own submissions
        details.submissions = [
            s for s in details.submissions if s.user_id == current_user.id
        ]
        
        # 2. If they haven't contributed, HIDE the global metrics and weights
        if not user_has_contributed:
            details.metrics = []
            details.final_metric = None
            details.final_weights = []
            details.message = "You must submit a local training update to view global model insights."

    return details


@router.post("/{job_id}/start", response_model=JobStartResponse)
def start_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role("platform_admin", "ml_engineer")
    ),
):
    """Schedule a federated job for Gamma's orchestration worker."""
    job = db.query(models.JobConfiguration).filter(
        models.JobConfiguration.id == job_id
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)

    job.status = "running"
    if job.current_round < 1:
        job.current_round = 1
    db.commit()
    db.refresh(job)

    return JobStartResponse(
        job_id=job.id,
        status=job.status,
        task_id=None,
        message="Job is running. Client Operators can now submit local update payloads from the website.",
    )


@router.get("/{job_id}/metrics", response_model=List[RoundMetricOut])
def get_job_metrics(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Return per-round metrics written by Gamma's aggregation engine."""
    job = db.query(models.JobConfiguration).filter(
        models.JobConfiguration.id == job_id
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)
    require_published_for_client(job, current_user)

    if current_user.role == "client_operator":
        user_has_contributed = db.query(models.ClientSubmission).filter(
            models.ClientSubmission.job_id == job_id,
            models.ClientSubmission.user_id == current_user.id,
        ).first() is not None
        if not user_has_contributed:
            return []

    return db.query(models.RoundMetric).filter(
        models.RoundMetric.job_id == job_id
    ).order_by(models.RoundMetric.round_number.asc()).all()


@router.post("/{job_id}/publish", response_model=PublishResponse)
def publish_job_results(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role("platform_admin", "ml_engineer")
    ),
):
    """Publish final results so Client Operators can view the details page."""
    job = db.query(models.JobConfiguration).filter(
        models.JobConfiguration.id == job_id
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only completed jobs can be published.",
        )

    metrics_count = db.query(models.RoundMetric).filter(
        models.RoundMetric.job_id == job_id
    ).count()
    if metrics_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No aggregated round metrics are available to publish.",
        )

    job.results_published = 1
    job.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)

    creator_email = None
    if job.created_by:
        creator = db.query(models.User).filter(models.User.id == job.created_by).first()
        creator_email = creator.email if creator else None

    return PublishResponse(
        job=job_to_out(job, creator_email),
        message="Final results published to Client Operators.",
    )


@router.get("/{job_id}/submissions", response_model=List[ClientSubmissionOut])
def get_job_submissions(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List client submissions for a job."""
    job = db.query(models.JobConfiguration).filter(
        models.JobConfiguration.id == job_id
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)

    query = db.query(models.ClientSubmission).filter(models.ClientSubmission.job_id == job_id)
    if current_user.role == "client_operator":
        query = query.filter(models.ClientSubmission.user_id == current_user.id)

    return query.order_by(
        models.ClientSubmission.round_number.asc(),
        models.ClientSubmission.created_at.desc(),
    ).all()


@router.post("/{job_id}/submissions", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def submit_client_update(
    request: Request,
    job_id: int,
    payload: ClientSubmissionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("client_operator")),
):
    """Client Operator: submit a local model update for the active round."""
    job = db.query(models.JobConfiguration).filter(
        models.JobConfiguration.id == job_id
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status not in {"running", "scheduled"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This job is not accepting client updates. Ask an ML Engineer to start it.",
        )

    # Verify this client is assigned to the job
    assigned = db.query(models.JobAssignment).filter(
        models.JobAssignment.job_id == job.id,
        models.JobAssignment.user_id == current_user.id,
    ).first()
    if not assigned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this job. Ask an ML Engineer to assign you.",
        )

    if payload.sample_count <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sample count must be greater than zero.",
        )

    if not payload.weights:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one model weight is required.",
        )

    round_number = job.current_round or 1
    existing = (
        db.query(models.ClientSubmission)
        .filter(
            models.ClientSubmission.job_id == job.id,
            models.ClientSubmission.user_id == current_user.id,
            models.ClientSubmission.round_number == round_number,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You already submitted an update for round {round_number}.",
        )

    submission = models.ClientSubmission(
        job_id=job.id,
        user_id=current_user.id,
        client_label=payload.client_label or current_user.email,
        round_number=round_number,
        sample_count=payload.sample_count,
        accuracy=payload.accuracy,
        loss=payload.loss,
        weights_json=json.dumps([float(value) for value in payload.weights]),
        status="accepted",
    )
    db.add(submission)

    if job.status == "scheduled":
        job.status = "running"

    db.commit()
    db.refresh(submission)
    db.refresh(job)

    aggregation_ran, message = aggregate_round_if_ready(db, job)

    creator_email = None
    if job.created_by:
        creator = db.query(models.User).filter(models.User.id == job.created_by).first()
        creator_email = creator.email if creator else None

    db.refresh(submission)
    return SubmissionResponse(
        job=job_to_out(job, creator_email),
        submission=submission,
        aggregation_ran=aggregation_ran,
        message=message,
    )


@router.patch("/{job_id}/status", response_model=JobOut)
def update_job_status(
    job_id: int,
    payload: JobStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role("platform_admin", "ml_engineer")
    ),
):
    """Update a job's status (draft → scheduled → running → completed)."""
    new_status = payload.status
    allowed = {"draft", "scheduled", "running", "completed", "failed"}
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Choose from: {allowed}",
        )
    job = db.query(models.JobConfiguration).filter(
        models.JobConfiguration.id == job_id
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)
    job.status = new_status
    db.commit()
    db.refresh(job)
    creator_email = None
    if job.created_by:
        creator = db.query(models.User).filter(models.User.id == job.created_by).first()
        creator_email = creator.email if creator else None
    return job_to_out(job, creator_email)


@router.post("/{job_id}/assign", status_code=status.HTTP_200_OK)
def assign_clients(
    job_id: int,
    payload: AssignClientsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("platform_admin", "ml_engineer")),
):
    """Assign client operators to a job. ML engineers can only assign to their own jobs."""
    job = db.query(models.JobConfiguration).filter(models.JobConfiguration.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)

    # Verify all user_ids exist and are client_operators
    for user_id in payload.user_ids:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=400, detail=f"User {user_id} not found.")
        if user.role != "client_operator":
            raise HTTPException(status_code=400, detail=f"User {user_id} is not a client_operator.")

    # Replace existing assignments
    db.query(models.JobAssignment).filter(models.JobAssignment.job_id == job_id).delete()
    for user_id in payload.user_ids:
        db.add(models.JobAssignment(job_id=job_id, user_id=user_id))
    db.commit()

    return {"job_id": job_id, "assigned_user_ids": payload.user_ids}


@router.get("/{job_id}/assigned-clients")
def list_assigned_clients(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("platform_admin", "ml_engineer")),
):
    """List all client operators assigned to a job."""
    job = db.query(models.JobConfiguration).filter(models.JobConfiguration.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)

    rows = (
        db.query(models.User)
        .join(models.JobAssignment, models.JobAssignment.user_id == models.User.id)
        .filter(models.JobAssignment.job_id == job_id)
        .all()
    )
    return [{"id": u.id, "email": u.email, "status": u.status} for u in rows]


def _snapshot_to_pt_response(snapshot: dict, job_id: int, job_name: str, round_number: int,
                              accuracy=None, loss=None) -> StreamingResponse:
    """Convert a weights snapshot dict to a streaming .pt file response."""
    if not TORCH_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PyTorch is not installed on the server. Use ?format=json instead.",
        )
    state_dict = {}
    for layer_name, info in snapshot.items():
        if layer_name in ("_meta", "algorithm", "round_number", "weight_count",
                          "weights_preview", "client_labels") or not isinstance(info, dict):
            continue
        if "data" not in info or "shape" not in info:
            continue
        state_dict[layer_name] = torch.tensor(info["data"], dtype=torch.float32).reshape(info["shape"])

    if not state_dict:
        flat = snapshot.get("global_weights") or snapshot.get("weights_preview") or []
        if flat:
            state_dict["global_weights"] = torch.tensor(flat, dtype=torch.float32)

    if not state_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No layer weights found in the stored snapshot. This round may predate full-weight storage.",
        )

    meta = snapshot.get("_meta", {})
    input_columns = meta.get("input_columns") or []
    label_column = meta.get("label_column") or "label"

    checkpoint = {
        "state_dict": state_dict,
        "job_id": job_id,
        "job_name": job_name,
        "round_number": round_number,
        "accuracy": accuracy,
        "loss": loss,
        "input_columns": input_columns,
        "label_column": label_column,
    }
    buf = io.BytesIO()
    torch.save(checkpoint, buf)
    buf.seek(0)
    filename = f"job_{job_id}_round_{round_number}_model.pt"
    return StreamingResponse(
        buf,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/model")
def download_job_model(
    job_id: int,
    format: str = Query("json", pattern="^(json|pt)$"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Download the latest aggregated global model. Use ?format=pt for PyTorch checkpoint."""
    job = db.query(models.JobConfiguration).filter(models.JobConfiguration.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)
    require_published_for_client(job, current_user)

    latest = (
        db.query(models.RoundMetric)
        .filter(
            models.RoundMetric.job_id == job_id,
            models.RoundMetric.global_weights_snapshot.isnot(None),
        )
        .order_by(models.RoundMetric.round_number.desc())
        .first()
    )
    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No aggregated model is available yet. Complete at least one round first.",
        )

    snapshot = parse_snapshot(latest.global_weights_snapshot)
    if format == "pt":
        return _snapshot_to_pt_response(snapshot, job_id, job.job_name, latest.round_number,
                                        latest.accuracy, latest.loss)

    meta = snapshot.get("_meta", {})
    return JSONResponse(
        content={
            "job_id": job_id,
            "job_name": job.job_name,
            "round_number": latest.round_number,
            "input_columns": meta.get("input_columns") or [],
            "label_column": meta.get("label_column") or "label",
            "weights": snapshot,
        },
        headers={"Content-Disposition": f'attachment; filename="job_{job_id}_round_{latest.round_number}_model.json"'},
    )


@router.get("/{job_id}/model/{round_number}")
def download_job_model_by_round(
    job_id: int,
    round_number: int,
    format: str = Query("json", pattern="^(json|pt)$"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Download aggregated global model for a specific round. Use ?format=pt for PyTorch checkpoint."""
    job = db.query(models.JobConfiguration).filter(models.JobConfiguration.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)
    require_published_for_client(job, current_user)

    metric = (
        db.query(models.RoundMetric)
        .filter(
            models.RoundMetric.job_id == job_id,
            models.RoundMetric.round_number == round_number,
            models.RoundMetric.global_weights_snapshot.isnot(None),
        )
        .first()
    )
    if not metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No aggregated model found for round {round_number}.",
        )

    snapshot = parse_snapshot(metric.global_weights_snapshot)
    if format == "pt":
        return _snapshot_to_pt_response(snapshot, job_id, job.job_name, round_number,
                                        metric.accuracy, metric.loss)

    meta = snapshot.get("_meta", {})
    return JSONResponse(
        content={
            "job_id": job_id,
            "job_name": job.job_name,
            "round_number": round_number,
            "accuracy": metric.accuracy,
            "loss": metric.loss,
            "total_samples": metric.total_samples,
            "num_clients": metric.num_clients,
            "input_columns": meta.get("input_columns") or [],
            "label_column": meta.get("label_column") or "label",
            "weights": snapshot,
        },
        headers={"Content-Disposition": f'attachment; filename="job_{job_id}_round_{round_number}_model.json"'},
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role("platform_admin", "ml_engineer")
    ),
):
    """Delete a training job and its associated round metrics."""
    job = db.query(models.JobConfiguration).filter(
        models.JobConfiguration.id == job_id
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    check_job_access(db, job, current_user)

    db.query(models.JobAssignment).filter(models.JobAssignment.job_id == job_id).delete()
    db.query(models.RoundMetric).filter(models.RoundMetric.job_id == job_id).delete()
    db.query(models.ClientSubmission).filter(models.ClientSubmission.job_id == job_id).delete()
    db.delete(job)
    db.commit()
    return None
