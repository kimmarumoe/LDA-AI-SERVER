"""회원과 세션의 저장을 담당한다. 비밀번호와 세션 원문은 DB에 저장하지 않는다."""
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import contextmanager

from pwdlib import PasswordHash

PASSWORD_HASH = PasswordHash.recommended()
DUMMY_HASH = PASSWORD_HASH.hash(secrets.token_urlsafe(32))
SESSION_SECONDS = 8 * 60 * 60


@contextmanager
def connection():
    path = Path(os.getenv("AUTH_DB_PATH", str(Path(__file__).resolve().parents[2] / "data" / "auth.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("""CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
            nickname TEXT NOT NULL, password_hash TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(id),
            expires_at INTEGER NOT NULL)""")
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
        yield db
        db.commit()
    finally:
        db.close()


def public_member(row):
    return {key: row[key] for key in ("id", "username", "nickname")}


def register(username, nickname, password):
    hashed = PASSWORD_HASH.hash(password)
    with connection() as db:
        cursor = db.execute("INSERT INTO members (username, nickname, password_hash) VALUES (?, ?, ?)",
                            (username.lower(), nickname.strip(), hashed))
        return public_member(db.execute("SELECT * FROM members WHERE id = ?", (cursor.lastrowid,)).fetchone())


def authenticate(username, password):
    with connection() as db:
        row = db.execute("SELECT * FROM members WHERE username = ?", (username.lower(),)).fetchone()
    valid = PASSWORD_HASH.verify(password, row["password_hash"] if row else DUMMY_HASH)
    return public_member(row) if row and valid else None


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(member_id, previous_token=None):
    token = secrets.token_urlsafe(32)
    with connection() as db:
        if previous_token:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(previous_token),))
        db.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                   (token_hash(token), member_id, int(time.time()) + SESSION_SECONDS))
    return token


def session_member(token):
    if not token:
        return None
    with connection() as db:
        row = db.execute("""SELECT m.id, m.username, m.nickname FROM members m
            JOIN sessions s ON s.member_id = m.id WHERE s.token_hash = ? AND s.expires_at > ?""",
                         (token_hash(token), int(time.time()))).fetchone()
        return public_member(row) if row else None


def delete_session(token):
    if token:
        with connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))


def editable_member(db, token):
    row = db.execute("""SELECT m.* FROM members m JOIN sessions s ON s.member_id = m.id
        WHERE s.token_hash = ? AND s.expires_at > ?""",
                     (token_hash(token or ""), int(time.time()))).fetchone()
    if row is None:
        raise PermissionError("로그인이 필요하거나 로그인 시간이 만료되었습니다.")
    return row


def update_nickname(token, nickname):
    with connection() as db:
        member = editable_member(db, token)
        db.execute("UPDATE members SET nickname = ? WHERE id = ?", (nickname.strip(), member["id"]))
        return public_member(db.execute("SELECT * FROM members WHERE id = ?", (member["id"],)).fetchone())


def change_password(token, current_password, new_password):
    # 같은 트랜잭션 안에서 검증·변경·세션 폐기를 모두 반영한다.
    with connection() as db:
        member = editable_member(db, token)
        if not PASSWORD_HASH.verify(current_password, member["password_hash"]):
            raise ValueError("현재 비밀번호가 올바르지 않습니다.")
        if current_password == new_password:
            raise ValueError("새 비밀번호는 현재 비밀번호와 다르게 입력해 주세요.")
        db.execute("UPDATE members SET password_hash = ? WHERE id = ?",
                   (PASSWORD_HASH.hash(new_password), member["id"]))
        db.execute("DELETE FROM sessions WHERE member_id = ?", (member["id"],))
