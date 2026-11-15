"""공개 읽기와 회원별 쓰기 권한, 개인 작품과 독립된 스냅샷을 검증한다."""
import unittest
from fastapi.testclient import TestClient
import test_works as fixtures
from app.main import app
from app.services import auth_store


class PostTests(unittest.TestCase):
    setUp = fixtures.WorkTests.setUp
    tearDown = fixtures.WorkTests.tearDown
    login = fixtures.WorkTests.login
    save = fixtures.WorkTests.save

    def create(self):
        work = self.save().json()
        response = self.client.post('/api/auth/posts', headers=self.headers,
                                    json={'workId': work['id'], 'title': '  공유 작품  ', 'description': '만드는 방법\n두 번째 줄'})
        self.assertEqual(response.status_code, 201, response.text)
        return work, response.json()

    def test_public_list_and_detail_exclude_private_member_fields(self):
        _, post = self.create()
        self.assertEqual(post['title'], '공유 작품')
        self.assertTrue(post['canEdit'])
        with TestClient(app, base_url='http://localhost:9000') as guest:
            listing = guest.get('/api/auth/posts')
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(listing.json()['items'][0]['id'], post['id'])
            self.assertNotIn('analysis', listing.json()['items'][0])
            detail = guest.get('/api/auth/posts/' + post['id'])
            self.assertEqual(detail.status_code, 200)
            data = detail.json()
            self.assertFalse(data['canEdit'])
            self.assertEqual(data['nickname'], 'first')
            for key in ('username', 'password', 'password_hash', 'member_id', 'workId', 'options'):
                self.assertNotIn(key, data)
            self.assertEqual(detail.headers['cache-control'], 'no-store')
            self.assertIsNone(data['analysis']['analysisId'])

    def test_only_owner_can_edit_and_delete(self):
        _, post = self.create()
        path = '/api/auth/posts/' + post['id']
        with TestClient(app, base_url='http://localhost:9000') as other:
            self.login(other, 'second')
            self.assertFalse(other.get(path).json()['canEdit'])
            self.assertEqual(other.patch(path, headers=self.headers, json={'title': '탈취', 'description': '다른 회원'}).status_code, 404)
            self.assertEqual(other.delete(path, headers=self.headers).status_code, 404)
        updated = self.client.patch(path, headers=self.headers, json={'title': '변경한 제목', 'description': '설명 변경'})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['title'], '변경한 제목')
        self.assertEqual(updated.json()['steps'], post['steps'])
        deleted = self.client.delete(path, headers=self.headers)
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(deleted.content, b'')
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(len(self.client.get('/api/auth/works').json()), 1)

    def test_original_changes_and_deletion_do_not_change_post(self):
        work, post = self.create()
        with auth_store.connection() as db:
            db.execute('UPDATE works SET title = ?, payload = ? WHERE id = ?', ('변경', '{}', work['id']))
        self.assertEqual(self.client.get('/api/auth/posts/' + post['id']).json()['steps'], post['steps'])
        with auth_store.connection() as db:
            db.execute('DELETE FROM works WHERE id = ?', (work['id'],))
        detail = self.client.get('/api/auth/posts/' + post['id'])
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['analysis'], post['analysis'])

    def test_mutations_require_session_and_trusted_origin(self):
        work, post = self.create()
        path = '/api/auth/posts/' + post['id']
        body = {'title': '제목', 'description': '설명'}
        self.assertEqual(self.client.post('/api/auth/posts', json={**body, 'workId': work['id']}).status_code, 403)
        self.assertEqual(self.client.patch(path, json=body).status_code, 403)
        self.assertEqual(self.client.delete(path).status_code, 403)
        with TestClient(app, base_url='http://localhost:9000') as guest:
            self.assertEqual(guest.post('/api/auth/posts', headers=self.headers, json={**body, 'workId': work['id']}).status_code, 401)
            self.assertEqual(guest.patch(path, headers=self.headers, json=body).status_code, 401)
            self.assertEqual(guest.delete(path, headers=self.headers).status_code, 401)

    def test_cannot_publish_another_members_work(self):
        work, _ = self.create()
        with TestClient(app, base_url='http://localhost:9000') as other:
            self.login(other, 'second')
            response = other.post('/api/auth/posts', headers=self.headers, json={'workId': work['id'], 'title': '탈취', 'description': '설명'})
            self.assertEqual(response.status_code, 404)

    def test_invalid_text_and_snapshot_injection(self):
        work = self.save().json()
        valid = {'workId': work['id'], 'title': '제목', 'description': '설명'}
        for invalid in ({'title': '  '}, {'description': '  '}, {'title': '가'*101}, {'description': '가'*5001}, {'member_id': 5}, {'analysis': {}}):
            response = self.client.post('/api/auth/posts', headers=self.headers, json={**valid, **invalid})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get('/api/auth/posts').json()['items'], [])

    def test_pagination_newest_first_and_missing(self):
        self.assertEqual(self.client.get('/api/auth/posts').json(), {'items': [], 'hasMore': False})
        _, first = self.create()
        _, second = self.create()
        first_page = self.client.get('/api/auth/posts?limit=1').json()
        self.assertEqual(first_page['items'][0]['id'], second['id'])
        self.assertTrue(first_page['hasMore'])
        self.assertEqual(self.client.get('/api/auth/posts?offset=1&limit=1').json()['items'][0]['id'], first['id'])
        self.assertEqual(self.client.get('/api/auth/posts?limit=100').status_code, 422)
        self.assertEqual(self.client.get('/api/auth/posts/missing').status_code, 404)

    def test_thumbnail_is_bounded_and_posts_persist(self):
        _, post = self.create()
        with TestClient(app, base_url='http://localhost:9000') as reopened:
            data = reopened.get('/api/auth/posts/' + post['id']).json()
        self.assertLessEqual(data['thumbnail']['width'], 24)
        self.assertLessEqual(data['thumbnail']['height'], 24)
        self.assertLessEqual(len(data['thumbnail']['cells']), 24*24)
        self.assertEqual(data['description'], post['description'])

    def test_work_management_api_keeps_public_post(self):
        work, post = self.create()
        work_path = '/api/auth/works/' + work['id']
        post_path = '/api/auth/posts/' + post['id']
        self.assertEqual(self.client.patch(work_path, headers=self.headers, json={'title': '개인 작품 새 이름'}).status_code, 200)
        self.assertEqual(self.client.get(post_path).json(), post)
        self.assertEqual(self.client.delete(work_path, headers=self.headers).status_code, 204)
        with TestClient(app, base_url='http://localhost:9000') as guest:
            public = guest.get(post_path)
            self.assertEqual(public.status_code, 200)
            self.assertEqual(public.json(), {**post, 'canEdit': False})
        self.assertEqual(self.client.get('/api/auth/works').json(), [])
