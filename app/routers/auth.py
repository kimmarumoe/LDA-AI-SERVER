import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.env import app_env, cors_allow_origins
from app.schemas.auth import LoginInput, RegisterInput, Member, NicknameInput, PasswordInput
from app.services import auth_store

COOKIE_NAME = "lda_session"
router = APIRouter(prefix="/api/auth", tags=["auth"])


def secure_cookie():
    return app_env() != "local"


def validate_mutation(request: Request):
    # 브라우저의 다른 사이트가 로그인·로그아웃을 대신 요청하지 못하게 한다.
    configured = os.getenv("AUTH_ALLOWED_ORIGINS", "").strip() or cors_allow_origins()
    allowed = {origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()}
    if app_env() == "local":
        allowed.update({"http://localhost:5173", "http://127.0.0.1:5173"})
    if request.headers.get("origin") not in allowed or request.headers.get("x-lda-request") != "auth":
        raise HTTPException(403, "허용되지 않은 인증 요청입니다.")


@router.post("/register", response_model=Member, status_code=201, dependencies=[Depends(validate_mutation)])
def register(payload: RegisterInput, response: Response):
    try:
        member = auth_store.register(payload.username, payload.nickname, payload.password)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "이미 사용 중인 아이디입니다.") from None
    response.headers["Cache-Control"] = "no-store"
    return member


@router.post("/login", response_model=Member, dependencies=[Depends(validate_mutation)])
def login(payload: LoginInput, request: Request, response: Response):
    member = auth_store.authenticate(payload.username, payload.password)
    if not member:
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    token = auth_store.create_session(member["id"], request.cookies.get(COOKIE_NAME))
    response.set_cookie(COOKIE_NAME, token, max_age=auth_store.SESSION_SECONDS,
                        httponly=True, secure=secure_cookie(), samesite="lax", path="/api/auth")
    response.headers["Cache-Control"] = "no-store"
    return member


@router.get("/me", response_model=Member)
def me(request: Request, response: Response):
    member = auth_store.session_member(request.cookies.get(COOKIE_NAME))
    if not member:
        raise HTTPException(401, "로그인이 필요하거나 로그인 시간이 만료되었습니다.")
    response.headers["Cache-Control"] = "no-store"
    return member


@router.post("/logout", status_code=204, dependencies=[Depends(validate_mutation)])
def logout(request: Request, response: Response):
    auth_store.delete_session(request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/api/auth", httponly=True,
                           secure=secure_cookie(), samesite="lax")
    response.headers["Cache-Control"] = "no-store"


@router.post("/nickname", response_model=Member, dependencies=[Depends(validate_mutation)])
def update_nickname(payload: NicknameInput, request: Request, response: Response):
    try:
        member = auth_store.update_nickname(request.cookies.get(COOKIE_NAME), payload.nickname)
    except PermissionError as error:
        raise HTTPException(401, str(error)) from None
    response.headers["Cache-Control"] = "no-store"
    return member


@router.post("/password", status_code=204, dependencies=[Depends(validate_mutation)])
def change_password(payload: PasswordInput, request: Request, response: Response):
    try:
        auth_store.change_password(request.cookies.get(COOKIE_NAME), payload.currentPassword, payload.newPassword)
    except PermissionError as error:
        raise HTTPException(401, str(error)) from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    response.delete_cookie(COOKIE_NAME, path="/api/auth", httponly=True,
                           secure=secure_cookie(), samesite="lax")
    response.headers["Cache-Control"] = "no-store"
