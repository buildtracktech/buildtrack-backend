from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth_schemas import BootstrapAdminCreate, PasswordChange, TokenResponse
from app.database import get_db
from app.services import auth_service
from app.user_schemas import UserResponse


router = APIRouter(prefix="/auth", tags=["Авторизация"])


@router.post(
    "/bootstrap",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать первого администратора",
)
def bootstrap_administrator(
    data: BootstrapAdminCreate,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = auth_service.bootstrap_admin(db, data)
    return auth_service.token_response(user)


@router.post("/login", response_model=TokenResponse, summary="Войти в систему")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = auth_service.authenticate_user(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверная электронная почта или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_service.token_response(user)


@router.get("/me", response_model=UserResponse, summary="Получить текущего пользователя")
def get_me(
    current_user=Depends(auth_service.get_current_user),
) -> UserResponse:
    return current_user


@router.put(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Изменить свой пароль",
)
def change_password(
    data: PasswordChange,
    current_user=Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not auth_service.verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Текущий пароль указан неверно",
        )
    current_user.password_hash = auth_service.hash_password(data.new_password)
    current_user.token_version += 1
    db.commit()
