import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.auth_schemas import BootstrapAdminCreate
from app.core.config import settings
from app.core.enums import ProjectRole, UserStatus
from app.core.time import utc_now
from app.database import get_db


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
PASSWORD_KEY_LENGTH = 32
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=PASSWORD_KEY_LENGTH,
    )
    return "$".join(
        [
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _base64url_encode(salt),
            _base64url_encode(derived),
        ]
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", maxsplit=5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_base64url_decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=PASSWORD_KEY_LENGTH,
        )
        return hmac.compare_digest(actual, _base64url_decode(expected))
    except (ValueError, TypeError):
        return False


def create_access_token(user: models.User) -> str:
    now = int(time.time())
    expires_in = settings.access_token_expire_minutes * 60
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user.id),
        "iat": now,
        "exp": now + expires_in,
        "ver": user.token_version,
    }
    encoded_header = _base64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    unsigned = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        unsigned,
        hashlib.sha256,
    ).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}"


def _decode_access_token(token: str) -> dict:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        unsigned = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = hmac.new(
            settings.jwt_secret.encode("utf-8"),
            unsigned,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(
            expected_signature,
            _base64url_decode(encoded_signature),
        ):
            raise ValueError("Invalid token signature")
        header = json.loads(_base64url_decode(encoded_header))
        payload = json.loads(_base64url_decode(encoded_payload))
        if header != {"alg": "HS256", "typ": "JWT"}:
            raise ValueError("Unsupported token header")
        if int(payload["exp"]) <= int(time.time()):
            raise ValueError("Token has expired")
        return payload
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        binascii.Error,
        UnicodeDecodeError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или просроченный токен доступа",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    payload = _decode_access_token(token)
    try:
        user_id = int(payload["sub"])
        token_version = int(payload["ver"])
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректные данные токена доступа",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if (
        user is None
        or user.status != UserStatus.ACTIVE.value
        or user.token_version != token_version
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь неактивен или токен был отозван",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_system_admin(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права системного администратора",
        )
    return current_user


def ensure_actor(current_user: models.User, actor_user_id: int | None) -> int:
    effective_actor_id = actor_user_id or current_user.id
    if not current_user.is_system_admin and effective_actor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь не может выполнять действие от имени другого пользователя",
        )
    return effective_actor_id


def ensure_project_roles(
    db: Session,
    current_user: models.User,
    project_id: int,
    allowed_roles: set[ProjectRole] | None = None,
) -> set[ProjectRole]:
    if current_user.is_system_admin:
        return set(ProjectRole)
    memberships = (
        db.query(models.ProjectMembership.role)
        .filter(
            models.ProjectMembership.project_id == project_id,
            models.ProjectMembership.user_id == current_user.id,
        )
        .all()
    )
    roles = {ProjectRole(row.role) for row in memberships}
    if not roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"У пользователя нет доступа к проекту {project_id}",
        )
    if allowed_roles is not None and roles.isdisjoint(allowed_roles):
        allowed = ", ".join(sorted(role.value for role in allowed_roles))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Требуется одна из ролей проекта: {allowed}",
        )
    return roles


def accessible_project_ids(db: Session, current_user: models.User) -> set[int] | None:
    if current_user.is_system_admin:
        return None
    return {
        row.project_id
        for row in db.query(models.ProjectMembership.project_id)
        .filter(models.ProjectMembership.user_id == current_user.id)
        .all()
    }


def project_ids_for_roles(
    db: Session,
    current_user: models.User,
    allowed_roles: set[ProjectRole],
) -> set[int] | None:
    """Return projects where the user has at least one of the requested roles.

    ``None`` means unrestricted system-administrator access, matching
    ``accessible_project_ids``.
    """

    if current_user.is_system_admin:
        return None
    allowed_values = {role.value for role in allowed_roles}
    return {
        row.project_id
        for row in db.query(models.ProjectMembership.project_id)
        .filter(
            models.ProjectMembership.user_id == current_user.id,
            models.ProjectMembership.role.in_(allowed_values),
        )
        .all()
    }


def authenticate_user(db: Session, email: str, password: str) -> models.User | None:
    user = db.query(models.User).filter(models.User.email == email.lower()).first()
    if (
        user is None
        or user.status != UserStatus.ACTIVE.value
        or not verify_password(password, user.password_hash)
    ):
        return None
    user.last_login_at = utc_now()
    db.commit()
    db.refresh(user)
    return user


def bootstrap_admin(db: Session, data: BootstrapAdminCreate) -> models.User:
    if db.query(models.User.id).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Первичная настройка доступна только пока в системе нет пользователей",
        )
    user = models.User(
        email=data.email,
        full_name=data.full_name,
        status=UserStatus.ACTIVE.value,
        is_system_admin=True,
        password_hash=hash_password(data.password),
        token_version=0,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Первичная настройка администратора уже выполнена",
        ) from exc
    db.refresh(user)
    return user


def token_response(user: models.User) -> dict:
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "expires_in": int(timedelta(minutes=settings.access_token_expire_minutes).total_seconds()),
    }
