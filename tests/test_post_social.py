"""댓글의 작성자·게시글 경계와 좋아요 중복·취소·연쇄 삭제를 검증한다."""
from concurrent.futures import ThreadPoolExecutor
import unittest
from fastapi.testclient import TestClient
import test_posts as fixtures
from app.main import app
from app.services import auth_store


class SocialTests(unittest.TestCase):
    setUp = fixtures.PostTests.setUp
    tearDown = fixtures.PostTests.tearDown
    login = fixtures.PostTests.login
    save = fixtures.PostTests.save
    create = fixtures.PostTests.create

    def post_path(self):
        _, post = self.create()
        return '/api/auth/posts/' + post['id']

    def comment(self, path, content='  좋은 작품이에요!  '):
        response = self.client.post(path + '/comments', headers=self.headers, json={'content': content})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['comment']

    def test_comment_public_read_edit_delete_and_counts(self):
        path = self.post_path()
        created = self.comment(path)
        self.assertEqual(created['content'], '좋은 작품이에요!')
        self.assertFalse(created['edited'])
        self.assertTrue(created['canEdit'])
        self.assertEqual(self.client.get('/api/auth/posts').json()['items'][0]['commentCount'], 1)
        with TestClient(app, base_url='http://localhost:9000') as guest:
            comments = guest.get(path + '/comments')
            self.assertEqual(comments.status_code, 200)
            self.assertEqual(comments.headers['cache-control'], 'no-store')
            self.assertEqual(comments.json()['total'], 1)
            public = comments.json()['items'][0]
            self.assertFalse(public['canEdit'])
            self.assertEqual(public['nickname'], 'first')
            for field in ('username', 'member_id', 'password', 'token_hash'):
                self.assertNotIn(field, public)
        target = path + '/comments/' + created['id']
        updated = self.client.patch(target, headers=self.headers, json={'content': '고친 댓글'})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['comment']['content'], '고친 댓글')
        self.assertTrue(updated.json()['comment']['edited'])
        self.assertEqual(updated.json()['comment']['createdAt'], created['createdAt'])
        self.assertEqual(self.client.delete(target, headers=self.headers).json(), {'commentCount': 0})
        self.assertEqual(self.client.delete(target, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get(path).json()['commentCount'], 0)

    def test_comment_only_author_can_manage_even_against_post_owner(self):
        path = self.post_path()
        with TestClient(app, base_url='http://localhost:9000') as other:
            self.login(other, 'second')
            response = other.post(path + '/comments', headers=self.headers, json={'content': '다른 회원 댓글'})
            self.assertEqual(response.status_code, 201)
            target = path + '/comments/' + response.json()['comment']['id']
            self.assertEqual(self.client.patch(target, headers=self.headers, json={'content': '탈취'}).status_code, 404)
            self.assertEqual(self.client.delete(target, headers=self.headers).status_code, 404)
            self.assertFalse(self.client.get(path + '/comments').json()['items'][0]['canEdit'])
            self.assertTrue(other.get(path + '/comments').json()['items'][0]['canEdit'])
            self.assertEqual(other.delete(target, headers=self.headers).status_code, 200)

    def test_comments_validate_empty_length_and_owner_injection(self):
        path = self.post_path()
        for payload in ({}, {'content': '   \n'}, {'content': '가'*1001}, {'content': '정상', 'member_id': 2}, {'content': None}):
            self.assertEqual(self.client.post(path + '/comments', headers=self.headers, json=payload).status_code, 422)
        for content in ('가', '가'*1000):
            created = self.comment(path, content)
            response = self.client.patch(path + '/comments/' + created['id'], headers=self.headers, json={'content': '  '})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(path).json()['commentCount'], 2)

    def test_comment_pagination_newest_first_and_reopen(self):
        path = self.post_path()
        comments = [self.comment(path, f'댓글 {i}') for i in range(21)]
        first = self.client.get(path + '/comments').json()
        self.assertEqual(len(first['items']), 20)
        self.assertTrue(first['hasMore'])
        self.assertEqual(first['items'][0]['id'], comments[-1]['id'])
        with TestClient(app, base_url='http://localhost:9000') as reopened:
            second = reopened.get(path + '/comments?offset=20&limit=20').json()
            self.assertEqual(second['items'][0]['id'], comments[0]['id'])
            self.assertFalse(second['hasMore'])
            self.assertEqual(second['total'], 21)
        self.assertEqual(self.client.get(path + '/comments?limit=21').status_code, 422)
        self.assertEqual(self.client.get(path + '/comments?offset=-1').status_code, 422)

    def test_comment_and_like_mutations_require_session_and_origin(self):
        path = self.post_path()
        target = path + '/comments/' + self.comment(path)['id']
        operations = [('post', path + '/comments', {'content': '새 댓글'}),
                      ('patch', target, {'content': '수정'}), ('delete', target, None),
                      ('put', path + '/like', None), ('delete', path + '/like', None)]
        with TestClient(app, base_url='http://localhost:9000') as guest:
            for method, url, payload in operations:
                kwargs = {'json': payload} if payload else {}
                self.assertEqual(getattr(guest, method)(url, headers=self.headers, **kwargs).status_code, 401)
                self.assertEqual(getattr(self.client, method)(url, **kwargs).status_code, 403)
                self.assertEqual(getattr(self.client, method)(url, headers={**self.headers, 'Origin':'https://other.example'}, **kwargs).status_code, 403)
        self.client.post('/api/auth/logout', headers=self.headers)
        self.assertEqual(self.client.put(path + '/like', headers=self.headers).status_code, 401)
        self.assertFalse(self.client.get(path).json()['likedByMe'])

    def test_like_is_idempotent_and_cancellation_does_not_remove_other_member(self):
        path = self.post_path()
        original = self.client.get(path).json()
        for _ in range(3):
            response = self.client.put(path + '/like', headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'likedByMe': True, 'likeCount': 1})
        self.assertEqual(self.client.get('/api/auth/posts').json()['items'][0]['likeCount'], 1)
        with TestClient(app, base_url='http://localhost:9000') as other:
            self.assertFalse(other.get(path).json()['likedByMe'])
            self.login(other, 'second')
            self.assertEqual(other.put(path + '/like', headers=self.headers).json()['likeCount'], 2)
            for _ in range(2):
                self.assertEqual(self.client.delete(path + '/like', headers=self.headers).json(), {'likedByMe':False, 'likeCount':1})
            self.assertTrue(other.get(path).json()['likedByMe'])
        final = self.client.get(path).json()
        self.assertEqual(final, {**original, 'likeCount': 1})

    def test_comment_post_boundary_and_missing_targets(self):
        first = self.post_path()
        second = self.post_path()
        comment = self.comment(first)
        wrong = second + '/comments/' + comment['id']
        self.assertEqual(self.client.patch(wrong, headers=self.headers, json={'content':'잘못된 글'}).status_code, 404)
        self.assertEqual(self.client.delete(wrong, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get(second + '/comments').json()['total'], 0)
        self.assertEqual(self.client.get('/api/auth/posts/missing/comments').status_code, 404)
        self.assertEqual(self.client.post('/api/auth/posts/missing/comments', headers=self.headers, json={'content':'댓글'}).status_code, 404)
        self.assertEqual(self.client.put('/api/auth/posts/missing/like', headers=self.headers).status_code, 404)
        self.assertEqual(self.client.delete('/api/auth/posts/missing/like', headers=self.headers).status_code, 404)

    def test_post_delete_cascades_comments_and_likes_only_for_that_post(self):
        first = self.post_path()
        second = self.post_path()
        for path in (first, second):
            self.comment(path)
            self.client.put(path + '/like', headers=self.headers)
        self.assertEqual(self.client.delete(first, headers=self.headers).status_code, 204)
        with auth_store.connection() as db:
            for table in ('post_comments','post_likes'):
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table} WHERE post_id = ?', (first.rsplit('/',1)[1],)).fetchone()[0], 0)
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 1)
        self.assertEqual(self.client.get(first + '/comments').status_code, 404)
        self.assertEqual(self.client.get(second).json()['likeCount'], 1)
        self.assertEqual(self.client.get(second).json()['commentCount'], 1)
        self.assertEqual(len(self.client.get('/api/auth/works').json()), 2)

    def test_existing_posts_survive_social_table_initialization(self):
        path = self.post_path()
        before = self.client.get(path).json()
        with auth_store.connection() as db:
            db.execute('DROP TABLE post_comments')
            db.execute('DROP TABLE post_likes')
        self.assertEqual(self.client.get(path).json(), before)
        self.assertEqual(self.client.get(path + '/comments').json()['total'], 0)

    def test_concurrent_like_requests_still_create_one_row(self):
        path = self.post_path()
        token = self.client.cookies.get('lda_session')
        def like(_):
            with TestClient(app, base_url='http://localhost:9000') as client:
                return client.put(path + '/like', headers={**self.headers, 'Cookie':f'lda_session={token}'})
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(like, range(8)))
        for response in responses:
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['likeCount'], 1)
        self.assertEqual(self.client.get(path).json()['likeCount'], 1)
