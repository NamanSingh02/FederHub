import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool  # <-- THE FIX: Import StaticPool
from passlib.context import CryptContext

# Import your FastAPI app and database dependencies
from app.main import app
from app.auth import get_db
from app import models

# --- 1. TEST DATABASE SETUP ---
# Use a lightning-fast, temporary in-memory database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# THE FIX: Add poolclass=StaticPool so the memory DB doesn't erase itself!
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Force the FastAPI app to use our memory database instead of the real one
app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

# Set up our own password hasher just for the tests
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- 2. FIXTURES (Runs before tests) ---
@pytest.fixture(autouse=True)
def setup_database():
    """Creates fresh tables before each test and drops them after."""
    models.Base.metadata.create_all(bind=engine)
    
    # Inject a test user into the clean database
    db = TestingSessionLocal()
    test_engineer = models.User(
        email="engineer@test.com",
        hashed_password=pwd_context.hash("password123"),
        role="ml_engineer",
        status="active"
    )
    db.add(test_engineer)
    db.commit()
    db.close()
    
    yield  # Run the tests
    models.Base.metadata.drop_all(bind=engine)

@pytest.fixture
def auth_token():
    """Helper to log in and get a token for protected routes."""
    response = client.post(
        "/auth/login",
        json={"email": "engineer@test.com", "password": "password123"}
    )
    return response.json()["access_token"]


# --- 3. THE TESTS ---

def test_login_success():
    """Test that a valid user can log in and receive a JWT."""
    response = client.post(
        "/auth/login",
        json={"email": "engineer@test.com", "password": "password123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_failure():
    """Test that bad passwords are rejected."""
    response = client.post(
        "/auth/login",
        json={"email": "engineer@test.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401

def test_create_job_unauthorized():
    """Test that an anonymous user CANNOT create a job."""
    payload = {
        "job_name": "Unauthorized Job",
        "expected_clients": 2,
        "round_count": 3,
    }
    response = client.post("/jobs/", json=payload)
    # Should block access because there is no JWT header
    assert response.status_code == 401

def test_create_job_authorized(auth_token):
    """Test that an ML Engineer CAN create a job."""
    payload = {
        "job_name": "Automated Test Job",
        "description": "Created via pytest",
        "expected_clients": 2,
        "round_count": 3,
        "local_epochs": 2
    }
    response = client.post(
        "/jobs/", 
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["job_name"] == "Automated Test Job"
    assert data["status"] == "draft"
    assert data["current_round"] == 0

# --- 4. INTEGRATION TESTS (Privacy & Orchestration) ---

@pytest.fixture
def client_token():
    """Injects a hospital client into the database and returns their JWT."""
    db = TestingSessionLocal()
    test_client = models.User(
        email="hospital4@test.com",
        hashed_password=pwd_context.hash("password123"),
        role="client_operator",
        status="active"
    )
    db.add(test_client)
    db.commit()
    db.close()

    response = client.post(
        "/auth/login",
        json={"email": "hospital4@test.com", "password": "password123"}
    )
    data = response.json()
    # Return both the token and the user_id so tests can use either
    return {"token": data["access_token"], "user_id": data["user_id"]}


def test_privacy_lock_hides_global_model(auth_token, client_token):
    """
    INTEGRATION TEST:
    1. ML Engineer creates a job and assigns the client operator.
    2. A fresh Client Operator (assigned but not yet contributed) tries to view the details.
    3. The API must return 200 but scrub global weights and metrics.
    """

    # 1. ML Engineer creates the job
    payload = {
        "job_name": "Bone Fracture Phase 2",
        "expected_clients": 2,
        "round_count": 3,
    }
    create_res = client.post("/jobs/", json=payload, headers={"Authorization": f"Bearer {auth_token}"})
    assert create_res.status_code == 201
    job_id = create_res.json()["id"]

    # 2. Assign the client operator to the job so they can access it
    assign_res = client.post(
        f"/jobs/{job_id}/assign",
        json={"user_ids": [client_token["user_id"]]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert assign_res.status_code == 200

    # 3. Client Operator fetches job details (assigned but not yet contributed)
    details_res = client.get(
        f"/jobs/{job_id}/details",
        headers={"Authorization": f"Bearer {client_token['token']}"},
    )
    assert details_res.status_code == 200
    details = details_res.json()

    # 4. Assert the Zero-Knowledge Privacy Locks are triggered
    assert details["final_weights"] == []  # Weights must be scrubbed
    assert details["metrics"] == []        # Analytics must be scrubbed
    assert "You must submit a local training update" in details.get("message", "")