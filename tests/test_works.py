import copy
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from io import BytesIO
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app.services import work_store


class WorkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"AUTH_DB_PATH": str(Path(self.temp.name) / "auth.sqlite3"), "ENV": "local"})
        self.env.start()
        self.client = TestClient(app, base_url="http://localhost:9000")
        self.headers = {"Origin": "http://localhost:5173", "X-LDA-Request": "auth"}
        self.login(self.client, "first")
        brick = {"id": "0,0:1x1", "x": 0, "y": 0, "type": "1x1", "hex": "#FFFFFF", "color": "흰색"}
        self.payload = {"title": "  내 작품  ", "analysis": {
            "analysisId": "temporary-token", "summary": {"totalBricks": 1, "uniqueTypes": 1, "difficulty": "초급", "estimatedTime": "1분"},
            "bricks": [brick], "palette": [], "meta": {"width": 1, "height": 1, "createdAt": "2026-10-22T00:00:00Z"}},
            "steps": [{"id": "step-1", "sectionId": "S1", "index": 1, "title": "1단계", "bricks": [brick]}],
            "options": {"gridSize": "16x16", "colorLimit": 16}}

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.temp.cleanup()

    def login(self, client, username):
        self.assertEqual(client.post("/api/auth/register", headers=self.headers, json={"username": username, "nickname": username, "password": "test-password"}).status_code, 201)
        self.assertEqual(client.post("/api/auth/login", headers=self.headers, json={"username": username, "password": "test-password"}).status_code, 200)

    def save(self, payload=None):
        return self.client.post("/api/auth/works", json=payload or self.payload, headers=self.headers)

    def test_save_list_detail_and_reopen_storage(self):
        saved = self.save()
        self.assertEqual(saved.status_code, 201, saved.text)
        self.assertEqual(saved.headers["cache-control"], "no-store")
        self.assertEqual(saved.json()["title"], "내 작품")
        listing = self.client.get("/api/auth/works").json()
        self.assertEqual(listing, [saved.json()])
        self.assertNotIn("analysis", listing[0])
        importlib.reload(work_store)
        with TestClient(app, base_url="http://localhost:9000") as reopened:
            reopened.cookies.update(self.client.cookies)
            detail = reopened.get('/api/auth/works/' + saved.json()["id"])
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["steps"][0]["bricks"][0]["hex"], "#FFFFFF")
        self.assertEqual(detail.json()["options"], self.payload["options"])
        self.assertIsNone(detail.json()["analysis"]["analysisId"])

    def test_ownership_and_missing_work(self):
        work_id = self.save().json()["id"]
        with TestClient(app, base_url="http://localhost:9000") as other:
            self.login(other, "second")
            self.assertEqual(other.get("/api/auth/works").json(), [])
            self.assertEqual(other.get(f"/api/auth/works/{work_id}").status_code, 404)
        self.assertEqual(self.client.get("/api/auth/works/missing").status_code, 404)

    def test_no_session_and_revoked_session(self):
        work_id = self.save().json()["id"]
        self.client.post("/api/auth/logout", headers=self.headers)
        self.assertEqual(self.save().status_code, 401)
        self.assertEqual(self.client.get("/api/auth/works").status_code, 401)
        self.assertEqual(self.client.get(f"/api/auth/works/{work_id}").status_code, 401)

    def test_mutation_origin_and_owner_injection(self):
        self.assertEqual(self.client.post("/api/auth/works", json=self.payload).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/works", json=self.payload, headers={**self.headers, "Origin": "https://other.example"}).status_code, 403)
        self.assertEqual(self.save({**self.payload, "member_id": 999}).status_code, 422)

    def test_incomplete_and_invalid_data(self):
        bad = [dict(self.payload, title="  "), dict(self.payload, title="가" * 81), dict(self.payload, steps=[])]
        no_bricks = copy.deepcopy(self.payload)
        no_bricks["analysis"]["bricks"] = []
        bad.append(no_bricks)
        for payload in bad:
            self.assertEqual(self.save(payload).status_code, 422)
        self.assertEqual(self.client.get("/api/auth/works").json(), [])

    def test_newest_first(self):
        first = self.save().json()
        second = self.save(dict(self.payload, title="두 번째")).json()
        self.assertEqual([w["id"] for w in self.client.get("/api/auth/works").json()], [second["id"], first["id"]])

    def test_real_analysis_and_steps_snapshot(self):
        image = BytesIO()
        Image.new("RGB", (16, 16), "white").save(image, format="PNG")
        response = self.client.post("/api/guide/analyze", files={"image": ("test.png", image.getvalue(), "image/png")}, data={"grid_size": "16x16"})
        self.assertEqual(response.status_code, 200, response.text)
        analysis = response.json()
        generated = self.client.post("/api/guide/steps", json={"analysisId": analysis["analysisId"]})
        self.assertEqual(generated.status_code, 200, generated.text)
        saved = self.save({"title": "실제 분석", "analysis": analysis, "steps": generated.json()["steps"], "options": {}})
        self.assertEqual(saved.status_code, 201, saved.text)
        detail = self.client.get('/api/auth/works/' + saved.json()["id"]).json()
        self.assertEqual(detail["steps"], generated.json()["steps"])

    def test_rename_persists_and_preserves_guide(self):
        work = self.save().json()
        path = '/api/auth/works/' + work['id']
        before = self.client.get(path).json()
        renamed = self.client.patch(path, headers=self.headers, json={'title': '  바꾼 이름  '})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json(), {**work, 'title': '바꾼 이름'})
        self.assertEqual(renamed.headers['cache-control'], 'no-store')
        with TestClient(app, base_url='http://localhost:9000') as reopened:
            reopened.cookies.update(self.client.cookies)
            self.assertEqual(reopened.get(path).json(), {**before, 'title': '바꾼 이름'})
        self.assertEqual(self.client.get('/api/auth/works').json()[0]['title'], '바꾼 이름')

    def test_delete_removes_only_target_work_and_is_persistent(self):
        removed = self.save().json()
        kept = self.save(dict(self.payload, title='유지할 작품')).json()
        path = '/api/auth/works/' + removed['id']
        response = self.client.delete(path, headers=self.headers)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b'')
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get('/api/auth/works').json(), [kept])
        with TestClient(app, base_url='http://localhost:9000') as reopened:
            reopened.cookies.update(self.client.cookies)
            self.assertEqual(reopened.get(path).status_code, 404)

    def test_rename_and_delete_require_owner_and_valid_session(self):
        work = self.save().json()
        path = '/api/auth/works/' + work['id']
        with TestClient(app, base_url='http://localhost:9000') as other:
            self.login(other, 'second')
            self.assertEqual(other.patch(path, headers=self.headers, json={'title': '탈취'}).status_code, 404)
            self.assertEqual(other.delete(path, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get(path).json()['title'], work['title'])
        self.assertEqual(self.client.patch('/api/auth/works/missing', headers=self.headers, json={'title': '제목'}).status_code, 404)
        self.assertEqual(self.client.delete('/api/auth/works/missing', headers=self.headers).status_code, 404)
        self.client.post('/api/auth/logout', headers=self.headers)
        self.assertEqual(self.client.patch(path, headers=self.headers, json={'title': '제목'}).status_code, 401)
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 401)

    def test_rename_and_delete_validate_request_origin(self):
        path = '/api/auth/works/' + self.save().json()['id']
        for headers in ({}, {**self.headers, 'Origin': 'https://other.example'}, {'Origin': self.headers['Origin']}):
            self.assertEqual(self.client.patch(path, headers=headers, json={'title': '제목'}).status_code, 403)
            self.assertEqual(self.client.delete(path, headers=headers).status_code, 403)
        self.assertEqual(self.client.get(path).status_code, 200)

    def test_rename_rejects_invalid_input_and_accepts_boundaries(self):
        work = self.save().json()
        path = '/api/auth/works/' + work['id']
        for payload in ({}, {'title': '  '}, {'title': '가'*81}, {'title': '새 이름', 'member_id': 2}, {'title': '새 이름', 'analysis': {}}, {'title': None}):
            response = self.client.patch(path, headers=self.headers, json=payload)
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get(path).json()['title'], work['title'])
        for title in ('가', '가'*80):
            self.assertEqual(self.client.patch(path, headers=self.headers, json={'title': title}).status_code, 200)
