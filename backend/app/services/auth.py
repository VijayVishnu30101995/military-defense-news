from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.jwt import create_access_token
from app.core.security import verify_password
from app.models.user import User
from app.schemas.auth import TokenResponse


def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> User | None:
    statement = select(User).where(User.email == email)
    user = db.scalar(statement)

    if user is None:
        return None

    if not user.is_active:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


def login_user(
    db: Session,
    email: str,
    password: str,
) -> TokenResponse | None:
    user = authenticate_user(db, email, password)

    if user is None:
        return None

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    access_token = create_access_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
    )
