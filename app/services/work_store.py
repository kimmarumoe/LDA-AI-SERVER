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
    db.execute("""CREATE TABLE IF NOT EXISTS work_progress (
        work_id TEXT PRIMARY KEY REFERENCES works(id) ON DELETE CASCADE,
        step_index INTEGER NOT NULL CHECK(step_index >= 0), saved_at TEXT NOT NULL)""")


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
        payload = json.loads(row["payload"])
        progress = db.execute("SELECT step_index, saved_at FROM work_progress WHERE work_id = ?", (work_id,)).fetchone()
        saved = {"stepIndex": min(progress["step_index"], max(0, len(payload["steps"]) - 1)), "savedAt": progress["saved_at"]} if progress else {"stepIndex": 0, "savedAt": None}
        return {**summary(row), **payload, "progress": saved}


def rename_work(token, work_id, title):
    with connection() as db:
        member = editable_member(db, token)
        prepare(db)
        cursor = db.execute("UPDATE works SET title = ? WHERE id = ? AND member_id = ?",
                            (title, work_id, member["id"]))
        if cursor.rowcount == 0:
            raise LookupError("수정할 작품을 찾을 수 없습니다.")
        row = db.execute("SELECT id, title, created_at FROM works WHERE id = ? AND member_id = ?",
                         (work_id, member["id"])).fetchone()
        return summary(row)


def delete_work(token, work_id):
    with connection() as db:
        member = editable_member(db, token)
        prepare(db)
        # 게시글은 작품과 독립된 복사본이므로 여기서는 개인 작품만 삭제한다.
        cursor = db.execute("DELETE FROM works WHERE id = ? AND member_id = ?", (work_id, member["id"]))
        if cursor.rowcount == 0:
            raise LookupError("삭제할 작품을 찾을 수 없습니다.")


class InvalidProgress(ValueError):
    pass


def update_progress(token, work_id, step_index):
    with connection() as db:
        member = editable_member(db, token)
        prepare(db)
        row = db.execute("SELECT payload FROM works WHERE id = ? AND member_id = ?", (work_id, member["id"])).fetchone()
        if row is None:
            raise LookupError("진행 위치를 저장할 작품을 찾을 수 없습니다.")
        total = len(json.loads(row["payload"])["steps"])
        if not 0 <= step_index < total:
            raise InvalidProgress("작품의 조립 단계 범위를 벗어났습니다.")
        saved_at = datetime.now(timezone.utc).isoformat()
        db.execute("""INSERT INTO work_progress (work_id, step_index, saved_at) VALUES (?, ?, ?)
            ON CONFLICT(work_id) DO UPDATE SET step_index = excluded.step_index, saved_at = excluded.saved_at""",
                   (work_id, step_index, saved_at))
        return {"stepIndex": step_index, "savedAt": saved_at}
