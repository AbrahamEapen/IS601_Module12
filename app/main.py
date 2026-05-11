from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import List
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_active_user
from app.models.calculation import Calculation
from app.models.user import User
from app.schemas.calculation import CalculationBase, CalculationResponse, CalculationUpdate
from app.schemas.token import TokenResponse
from app.schemas.user import UserCreate, UserResponse, UserLogin
from app.database import Base, get_db, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")
    yield


app = FastAPI(
    title="Calculations API",
    description="API for managing users and calculations",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"])
def read_health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Shared business-logic helpers (avoids duplicating code between /users and /auth)
# ---------------------------------------------------------------------------
def _register_user(user_create: UserCreate, db: Session) -> User:
    user_data = user_create.model_dump(exclude={"confirm_password"})
    try:
        user = User.register(db, user_data)
        db.commit()
        db.refresh(user)
        return user
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _login_user(username: str, password: str, db: Session) -> TokenResponse:
    auth_result = User.authenticate(db, username, password)
    if auth_result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    db.commit()
    user = auth_result["user"]
    expires_at = auth_result.get("expires_at")
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    elif expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return TokenResponse(
        access_token=auth_result["access_token"],
        refresh_token=auth_result["refresh_token"],
        token_type="bearer",
        expires_at=expires_at,
        user_id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
    )


# ---------------------------------------------------------------------------
# /users  (canonical paths required by the assignment)
# ---------------------------------------------------------------------------
@app.post(
    "/users/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
    summary="Register a new user",
)
def users_register(user_create: UserCreate, db: Session = Depends(get_db)):
    return _register_user(user_create, db)


@app.post(
    "/users/login",
    response_model=TokenResponse,
    tags=["users"],
    summary="Login and receive JWT tokens",
)
def users_login(user_login: UserLogin, db: Session = Depends(get_db)):
    return _login_user(user_login.username, user_login.password, db)


# ---------------------------------------------------------------------------
# /auth  (kept for backward compatibility + Swagger Authorize button)
# ---------------------------------------------------------------------------
@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
    summary="Register (alias)",
)
def auth_register(user_create: UserCreate, db: Session = Depends(get_db)):
    return _register_user(user_create, db)


@app.post(
    "/auth/login",
    response_model=TokenResponse,
    tags=["auth"],
    summary="Login (alias)",
)
def auth_login(user_login: UserLogin, db: Session = Depends(get_db)):
    return _login_user(user_login.username, user_login.password, db)


@app.post(
    "/auth/token",
    tags=["auth"],
    summary="Login via form (Swagger UI Authorize button)",
)
def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    auth_result = User.authenticate(db, form_data.username, form_data.password)
    if auth_result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": auth_result["access_token"], "token_type": "bearer"}


# ---------------------------------------------------------------------------
# Calculations – BREAD
# ---------------------------------------------------------------------------
@app.post(
    "/calculations",
    response_model=CalculationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["calculations"],
    summary="Add – create and persist a calculation",
)
def create_calculation(
    calculation_data: CalculationBase,
    current_user: UserResponse = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        new_calc = Calculation.create(
            calculation_type=calculation_data.type,
            user_id=current_user.id,
            inputs=calculation_data.inputs,
        )
        new_calc.result = new_calc.get_result()
        db.add(new_calc)
        db.commit()
        db.refresh(new_calc)
        return new_calc
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get(
    "/calculations",
    response_model=List[CalculationResponse],
    tags=["calculations"],
    summary="Browse – list all calculations for the current user",
)
def list_calculations(
    current_user: UserResponse = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return db.query(Calculation).filter(Calculation.user_id == current_user.id).all()


@app.get(
    "/calculations/{calc_id}",
    response_model=CalculationResponse,
    tags=["calculations"],
    summary="Read – retrieve a specific calculation by ID",
)
def get_calculation(
    calc_id: str,
    current_user: UserResponse = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        calc_uuid = UUID(calc_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid calculation id format.",
        )
    calculation = db.query(Calculation).filter(
        Calculation.id == calc_uuid,
        Calculation.user_id == current_user.id,
    ).first()
    if not calculation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calculation not found.",
        )
    return calculation


@app.put(
    "/calculations/{calc_id}",
    response_model=CalculationResponse,
    tags=["calculations"],
    summary="Edit – update inputs and recompute result",
)
def update_calculation(
    calc_id: str,
    calculation_update: CalculationUpdate,
    current_user: UserResponse = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        calc_uuid = UUID(calc_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid calculation id format.",
        )
    calculation = db.query(Calculation).filter(
        Calculation.id == calc_uuid,
        Calculation.user_id == current_user.id,
    ).first()
    if not calculation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calculation not found.",
        )
    if calculation_update.inputs is not None:
        calculation.inputs = calculation_update.inputs
        calculation.result = calculation.get_result()
    calculation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(calculation)
    return calculation


@app.delete(
    "/calculations/{calc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["calculations"],
    summary="Delete – remove a calculation permanently",
)
def delete_calculation(
    calc_id: str,
    current_user: UserResponse = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        calc_uuid = UUID(calc_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid calculation id format.",
        )
    calculation = db.query(Calculation).filter(
        Calculation.id == calc_uuid,
        Calculation.user_id == current_user.id,
    ).first()
    if not calculation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calculation not found.",
        )
    db.delete(calculation)
    db.commit()
    return None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, log_level="info")
