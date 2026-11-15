"""댓글과 좋아요의 소유권·중복 방지·게시글별 분리를 담당한다."""
from datetime import datetime, timezone
import uuid
from app.services.auth_store import connection, editable_member, session_member


def prepare(db):
    db.execute("""CREATE TABLE IF NOT EXISTS post_comments (
        id TEXT PRIMARY KEY, post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        member_id INTEGER NOT NULL REFERENCES members(id), content TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS comments_post_created ON post_comments(post_id, created_at DESC, id DESC)")
    db.execute("""CREATE TABLE IF NOT EXISTS post_likes (
        post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        member_id INTEGER NOT NULL REFERENCES members(id), PRIMARY KEY (post_id, member_id))""")


def require_post(db, post_id):
    # 로컬 import로 게시글 저장 모듈과의 순환 import를 피한다.
    from app.services.post_store import prepare as prepare_posts
    prepare_posts(db)
    if db.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone() is None:
        raise LookupError("게시글을 찾을 수 없습니다.")


def is_liked(db, post_id, member_id):
    return bool(member_id and db.execute("SELECT 1 FROM post_likes WHERE post_id = ? AND member_id = ?",
                                        (post_id, member_id)).fetchone())


def comment_count(db, post_id):
    return db.execute("SELECT COUNT(*) FROM post_comments WHERE post_id = ?", (post_id,)).fetchone()[0]


def public_comment(row, member_id):
    return {"id": row["id"], "content": row["content"], "nickname": row["nickname"],
            "createdAt": row["created_at"], "updatedAt": row["updated_at"],
            "edited": row["created_at"] != row["updated_at"], "canEdit": row["member_id"] == member_id}


def comment_row(db, post_id, comment_id):
    row = db.execute("""SELECT c.*, m.nickname FROM post_comments c JOIN members m ON m.id = c.member_id
        WHERE c.id = ? AND c.post_id = ?""", (comment_id, post_id)).fetchone()
    if row is None:
        raise LookupError("댓글을 찾을 수 없습니다.")
    return row


def list_comments(post_id, token, offset, limit):
    member = session_member(token)
    with connection() as db:
        require_post(db, post_id)
        rows = db.execute("""SELECT c.*, m.nickname FROM post_comments c JOIN members m ON m.id = c.member_id
            WHERE c.post_id = ? ORDER BY c.created_at DESC, c.id DESC LIMIT ? OFFSET ?""",
                          (post_id, limit + 1, offset)).fetchall()
        return {"items": [public_comment(row, member["id"] if member else None) for row in rows[:limit]],
                "hasMore": len(rows) > limit, "total": comment_count(db, post_id)}


def create_comment(token, post_id, content):
    with connection() as db:
        member = editable_member(db, token)
        require_post(db, post_id)
        comment_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        db.execute("INSERT INTO post_comments VALUES (?, ?, ?, ?, ?, ?)",
                   (comment_id, post_id, member["id"], content, now, now))
        return {"comment": public_comment(comment_row(db, post_id, comment_id), member["id"]),
                "commentCount": comment_count(db, post_id)}


def edit_comment(token, post_id, comment_id, content):
    with connection() as db:
        member = editable_member(db, token)
        require_post(db, post_id)
        cursor = db.execute("UPDATE post_comments SET content = ?, updated_at = ? WHERE id = ? AND post_id = ? AND member_id = ?",
                            (content, datetime.now(timezone.utc).isoformat(), comment_id, post_id, member["id"]))
        if cursor.rowcount == 0:
            raise LookupError("수정할 댓글을 찾을 수 없습니다.")
        return {"comment": public_comment(comment_row(db, post_id, comment_id), member["id"]),
                "commentCount": comment_count(db, post_id)}


def delete_comment(token, post_id, comment_id):
    with connection() as db:
        member = editable_member(db, token)
        require_post(db, post_id)
        cursor = db.execute("DELETE FROM post_comments WHERE id = ? AND post_id = ? AND member_id = ?",
                            (comment_id, post_id, member["id"]))
        if cursor.rowcount == 0:
            raise LookupError("삭제할 댓글을 찾을 수 없습니다.")
        return {"commentCount": comment_count(db, post_id)}


def set_like(token, post_id, liked):
    with connection() as db:
        member = editable_member(db, token)
        require_post(db, post_id)
        if liked:
            # 같은 PUT이 재전송되어도 좋아요는 한 번만 기록한다.
            db.execute("INSERT INTO post_likes VALUES (?, ?) ON CONFLICT(post_id, member_id) DO NOTHING",
                       (post_id, member["id"]))
        else:
            db.execute("DELETE FROM post_likes WHERE post_id = ? AND member_id = ?", (post_id, member["id"]))
        count = db.execute("SELECT COUNT(*) FROM post_likes WHERE post_id = ?", (post_id,)).fetchone()[0]
        return {"likedByMe": is_liked(db, post_id, member["id"]), "likeCount": count}
