"""Auth API — login and token generation."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models.models import User
from app.core.security import verify_password, create_access_token, hash_password
from pydantic import BaseModel

router = APIRouter()


class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    username: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "nurse"
    full_name: str = ""


@router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"sub": user.username, "role": user.role.value})
    return Token(access_token=token, token_type="bearer", role=user.role.value, username=user.username)


from typing import Optional
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import get_current_user, require_role
from app.models.models import UserRole

security_bearer = HTTPBearer(auto_error=False)


@router.post("/register", status_code=201)
async def register(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
):
    """
    Public registration endpoint.
    Only patient accounts can be registered publicly.
    Registering nurse/admin roles requires an authenticated admin.
    """
    requested_role = (body.role or "patient").lower()
    if requested_role in ("nurse", "admin"):
        # Verify admin credentials
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can register nurse or admin staff accounts.",
            )
        try:
            current_user = await get_current_user(credentials.credentials)
            if current_user.get("role") != "admin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can register nurse or admin staff accounts.",
                )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can register nurse or admin staff accounts.",
            )
        assigned_role = UserRole.ADMIN if requested_role == "admin" else UserRole.NURSE
    else:
        assigned_role = UserRole.PATIENT

    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
        role=assigned_role,
        full_name=body.full_name,
    )
    db.add(user)
    await db.commit()
    return {"message": "User created", "username": body.username, "role": assigned_role.value}
