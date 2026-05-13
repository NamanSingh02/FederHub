from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.schemas import UserRegister, UserLogin, TokenResponse, UserOut, UserStatusUpdate
from app.auth import (
    get_db,
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_role,
)
from app.limiter import limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
def register(request: Request, payload: UserRegister, db: Session = Depends(get_db)):
    """Register a new user. Roles: platform_admin | ml_engineer | client_operator."""
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    allowed_roles = {"platform_admin", "ml_engineer", "client_operator"}
    if payload.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Choose from: {allowed_roles}",
        )

    user = models.User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, payload: UserLogin, db: Session = Depends(get_db)):
    """Authenticate and receive a JWT access token."""
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status}. Access is allowed only after activation.",
        )

    token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return TokenResponse(
        access_token=token,
        role=user.role,
        user_id=user.id,
        email=user.email,
        status=user.status,
    )


@router.get("/me", response_model=UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("platform_admin")),
):
    """Platform Admin: list all users for account governance."""
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


@router.get("/client-operators", response_model=list[UserOut])
def list_client_operators(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("platform_admin", "ml_engineer")),
):
    """ML Engineer / Admin: list all active client_operator accounts for job assignment."""
    return (
        db.query(models.User)
        .filter(models.User.role == "client_operator")
        .order_by(models.User.email.asc())
        .all()
    )


@router.patch("/users/{user_id}/status", response_model=UserOut)
def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("platform_admin")),
):
    """Platform Admin: activate, deactivate, reject, or mark users pending."""
    allowed = {"pending", "active", "rejected", "deactivated"}
    if payload.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Choose from: {allowed}",
        )

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.status = payload.status
    db.commit()
    db.refresh(user)
    return user
