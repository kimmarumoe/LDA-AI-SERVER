"""회원 DB에 가이드의 스냅샷을 저장하고 소유자별로 조회한다."""
from datetime import datetime, timezone
import json
import uuid
from app.services.auth_store import connection, editable_member


def prepare(db):
    db.execute("""CREATE TABLE IF NOT EXISTS works (
        id TEXT PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(id),
        title TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS works_member_created ON works(member_id, created_at DESC)")


def summary(row):
    return {"id": row["id"], "title": row["title"], "createdAt": row["created_at"]}


def save(token, payload):
    with connection() as db:
        member = editable_member(db, token)
        prepare(db)
        work_id = uuid.uuid4().hex
        created = datetime.now(timezone.utc).isoformat()
        snapshot = payload.model_dump(exclude={"title"})
        # 만료되는 분석 번호를 영구 작품의 참조로 사용하지 않는다.
        snapshot["analysis"]["analysisId"] = None
        db.execute("INSERT INTO works VALUES (?, ?, ?, ?, ?)",
                   (work_id, member["id"], payload.title, created,
                    json.dumps(snapshot, ensure_ascii=False)))
        return {"id": work_id, "title": payload.title, "createdAt": created}


def list_works(token):
    with connection() as db:
        member = editable_member(db, token)
        prepare(db)
        rows = db.execute("SELECT id, title, created_at FROM works WHERE member_id = ? ORDER BY created_at DESC, id DESC",
                          (member["id"],)).fetchall()
        return [summary(row) for row in rows]


def get_work(token, work_id):
    with connection() as db:
        member = editable_member(db, token)
        prepare(db)
        row = db.execute("SELECT * FROM works WHERE id = ? AND member_id = ?",
                         (work_id, member["id"])).fetchone()
        if row is None:
            raise LookupError("작품을 찾을 수 없습니다.")
        return {**summary(row), **json.loads(row["payload"])}
