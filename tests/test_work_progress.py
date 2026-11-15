import copy
import unittest
from fastapi.testclient import TestClient
import test_works as fixtures
from app.main import app
from app.services import auth_store


class WorkProgressTests(unittest.TestCase):
    setUp = fixtures.WorkTests.setUp
    tearDown = fixtures.WorkTests.tearDown
    login = fixtures.WorkTests.login
    save = fixtures.WorkTests.save

    def work(self):
        payload = copy.deepcopy(self.payload)
        payload['steps'] = [{**payload['steps'][0], 'id':f'step-{i}', 'index':i} for i in range(1,5)]
        work = self.save(payload).json()
        return '/api/auth/works/' + work['id']

    def test_default_progress_and_persistent_position_without_guide_changes(self):
        path = self.work()
        before = self.client.get(path).json()
        self.assertEqual(before['progress'], {'stepIndex':0,'savedAt':None})
        response = self.client.patch(path + '/progress', headers=self.headers, json={'stepIndex':3})
        self.assertEqual(response.status_code, 200, response.text)
        progress = response.json()
        self.assertEqual(progress['stepIndex'], 3)
        self.assertTrue(progress['savedAt'])
        self.assertEqual(response.headers['cache-control'], 'no-store')
        with TestClient(app, base_url='http://localhost:9000') as reopened:
            reopened.cookies.update(self.client.cookies)
            self.assertEqual(reopened.get(path).json(), {**before, 'progress':progress})

    def test_backward_navigation_and_start_over_save_latest_not_maximum(self):
        path = self.work()
        for step in (3, 2, 0):
            self.assertEqual(self.client.patch(path + '/progress', headers=self.headers, json={'stepIndex':step}).status_code, 200)
        self.assertEqual(self.client.get(path).json()['progress']['stepIndex'], 0)
        self.assertTrue(self.client.get(path).json()['progress']['savedAt'])
        with auth_store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_progress').fetchone()[0], 1)

    def test_invalid_step_type_range_and_owner_injection_do_not_overwrite(self):
        path = self.work()
        saved = self.client.patch(path + '/progress', headers=self.headers, json={'stepIndex':2}).json()
        for payload in ({}, {'stepIndex':-1}, {'stepIndex':4}, {'stepIndex':16384}, {'stepIndex':True}, {'stepIndex':1.5}, {'stepIndex':'1'}, {'stepIndex':None}, {'stepIndex':1,'member_id':2}):
            response = self.client.patch(path + '/progress', headers=self.headers, json=payload)
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get(path).json()['progress'], saved)

    def test_owner_session_and_missing_work(self):
        path = self.work()
        with TestClient(app, base_url='http://localhost:9000') as other:
            self.assertEqual(other.patch(path + '/progress', headers=self.headers, json={'stepIndex':1}).status_code, 401)
            self.login(other, 'second')
            self.assertEqual(other.patch(path + '/progress', headers=self.headers, json={'stepIndex':1}).status_code, 404)
        self.assertEqual(self.client.patch('/api/auth/works/missing/progress', headers=self.headers, json={'stepIndex':1}).status_code, 404)
        self.assertIsNone(self.client.get(path).json()['progress']['savedAt'])
        self.client.post('/api/auth/logout', headers=self.headers)
        self.assertEqual(self.client.patch(path + '/progress', headers=self.headers, json={'stepIndex':1}).status_code, 401)

    def test_request_origin_is_required(self):
        path = self.work()
        for headers in ({}, {**self.headers,'Origin':'https://other.example'}, {'Origin':self.headers['Origin']}):
            self.assertEqual(self.client.patch(path + '/progress', headers=headers, json={'stepIndex':1}).status_code, 403)
        self.assertIsNone(self.client.get(path).json()['progress']['savedAt'])

    def test_rename_preserves_progress_and_delete_cascades_only_own_work(self):
        first, second = self.work(), self.work()
        for path in (first,second):
            self.assertEqual(self.client.patch(path + '/progress', headers=self.headers, json={'stepIndex':2}).status_code, 200)
        before = self.client.get(first).json()['progress']
        self.assertEqual(self.client.patch(first, headers=self.headers, json={'title':'새 작품 이름'}).status_code, 200)
        self.assertEqual(self.client.get(first).json()['progress'], before)
        self.assertEqual(self.client.delete(first, headers=self.headers).status_code, 204)
        with auth_store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_progress').fetchone()[0],1)
        self.assertEqual(self.client.get(second).json()['progress']['stepIndex'],2)

    def test_legacy_work_and_public_snapshot_do_not_contain_private_progress(self):
        path = self.work()
        before = self.client.get(path).json()
        with auth_store.connection() as db:
            db.execute('DROP TABLE work_progress')
        self.assertEqual(self.client.get(path).json(),before)
        self.client.patch(path + '/progress',headers=self.headers,json={'stepIndex':2})
        response = self.client.post('/api/auth/posts',headers=self.headers,json={'workId':before['id'],'title':'공유','description':'설명'})
        self.assertEqual(response.status_code,201,response.text)
        self.assertNotIn('progress',response.json())
        self.assertNotIn('progress',response.json()['analysis'])
