import os
from contextlib import closing
from io import BytesIO
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services import auth_store


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "auth.sqlite3"
        self.env = patch.dict(os.environ, {"AUTH_DB_PATH": str(self.db), "ENV": "local"})
        self.env.start()
        self.client = TestClient(app, base_url="http://localhost:9000")
        self.headers = {"Origin": "http://localhost:5173", "X-LDA-Request": "auth"}
        self.member = {"username": "Test_User", "nickname": "테스트 회원", "password": "test-pass-123"}

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.temp.cleanup()

    def register(self):
        return self.client.post("/api/auth/register", json=self.member, headers=self.headers)

    def login(self):
        return self.client.post("/api/auth/login", json={key: self.member[key] for key in ("username", "password")}, headers=self.headers)

    def test_member_lifecycle_and_logout_revocation(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        registered = self.register()
        self.assertEqual(registered.status_code, 201)
        self.assertEqual(registered.json()["username"], "test_user")
        self.assertNotIn("password", registered.text)
        logged_in = self.login()
        self.assertEqual(logged_in.status_code, 200)
        cookie = logged_in.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertIn("max-age=28800", cookie)
        token = self.client.cookies.get("lda_session")
        self.assertEqual(self.client.get("/api/auth/me").json()["nickname"], "테스트 회원")
        self.assertEqual(self.client.post("/api/auth/logout", headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.client.cookies.set("lda_session", token)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_duplicate_username_is_case_insensitive(self):
        self.assertEqual(self.register().status_code, 201)
        duplicate = dict(self.member, username="test_user")
        self.assertEqual(self.client.post("/api/auth/register", json=duplicate, headers=self.headers).status_code, 409)

    def test_unknown_user_and_wrong_password_have_same_error(self):
        self.register()
        results = []
        for username, password in [("unknown", "test-pass-123"), ("test_user", "wrong-pass-123")]:
            result = self.client.post("/api/auth/login", json={"username": username, "password": password}, headers=self.headers)
            self.assertEqual(result.status_code, 401)
            results.append(result.json())
        self.assertEqual(results[0], results[1])

    def test_password_validation_does_not_echo_secret(self):
        result = self.client.post("/api/auth/register", json=dict(self.member, password="secret"), headers=self.headers)
        self.assertEqual(result.status_code, 422)
        self.assertNotIn("secret", result.text)

    def test_registration_password_length_boundaries(self):
        for length, expected in [(7, 422), (8, 201), (20, 201), (21, 422)]:
            with self.subTest(length=length):
                payload = dict(self.member, username=f"length_{length}", password="a" * length)
                result = self.client.post("/api/auth/register", json=payload, headers=self.headers)
                self.assertEqual(result.status_code, expected)

    def test_existing_long_password_still_logs_in(self):
        password = "legacy-password-" * 4
        auth_store.register("legacy_user", "기존 회원", password)
        result = self.client.post("/api/auth/login", json={"username": "legacy_user", "password": password}, headers=self.headers)
        self.assertEqual(result.status_code, 200)

    def test_nickname_update_persists_and_keeps_username(self):
        self.register()
        self.login()
        result = self.client.post("/api/auth/nickname", json={"nickname": "  새 닉네임  "}, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["nickname"], "새 닉네임")
        self.assertEqual(result.json()["username"], "test_user")
        self.assertEqual(self.client.get("/api/auth/me").json()["nickname"], "새 닉네임")

    def test_profile_does_not_accept_username_or_another_member_id(self):
        self.register()
        self.login()
        other = auth_store.register("another_user", "다른 회원", "other-pass-123")
        for extra in [{"username": "changed"}, {"id": other["id"]}]:
            result = self.client.post("/api/auth/nickname", json={"nickname": "변경", **extra}, headers=self.headers)
            self.assertEqual(result.status_code, 422)
        self.assertEqual(self.client.get("/api/auth/me").json()["nickname"], self.member["nickname"])
        self.assertEqual(auth_store.authenticate("another_user", "other-pass-123")["nickname"], "다른 회원")

    def test_profile_mutations_require_login_and_trusted_origin(self):
        for path, payload in [("nickname", {"nickname": "변경"}), ("password", {"currentPassword": "test-pass-123", "newPassword": "new-pass-123"})]:
            self.assertEqual(self.client.post(f"/api/auth/{path}", json=payload, headers=self.headers).status_code, 401)
            self.assertEqual(self.client.post(f"/api/auth/{path}", json=payload).status_code, 403)

    def test_blank_or_long_nickname_is_rejected(self):
        self.register()
        self.login()
        for nickname in ["", "   ", "가" * 31]:
            self.assertEqual(self.client.post("/api/auth/nickname", json={"nickname": nickname}, headers=self.headers).status_code, 422)

    def test_wrong_current_password_keeps_account_and_session(self):
        self.register()
        self.login()
        result = self.client.post("/api/auth/password", json={"currentPassword": "wrong-pass-123", "newPassword": "new-pass-123"}, headers=self.headers)
        self.assertEqual(result.status_code, 400)
        self.assertIn("현재 비밀번호가 올바르지 않습니다.", result.json()["error"]["message"])
        self.assertIsNotNone(auth_store.authenticate("test_user", self.member["password"]))
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

    def test_password_change_revokes_all_own_sessions_only(self):
        self.register()
        self.login()
        own_id = self.client.get("/api/auth/me").json()["id"]
        second_token = auth_store.create_session(own_id)
        other = auth_store.register("another_user", "다른 회원", "other-pass-123")
        other_token = auth_store.create_session(other["id"])
        result = self.client.post("/api/auth/password", json={"currentPassword": self.member["password"], "newPassword": "new-pass-123"}, headers=self.headers)
        self.assertEqual(result.status_code, 204)
        self.assertIn("Max-Age=0", result.headers["set-cookie"])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertIsNone(auth_store.session_member(second_token))
        self.assertIsNotNone(auth_store.session_member(other_token))
        self.assertIsNone(auth_store.authenticate("test_user", self.member["password"]))
        self.assertIsNotNone(auth_store.authenticate("test_user", "new-pass-123"))

    def test_new_password_boundaries_and_same_password(self):
        self.register()
        self.login()
        for password, expected in [("a" * 7, 422), ("a" * 21, 422), (self.member["password"], 400)]:
            result = self.client.post("/api/auth/password", json={"currentPassword": self.member["password"], "newPassword": password}, headers=self.headers)
            self.assertEqual(result.status_code, expected)
        result = self.client.post("/api/auth/password", json={"currentPassword": self.member["password"], "newPassword": "a" * 20}, headers=self.headers)
        self.assertEqual(result.status_code, 204)

    def test_legacy_long_current_password_can_be_changed(self):
        password = "legacy-password-" * 4
        member = auth_store.register("legacy_user", "기존 회원", password)
        self.client.cookies.set("lda_session", auth_store.create_session(member["id"]))
        result = self.client.post("/api/auth/password", json={"currentPassword": password, "newPassword": "new-pass-123"}, headers=self.headers)
        self.assertEqual(result.status_code, 204)

    def test_session_delete_failure_rolls_back_password_change(self):
        self.register()
        self.login()
        token = self.client.cookies.get("lda_session")
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("""CREATE TRIGGER prevent_session_delete BEFORE DELETE ON sessions
                BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
            db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            auth_store.change_password(token, self.member["password"], "new-pass-123")
        self.assertIsNotNone(auth_store.authenticate("test_user", self.member["password"]))
        self.assertIsNotNone(auth_store.session_member(token))

    def test_invalid_username_and_blank_nickname(self):
        for changed in [{"username": "ab"}, {"username": "has space"}, {"nickname": "   "}]:
            with self.subTest(changed=changed):
                result = self.client.post("/api/auth/register", json=dict(self.member, **changed), headers=self.headers)
                self.assertEqual(result.status_code, 422)

    def test_csrf_requests_are_rejected(self):
        for headers in [{}, {"Origin": "https://untrusted.example", "X-LDA-Request": "auth"}, {"Origin": "http://localhost:5173"}]:
            for path in ["register", "login", "logout"]:
                with self.subTest(path=path, headers=headers):
                    self.assertEqual(self.client.post(f"/api/auth/{path}", json=self.member, headers=headers).status_code, 403)

    def test_password_and_session_are_hashed_at_rest(self):
        self.register()
        self.login()
        with closing(sqlite3.connect(self.db)) as db:
            hashed = db.execute("SELECT password_hash FROM members").fetchone()[0]
            token_hash = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
        self.assertTrue(hashed.startswith("$argon2id$"))
        self.assertNotEqual(hashed, self.member["password"])
        self.assertTrue(auth_store.PASSWORD_HASH.verify(self.member["password"], hashed))
        self.assertNotEqual(token_hash, self.client.cookies.get("lda_session"))

    def test_expired_session_is_rejected(self):
        self.register()
        self.login()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE sessions SET expires_at = ?", (int(time.time()) - 1,))
            db.commit()
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_login_rotates_previous_session(self):
        self.register()
        self.login()
        first = self.client.cookies.get("lda_session")
        self.login()
        self.assertNotEqual(first, self.client.cookies.get("lda_session"))
        self.assertIsNone(auth_store.session_member(first))

    def test_secure_cookie_outside_local(self):
        self.register()
        with patch.dict(os.environ, {"ENV": "prod", "AUTH_ALLOWED_ORIGINS": "http://localhost:5173"}):
            self.assertIn("Secure", self.login().headers["set-cookie"])

    def test_member_persists_across_clients(self):
        self.register()
        with TestClient(app, base_url="http://localhost:9000") as client:
            response = client.post("/api/auth/login", json={"username": "test_user", "password": self.member["password"]}, headers=self.headers)
            self.assertEqual(response.status_code, 200)

    def test_existing_guide_routes_remain_registered(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/api/guide/analyze", paths)
        self.assertIn("/api/guide/steps", paths)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_existing_image_analysis_and_steps_work_without_login(self):
        image = BytesIO()
        Image.new("RGB", (16, 16), "red").save(image, format="PNG")
        analyzed = self.client.post("/api/guide/analyze",
                                    files={"image": ("test.png", image.getvalue(), "image/png")},
                                    data={"grid_size": "16x16", "max_colors": "8"})
        self.assertEqual(analyzed.status_code, 200)
        steps = self.client.post("/api/guide/steps", json={"analysisId": analyzed.json()["analysisId"]})
        self.assertEqual(steps.status_code, 200)
        self.assertTrue(steps.json()["steps"])


if __name__ == "__main__":
    unittest.main()
