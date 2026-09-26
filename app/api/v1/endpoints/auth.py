from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select

from app.api.deps import CurrentUser, ErrorBody, SessionDep, error_responses
from app.core.audit import audit
from app.core.config import settings
from app.core.exceptions import APIError
from app.core.rate_limit import client_ip, ip_key, limiter
from app.core.security import hash_password
from app.models.user import User
from app.schemas.auth import RefreshRequest, TokenPair
from app.schemas.user import UserRead, UserRegister
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_TAKEN = APIError(status.HTTP_409_CONFLICT, "Email already registered", code="email_taken")


async def _require_form(request: Request) -> None:
    """El login es el flujo "password" de OAuth2: exige un formulario. Sin esta
    comprobación, un JSON produce un 422 confuso ("username: Field required")."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {"application/x-www-form-urlencoded", "multipart/form-data"}:
        raise APIError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Login expects application/x-www-form-urlencoded with the fields "
            "'username' (your email) and 'password'",
            code="login_expects_form",
        )


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(409, 415, 429),
)
@limiter.limit(settings.RATE_LIMIT_REGISTER, key_func=ip_key)
async def register(
    request: Request, response: Response, payload: UserRegister, session: SessionDep
) -> User:
    """Crea una cuenta. La política de contraseñas se valida en el esquema (422),
    antes del límite de registro: un intento con contraseña débil no consume cupo.

    Un email ya registrado responde 409 `email_taken` (riesgo de enumeración
    aceptado y documentado: ver README, sección Seguridad)."""
    if not settings.ALLOW_REGISTRATION:
        raise APIError(
            status.HTTP_403_FORBIDDEN, "Registration is disabled", code="registration_disabled"
        )
    exists = (await session.exec(select(User.id).where(User.email == payload.email))).first()
    await session.commit()  # libera la conexión mientras se calcula Argon2
    if exists:
        raise EMAIL_TAKEN
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=await hash_password(payload.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    audit("auth.register", user_id=user.id, client_ip=client_ip(request))
    return user


@router.post(
    "/login",
    response_model=TokenPair,
    dependencies=[Depends(_require_form)],
    responses=error_responses(401, 415, 429),
)
@limiter.limit(settings.RATE_LIMIT_LOGIN, key_func=ip_key)
async def login(
    request: Request,
    response: Response,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> TokenPair:
    """Login OAuth2 (form `username` + `password`). `scope` opcional para pedir
    un token más restringido, p. ej. `scope=read`."""
    ip = client_ip(request)
    user = await auth_service.authenticate(session, form.username, form.password, client_ip=ip)
    scopes = auth_service.resolve_scopes(user.role, form.scopes)
    return await auth_service.start_session(
        session, user, scopes, request.headers.get("user-agent"), client_ip=ip
    )


@router.post(
    "/refresh",
    response_model=TokenPair,
    responses={
        **error_responses(401, 415, 429),
        409: {
            "model": ErrorBody,
            "description": "`refresh_token_rotated`: otra petición del mismo cliente acaba "
            "de rotarlo. Reintenta con el refresh más reciente o, si no lo tienes, llama a "
            "/auth/logout con este.",
        },
    },
)
@limiter.limit(settings.RATE_LIMIT_REFRESH, key_func=ip_key)
async def refresh(
    request: Request, response: Response, payload: RefreshRequest, session: SessionDep
) -> TokenPair:
    """Rota el refresh token: el antiguo deja de valer.

    - Reutilizar uno ya rotado revoca toda la sesión (indica robo de token).
    - Excepción: si otra petición del MISMO cliente lo acaba de rotar (dos pestañas),
      responde 409 `refresh_token_rotated` sin cerrar la sesión: relee el token más
      reciente de tu almacenamiento y reintenta."""
    return await auth_service.rotate_refresh_token(
        session, payload.refresh_token, request.headers.get("user-agent"), client_ip(request)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_REFRESH, key_func=ip_key)
async def logout(
    request: Request, response: Response, payload: RefreshRequest, session: SessionDep
) -> None:
    """Cierra la sesión asociada a este refresh token. El access token ya emitido
    sigue siendo válido hasta que caduca (ACCESS_TOKEN_EXPIRE_MINUTES); para
    invalidarlo al instante usa /logout-all."""
    await auth_service.revoke_by_token(session, payload.refresh_token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(request: Request, user: CurrentUser, session: SessionDep) -> None:
    """Cierra TODAS las sesiones del usuario e invalida sus access tokens."""
    await auth_service.revoke_all_sessions(session, user)
    audit("auth.logout_all", user_id=user.id, client_ip=client_ip(request))
