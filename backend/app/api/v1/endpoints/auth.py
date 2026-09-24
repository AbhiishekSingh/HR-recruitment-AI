from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.schemas.user import UserCreate, UserOut
from app.schemas.auth import Token

router = APIRouter()


@router.post("/register", response_model=UserOut)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    # Lowercased before the lookup and the insert -- without this,
    # "Foo@Bar.com" and "foo@bar.com" register as two different accounts,
    # and neither can log in with the other's casing. Matches the same
    # normalization candidates.py already applies to Candidate.email.
    email = payload.email.strip().lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    user = User(
        name=payload.name,
        email=email,
        hashed_password=hash_password(payload.password),
        role="recruiter",  # admins are promoted manually, not self-assigned at signup
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """OAuth2PasswordRequestForm expects 'username' (we use it as email) + 'password',
    sent as form data — this is what makes Swagger UI's Authorize button work out of the box."""
    result = await db.execute(select(User).where(User.email == form_data.username.strip().lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password")

    token = create_access_token(subject=str(user.id), role=user.role)
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user
