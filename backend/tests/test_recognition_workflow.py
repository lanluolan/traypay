"""Recognition/review/sample contracts on an isolated SQLite DB and fake ML.

These exercise workflow validation and persistence failure paths. MySQL
transaction/isolation behavior remains covered by the MySQL integration suite.
"""
import base64
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image
from flask import Flask, g
from dish_recognition import legacy_api
from dish_recognition.config import RecognizerConfig
from dish_recognition.detector import FullImageDetector
from dish_recognition.feature_store import FeatureStore
from dish_recognition.recognizer import DishRecognizer, DetectorUnavailable, NoDishesDetected

from payment import db
from payment.auth import ADMIN, USER, issue_token
from payment.models import Admin, Cuisine, Record, User
from payment.views import register_blueprints
from payment.cuisine_samples import sample_paths
from payment.checkout_review import issue_review


def png(color='red'):
    stream = io.BytesIO()
    Image.new('RGB', (100, 80), color).save(stream, 'PNG')
    stream.seek(0)
    return stream


class ColorEmbedder:
    dim = 3
    def embed_images(self, images):
        if not images:
            return np.zeros((0, 3), dtype=np.float32)
        return np.asarray([np.asarray(i).mean(axis=(0, 1)) for i in images], dtype=np.float32)


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='workflow-test', AUTH_TOKEN_MAX_AGE=3600,
                               SQLALCHEMY_DATABASE_URI='sqlite://',
                               CUISINE_IMAGE_DIR=str(self.root / 'images'))
        db.init_app(self.app)
        register_blueprints(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.admin = Admin(a_name='test', a_password='unused', a_store_name='test')
        self.user = User(u_name='test', u_password='unused', u_money=100)
        self.dish = Cuisine(c_name='番茄蛋', c_price=Decimal('12.50'))
        db.session.add_all([self.admin, self.user, self.dish])
        db.session.commit()
        self.headers = {'Authorization': 'Bearer ' + issue_token(ADMIN, self.admin.a_id)}
        self.client = self.app.test_client()
        self.rec = DishRecognizer(RecognizerConfig(store_dir=self.root / 'features'),
                                  detector=FullImageDetector(), embedder=ColorEmbedder())
        self.patcher = mock.patch.object(legacy_api, '_recognizer', self.rec)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()
        self.tmp.cleanup()

    def detect(self, result=None, error=None):
        with mock.patch('payment.views.admin.cuisine_detect.recognize', return_value=result, side_effect=error):
            return self.client.post('/admin/detect', headers=self.headers,
                                    data={'img': (png(), 'tray.png')})

    def result(self):
        return {'image_width': 100, 'image_height': 80, 'matches': [
            {'box': [0, 0, 40, 80], 'dish_id': str(self.dish.c_id), 'status': 'accepted',
             'candidates': [{'dish_id': str(self.dish.c_id), 'similarity': .9}]},
            {'box': [40, 0, 100, 80], 'dish_id': None, 'status': 'unknown', 'candidates': []},
        ]}

    def post_purchase(self, token, rows, confirmed=True, total='12.50'):
        return self.client.post('/admin/purchase', headers=self.headers, data={
            'u_id': self.user.u_id, 'a_id': self.admin.a_id, 'review_token': token,
            'review': json.dumps(rows), 'tray_confirmed': str(confirmed).lower(), 'total_price': total,
        })

    def row(self, region=0, **overrides):
        return {'region_id': region, 'c_id': self.dish.c_id, 'quantity': 1,
                'confirmed': True, **overrides}

    def test_detect_preserves_unknown_and_returns_oriented_preview(self):
        response = self.detect(self.result())
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(len(body['regions']), 2)
        self.assertEqual(body['regions'][1]['status'], 'unknown')
        self.assertIsNone(body['regions'][1]['selected'])
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(body['image_preview']))).size, (100, 80))

    def test_degraded_and_empty_detection_cannot_issue_review_token(self):
        for error, status, code in [(DetectorUnavailable(), 503, 3), (NoDishesDetected(), 200, 4)]:
            response = self.detect(error=error)
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.get_json()['code'], code)
            self.assertNotIn('review_token', response.get_json())

    def test_missing_or_unconfirmed_region_prevents_charge(self):
        token = self.detect(self.result()).get_json()['review_token']
        for rows in ([self.row()], [self.row(), self.row(1, confirmed=False)]):
            response = self.post_purchase(token, rows)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Record.query.count(), 0)

    def test_operator_can_resolve_unknown_as_second_portion(self):
        token = self.detect(self.result()).get_json()['review_token']
        response = self.post_purchase(token, [self.row(), self.row(1)], total='25.00')
        self.assertEqual(response.get_json()['code'], 0)
        self.assertEqual(Record.query.count(), 2)

    def test_explicit_ignore_preserves_region_accountability(self):
        token = self.detect(self.result()).get_json()['review_token']
        response = self.post_purchase(token, [self.row(), self.row(1, c_id=None, quantity=0)])
        self.assertEqual(response.get_json()['code'], 0)
        self.assertEqual(Record.query.count(), 1)

    def test_tray_confirmation_and_price_are_checked(self):
        token = self.client.post('/admin/checkout/manual', headers=self.headers).get_json()['review_token']
        self.assertEqual(self.post_purchase(token, [self.row(None)], confirmed=False).status_code, 400)
        self.assertEqual(self.post_purchase(token, [self.row(None)], total='0.01').status_code, 409)
        self.assertEqual(Record.query.count(), 0)

    def test_draft_cannot_be_used_by_another_admin(self):
        token = self.client.post('/admin/checkout/manual', headers=self.headers).get_json()['review_token']
        self.headers = {'Authorization': 'Bearer ' + issue_token(ADMIN, self.admin.a_id + 1)}
        self.assertEqual(self.post_purchase(token, [self.row(None)]).status_code, 400)

    def test_missing_tampered_and_expired_drafts_are_rejected(self):
        token = self.client.post('/admin/checkout/manual', headers=self.headers).get_json()['review_token']
        for bad in ('', 'tampered' + token):
            self.assertEqual(self.post_purchase(bad, [self.row(None)]).status_code, 400)
        with self.app.test_request_context():
            g.identity = {'kind': ADMIN, 'id': self.admin.a_id}
            with mock.patch('itsdangerous.timed.TimestampSigner.get_timestamp', return_value=1):
                expired = issue_review(0)
        self.assertEqual(self.post_purchase(expired, [self.row(None)]).status_code, 400)

    def test_duplicate_regions_and_invalid_quantities_are_rejected(self):
        token = self.detect(self.result()).get_json()['review_token']
        for rows in ([self.row(), self.row()],
                     [self.row(), self.row(1, quantity=-1)],
                     [self.row(), self.row(1, quantity=True)]):
            self.assertEqual(self.post_purchase(token, rows).status_code, 400)
        self.assertEqual(Record.query.count(), 0)

    def test_confirmed_new_dish_can_be_enrolled_without_changing_model(self):
        response = self.client.post('/cuisine/add', headers=self.headers, data={
            'c_name': '青菜', 'c_price': '8.00', 'crops_confirmed': 'true',
            'img': (png('green'), 'sample.png'),
        })
        self.assertEqual(response.get_json()['code'], 0)
        new = Cuisine.query.filter_by(c_name='青菜').one()
        self.assertEqual(len(sample_paths(new.c_id)), 1)
        self.assertEqual(self.rec.store.counts[str(new.c_id)], 1)

    def test_customer_cannot_preview_or_manage_samples(self):
        headers = {'Authorization': 'Bearer ' + issue_token(USER, self.user.u_id)}
        for method, url in [('post', '/cuisine/samples/preview'), ('get', f'/cuisine/{self.dish.c_id}/samples')]:
            self.assertEqual(getattr(self.client, method)(url, headers=headers).status_code, 403)

    def append(self, color='red'):
        return self.client.post(f'/cuisine/{self.dish.c_id}/samples', headers=self.headers,
                                data={'crops_confirmed': 'true', 'img': (png(color), 'sample.png')})

    def test_preview_does_not_mutate_feature_store(self):
        response = self.client.post('/cuisine/samples/preview', headers=self.headers,
                                    data={'img': (png(), 'sample.png')})
        self.assertEqual(response.get_json()['code'], 0)
        self.assertEqual(len(self.rec.store), 0)
        self.assertEqual(sample_paths(self.dish.c_id), [])

    def test_append_and_delete_rebuild_features_and_preserve_other_dishes(self):
        self.rec.store.add('999', [0, 1, 0])
        self.assertEqual(self.append().get_json()['code'], 0)
        self.assertEqual(self.append('blue').get_json()['code'], 0)
        samples = self.client.get(f'/cuisine/{self.dish.c_id}/samples', headers=self.headers).get_json()['samples']
        self.assertEqual(len(samples), 2)
        self.assertEqual(self.rec.store.counts[str(self.dish.c_id)], 2)
        self.assertIn('999', self.rec.store.dish_ids)
        image_response = self.client.get(samples[0]['url'], headers=self.headers)
        self.assertEqual(image_response.mimetype, 'image/png')
        image_response.close()
        response = self.client.delete(samples[0]['url'], headers=self.headers)
        self.assertEqual(response.get_json()['code'], 0)
        self.assertEqual(self.rec.store.counts[str(self.dish.c_id)], 1)
        self.assertEqual(len(sample_paths(self.dish.c_id)), 1)
        self.assertEqual(self.client.delete(samples[1]['url'], headers=self.headers).status_code, 400)

    def test_failed_append_keeps_old_images_and_live_and_saved_vectors(self):
        self.append()
        before = sample_paths(self.dish.c_id)
        with self.assertLogs('payment.views.cuisine', level='ERROR'), mock.patch.object(FeatureStore, 'save', side_effect=OSError('disk full')):
            self.assertEqual(self.append('blue').status_code, 500)
        self.assertEqual(sample_paths(self.dish.c_id), before)
        self.assertEqual(self.rec.store.counts[str(self.dish.c_id)], 1)
        self.assertEqual(FeatureStore.load(self.root / 'features').counts[str(self.dish.c_id)], 1)

    def test_failed_delete_restores_original_sample(self):
        self.append()
        self.append('blue')
        before = sample_paths(self.dish.c_id)
        with self.assertLogs('payment.views.cuisine', level='ERROR'), mock.patch.object(FeatureStore, 'save', side_effect=OSError('disk full')):
            response = self.client.delete(f'/cuisine/{self.dish.c_id}/samples/{before[0].name}', headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(sample_paths(self.dish.c_id), before)
        self.assertEqual(self.rec.store.counts[str(self.dish.c_id)], 2)

    def test_sample_route_cannot_delete_another_dish_image(self):
        self.append()
        name = sample_paths(self.dish.c_id)[0].name
        self.assertEqual(self.client.delete(f'/cuisine/999/samples/{name}', headers=self.headers).status_code, 404)


if __name__ == '__main__':
    unittest.main()
