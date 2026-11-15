"""개인 작품과 독립된 공개 스냅샷을 저장한다."""
from datetime import datetime, timezone
import json
import math
import re
import uuid
from fastapi import HTTPException
from app.services.auth_store import connection, editable_member, session_member
from app.services.work_store import prepare as prepare_works
from app.schemas.works import WorkInput


def prepare(db):
    db.execute("""CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(id),
        title TEXT NOT NULL, description TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        snapshot TEXT NOT NULL, thumbnail TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS posts_created ON posts(created_at DESC, id DESC)")


def thumbnail(analysis):
    width, height = analysis["meta"]["width"], analysis["meta"]["height"]
    if not (1 <= width <= 128 and 1 <= height <= 128):
        raise HTTPException(422, "공유할 작품의 크기가 올바르지 않습니다.")
    scale = max(1, math.ceil(max(width, height) / 24))
    cells = {}
    for brick in analysis["bricks"]:
        x, y = brick["x"], brick["y"]
        if not (0 <= x < width and 0 <= y < height):
            raise HTTPException(422, "브릭 좌표가 작품 범위를 벗어났습니다.")
        color = brick["hex"]
        if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            # 작은 목록 미리보기는 같은 칸을 대표 색상 하나로 표시한다.
            cells[(x // scale, y // scale)] = color
    return {"width": math.ceil(width / scale), "height": math.ceil(height / scale),
            "cells": [{"x": x, "y": y, "hex": color} for (x, y), color in cells.items()]}


def summary(row):
    return {"id": row["id"], "title": row["title"], "description": row["description"],
            "nickname": row["nickname"], "createdAt": row["created_at"], "updatedAt": row["updated_at"],
            "thumbnail": json.loads(row["thumbnail"])}


def detail_row(db, post_id):
    row = db.execute("SELECT p.*, m.nickname FROM posts p JOIN members m ON m.id = p.member_id WHERE p.id = ?", (post_id,)).fetchone()
    if row is None:
        raise LookupError("게시글을 찾을 수 없습니다.")
    return row


def create(token, payload):
    with connection() as db:
        member = editable_member(db, token)
        prepare_works(db)
        work = db.execute("SELECT * FROM works WHERE id = ? AND member_id = ?", (payload.workId, member["id"])).fetchone()
        if work is None:
            raise LookupError("공유할 내 작품을 찾을 수 없습니다.")
        # 사용자가 보낸 가이드 대신 서버에 저장된 본인 작품에서 복사한다.
        saved = WorkInput.model_validate({**json.loads(work["payload"]), "title": work["title"]})
        snapshot = saved.model_dump(include={"analysis", "steps"})
        snapshot["analysis"]["analysisId"] = None
        cover = thumbnail(snapshot["analysis"])
        prepare(db)
        post_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        db.execute("INSERT INTO posts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (post_id, member["id"], payload.title, payload.description, now, now,
                    json.dumps(snapshot, ensure_ascii=False), json.dumps(cover)))
        return {**summary(detail_row(db, post_id)), **snapshot, "canEdit": True}


def list_posts(offset, limit):
    with connection() as db:
        prepare(db)
        rows = db.execute("""SELECT p.id, p.title, substr(p.description, 1, 160) AS description,
            p.created_at, p.updated_at, p.thumbnail, m.nickname FROM posts p
            JOIN members m ON m.id = p.member_id ORDER BY p.created_at DESC, p.id DESC LIMIT ? OFFSET ?""", (limit + 1, offset)).fetchall()
        return {"items": [summary(row) for row in rows[:limit]], "hasMore": len(rows) > limit}


def get(post_id, token):
    member = session_member(token)
    with connection() as db:
        prepare(db)
        row = detail_row(db, post_id)
        return {**summary(row), **json.loads(row["snapshot"]), "canEdit": bool(member and member["id"] == row["member_id"])}


def edit(token, post_id, payload):
    with connection() as db:
        member = editable_member(db, token)
        prepare(db)
        row = detail_row(db, post_id)
        if row["member_id"] != member["id"]:
            raise LookupError("수정할 게시글을 찾을 수 없습니다.")
        db.execute("UPDATE posts SET title = ?, description = ?, updated_at = ? WHERE id = ? AND member_id = ?",
                   (payload.title, payload.description, datetime.now(timezone.utc).isoformat(), post_id, member["id"]))
        updated = detail_row(db, post_id)
        return {**summary(updated), **json.loads(updated["snapshot"]), "canEdit": True}


def delete(token, post_id):
    with connection() as db:
        member = editable_member(db, token)
        prepare(db)
        cursor = db.execute("DELETE FROM posts WHERE id = ? AND member_id = ?", (post_id, member["id"]))
        if cursor.rowcount == 0:
            raise LookupError("삭제할 게시글을 찾을 수 없습니다.")
