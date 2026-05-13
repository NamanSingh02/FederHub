from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Optional, List
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    role: Optional[str] = "ml_engineer"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: int
    email: str
    status: str

class UserOut(BaseModel):
    id: int
    email: str
    role: str
    status: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Jobs ──────────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    job_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    round_count: int = Field(5, ge=1, le=500)
    local_epochs: int = Field(3, ge=1, le=200)
    expected_clients: int = Field(1, ge=1, le=1000)
    assigned_user_ids: List[int] = []

class JobOut(BaseModel):
    id: int
    job_name: str
    description: Optional[str] = None
    round_count: int
    local_epochs: int
    expected_clients: int
    current_round: int
    status: str
    results_published: bool = False
    published_at: Optional[datetime] = None
    created_by: Optional[int]
    creator_email: Optional[str] = None
    created_at: datetime
    assigned_user_ids: List[int] = []

    model_config = ConfigDict(from_attributes=True)

class AssignClientsRequest(BaseModel):
    user_ids: List[int]

class JobStartResponse(BaseModel):
    job_id: int
    status: str
    task_id: Optional[str] = None
    message: str

class RoundMetricOut(BaseModel):
    id: int
    job_id: int
    round_number: int
    accuracy: Optional[float] = None
    loss: Optional[float] = None
    num_clients: Optional[int] = None
    total_samples: Optional[int] = None
    global_weights_snapshot: Optional[str] = None
    completed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserStatusUpdate(BaseModel):
    status: str

class JobStatusUpdate(BaseModel):
    status: str


class ClientSubmissionCreate(BaseModel):
    client_label: Optional[str] = Field(None, max_length=200)
    sample_count: int = Field(..., ge=1)
    accuracy: Optional[float] = Field(None, ge=0.0, le=1.0)
    loss: Optional[float] = Field(None, ge=0.0)
    weights: List[float] = Field(..., min_length=1, max_length=50000)


class ClientSubmissionOut(BaseModel):
    id: int
    job_id: int
    user_id: int
    client_label: str
    round_number: int
    sample_count: int
    accuracy: Optional[float] = None
    loss: Optional[float] = None
    weights_json: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubmissionResponse(BaseModel):
    job: JobOut
    submission: ClientSubmissionOut
    aggregation_ran: bool
    message: str


class ClientSubmissionDetail(BaseModel):
    id: int
    job_id: int
    user_id: int
    client_email: Optional[str] = None
    client_label: str
    round_number: int
    sample_count: int
    accuracy: Optional[float] = None
    loss: Optional[float] = None
    weights: List[float]
    status: str
    created_at: datetime


class RoundMetricDetail(BaseModel):
    id: int
    job_id: int
    round_number: int
    accuracy: Optional[float] = None
    loss: Optional[float] = None
    num_clients: Optional[int] = None
    total_samples: Optional[int] = None
    global_weights: List[float] = []
    global_weights_snapshot: Optional[dict] = None
    completed_at: datetime


class JobDetailsOut(BaseModel):
    job: JobOut
    submissions: List[ClientSubmissionDetail]
    metrics: List[RoundMetricDetail]
    final_metric: Optional[RoundMetricDetail] = None
    final_weights: List[float] = []
    visible_to_clients: bool
    message: Optional[str] = None


class PublishResponse(BaseModel):
    job: JobOut
    message: str