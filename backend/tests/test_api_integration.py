"""End-to-end API tests against a real MySQL.

Unlike the suite this replaces, these are **self-contained**: every fixture
(users, admins, dishes) is created by the test and torn down afterwards, so
there is no "u_id=1 must already exist" precondition and no rewriting of
data someone else cares about. That was ISSUES.md C1.

Still not a CI job, because it needs a live MySQL — window functions and
`EXTRACT` do not translate cleanly to SQLite, and DECIMAL degrades to float,
so the money assertions would be testing the wrong engine. Point it at a
throwaway database and run it by hand:

    cd backend
    set TEST_DATABASE_URL=mysql+pymysql://checkout:pw@127.0.0.1:3307/payment_test
    python -m unittest discover -s tests -t .

Without TEST_DATABASE_URL the whole module skips.

Recognition is stubbed out — these test the HTTP/DB layer. The recognizer
itself is covered by recognition/tests/.
"""

import os
import io
import json
import unittest
from decimal import Decimal
from unittest import mock

TEST_DATABASE_URL = os.environ.get('TEST_DATABASE_URL')


@unittest.skipUnless(TEST_DATABASE_URL, 'set TEST_DATABASE_URL to run')
class ApiTestCase(unittest.TestCase):
    """Builds an app on the test database and wipes its tables per test."""

    @classmethod
    def setUpClass(cls):
        from payment import create_app, db

        cls.db = db
        cls.app = create_app('pro', {'SQLALCHEMY_DATABASE_URI': TEST_DATABASE_URL,
                                     'SECRET_KEY': 'integration-test-key'})
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()

    @classmethod
    def tearDownClass(cls):
        cls.db.session.remove()
        cls.db.drop_all()
        cls.ctx.pop()

    def setUp(self):
        from payment.models import Admin, Cuisine, Possess, Record, User

        self.client = self.app.test_client()
        for model in (Record, Possess, Cuisine, User, Admin):
            model.query.delete()
        self.db.session.commit()

    # ---------------------------------------------------------- fixtures

    def make_user(self, name='alice', password='pw', money='100.00'):
        from werkzeug.security import generate_password_hash

        from payment.models import User

        row = User(
            u_name=name,
            u_password=generate_password_hash(password),
            u_money=Decimal(money),
        )
        self.db.session.add(row)
        self.db.session.commit()
        return row

    def make_admin(self, name='canteen', password='pw', store='一食堂'):
        from werkzeug.security import generate_password_hash

        from payment.models import Admin

        row = Admin(
            a_name=name,
            a_password=generate_password_hash(password),
            a_store_name=store,
            a_address='A 楼',
        )
        self.db.session.add(row)
        self.db.session.commit()
        return row

    def make_cuisine(self, name='番茄炒蛋', price='12.50'):
        from payment.models import Cuisine

        row = Cuisine(c_name=name, c_price=Decimal(price))
        self.db.session.add(row)
        self.db.session.commit()
        return row

    def login_user(self, name='alice', password='pw'):
        body = self.client.post(
            '/user/login', data={'u_name': name, 'u_password': password}
        ).get_json()
        return body['token']

    def login_admin(self, name='canteen', password='pw'):
        body = self.client.post(
            '/admin/login', data={'a_name': name, 'a_password': password}
        ).get_json()
        return body['token']

    @staticmethod
    def auth(token):
        return {'Authorization': f'Bearer {token}'}

    def review_fields(self, token, ids):
        draft = self.client.post('/admin/checkout/manual', headers=self.auth(token)).get_json()
        return {'review_token': draft['review_token'], 'tray_confirmed': 'true',
                'review': json.dumps([{'region_id': None, 'c_id': c_id,
                                      'quantity': 1, 'confirmed': True} for c_id in ids])}


class AuthFlowTest(ApiTestCase):
    def test_register_hashes_the_password(self):
        from payment.models import User

        body = self.client.post(
            '/user/register', data={'u_name': 'bob', 'u_password': 's3cret'}
        ).get_json()
        self.assertEqual(body['code'], 0)
        self.assertIn('token', body)
        stored = User.query.filter_by(u_name='bob').first().u_password
        self.assertNotEqual(stored, 's3cret')
        self.assertGreater(len(stored), 40)  # scrypt hashes are ~162 chars

    def test_register_missing_field_is_code_2_not_500(self):
        body = self.client.post('/user/register', data={'u_name': 'bob'}).get_json()
        self.assertEqual(body['code'], 2)

    def test_register_duplicate_name(self):
        self.make_user('alice')
        body = self.client.post(
            '/user/register', data={'u_name': 'alice', 'u_password': 'x'}
        ).get_json()
        self.assertEqual(body['code'], 1)

    def test_login_wrong_password_is_code_2(self):
        self.make_user('alice', 'pw')
        body = self.client.post(
            '/user/login', data={'u_name': 'alice', 'u_password': 'nope'}
        ).get_json()
        self.assertEqual(body['code'], 2)
        self.assertNotIn('token', body)

    def test_login_missing_password_does_not_crash(self):
        self.make_user('alice', 'pw')
        body = self.client.post('/user/login', data={'u_name': 'alice'}).get_json()
        self.assertEqual(body['code'], 2)

    def test_protected_endpoint_rejects_anonymous(self):
        user = self.make_user()
        response = self.client.get(f'/user/query/record/all/{user.u_id}/1')
        self.assertEqual(response.status_code, 401)


class AuthorizationTest(ApiTestCase):
    def test_user_cannot_recharge_another_user(self):
        alice = self.make_user('alice', money='10.00')
        self.make_user('mallory', money='0.00')
        token = self.login_user('mallory')
        response = self.client.post(
            '/user/recharge',
            data={'u_id': alice.u_id, 'recharge': '999'},
            headers=self.auth(token),
        )
        self.assertEqual(response.status_code, 403)
        self.db.session.refresh(alice)
        self.assertEqual(alice.u_money, Decimal('10.00'))

    def test_admin_may_recharge_any_user(self):
        alice = self.make_user('alice', money='10.00')
        self.make_admin()
        response = self.client.post(
            '/user/recharge',
            data={'u_id': alice.u_id, 'recharge': '25.50'},
            headers=self.auth(self.login_admin()),
        )
        self.assertEqual(response.get_json()['code'], 0)
        self.db.session.refresh(alice)
        self.assertEqual(alice.u_money, Decimal('35.50'))

    def test_customer_token_cannot_reach_admin_endpoints(self):
        self.make_user('alice')
        response = self.client.get(
            '/cuisine/query/all/1', headers=self.auth(self.login_user())
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_book_sales_against_another_canteen(self):
        alice = self.make_user('alice', money='100.00')
        other = self.make_admin('other', store='二食堂')
        self.make_admin('canteen')
        dish = self.make_cuisine()
        response = self.client.post(
            '/admin/purchase',
            data={
                'u_id': alice.u_id,
                'a_id': other.a_id,  # not the caller
                **self.review_fields(self.login_admin('canteen'), [dish.c_id]),
                'cuisines': f'[{dish.c_id}]',
                'total_price': '12.50',
            },
            headers=self.auth(self.login_admin('canteen')),
        )
        self.assertEqual(response.status_code, 403)
        self.db.session.refresh(alice)
        self.assertEqual(alice.u_money, Decimal('100.00'))


class PurchaseTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user('alice', money='100.00')
        self.admin = self.make_admin('canteen')
        self.dish = self.make_cuisine('番茄炒蛋', '12.50')
        self.token = self.login_admin('canteen')

    def _purchase(self, cuisines, total):
        ids = json.loads(cuisines) if cuisines.startswith('[') else [int(c) for c in cuisines.split(',')]
        return self.client.post(
            '/admin/purchase',
            data={
                'u_id': self.user.u_id,
                'a_id': self.admin.a_id,
                'cuisines': cuisines,
                **self.review_fields(self.token, ids),
                'total_price': total,
            },
            headers=self.auth(self.token),
        ).get_json()

    def test_two_portions_are_charged_twice(self):
        from payment.models import Record

        body = self._purchase(f'[{self.dish.c_id}, {self.dish.c_id}]', '25.00')
        self.assertEqual(body['code'], 0)
        self.assertEqual(Record.query.count(), 2)
        self.db.session.refresh(self.user)
        self.assertEqual(self.user.u_money, Decimal('75.00'))

    def test_review_can_include_two_different_dishes(self):
        from payment.models import Record

        second = self.make_cuisine('青椒肉丝', '14.00')
        body = self._purchase(f'{self.dish.c_id},{second.c_id}', '26.50')
        self.assertEqual(body['code'], 0)
        self.assertEqual(Record.query.count(), 2)

    def test_insufficient_balance_changes_nothing(self):
        from payment.models import Record

        self.user.u_money = Decimal('1.00')
        self.db.session.commit()
        body = self._purchase(f'[{self.dish.c_id}]', '12.50')
        self.assertEqual(body['code'], 1)
        self.assertEqual(Record.query.count(), 0)
        self.db.session.refresh(self.user)
        self.assertEqual(self.user.u_money, Decimal('1.00'))

    def test_unknown_user_is_code_2(self):
        body = self.client.post(
            '/admin/purchase',
            data={
                'u_id': 999999,
                **self.review_fields(self.token, [self.dish.c_id]),
                'a_id': self.admin.a_id,
                'cuisines': f'[{self.dish.c_id}]',
                'total_price': '12.50',
            },
            headers=self.auth(self.token),
        ).get_json()
        self.assertEqual(body['code'], 2)

    def test_deduction_and_records_are_one_transaction(self):
        # A failure while writing records must roll the deduction back too.
        from payment.models import Record

        with mock.patch(
            'payment.views.admin.Record', side_effect=RuntimeError('boom')
        ):
            body = self._purchase(f'[{self.dish.c_id}]', '12.50')
            self.assertEqual(body['code'], 500)
        self.db.session.refresh(self.user)
        self.assertEqual(self.user.u_money, Decimal('100.00'))
        self.assertEqual(Record.query.count(), 0)


class CuisineTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin('canteen')
        self.token = self.login_admin('canteen')

    def test_delete_refuses_a_dish_that_has_been_sold(self):
        # Cascading would destroy sales history and silently shrink the
        # takings reported by /admin/query/data/*. See ISSUES.md B6.
        from payment.models import Cuisine, Record

        user = self.make_user('alice')
        dish = self.make_cuisine()
        self.db.session.add(
            Record(u_id=user.u_id, c_id=dish.c_id, a_id=self.admin.a_id)
        )
        self.db.session.commit()

        body = self.client.post(
            '/cuisine/delete',
            data={'c_id': dish.c_id},
            headers=self.auth(self.token),
        ).get_json()
        self.assertEqual(body['code'], 2)
        self.assertIn('1', body['message'])
        self.assertIsNotNone(Cuisine.query.filter_by(c_id=dish.c_id).first())

    def test_delete_unsold_dish_succeeds(self):
        from payment.models import Cuisine

        dish = self.make_cuisine()
        with mock.patch('payment.views.cuisine.cuisine_detect') as detector:
            body = self.client.post(
                '/cuisine/delete',
                data={'c_id': dish.c_id},
                headers=self.auth(self.token),
            ).get_json()
        self.assertEqual(body['code'], 0)
        detector.delete.assert_called_once()
        self.assertIsNone(Cuisine.query.filter_by(c_id=dish.c_id).first())

    def test_delete_missing_dish_is_code_1_not_500(self):
        body = self.client.post(
            '/cuisine/delete', data={'c_id': 999999}, headers=self.auth(self.token)
        ).get_json()
        self.assertEqual(body['code'], 1)

    def test_modify_missing_dish_is_code_2_not_500(self):
        body = self.client.post(
            '/cuisine/modify',
            data={'c_id': 999999, 'c_name': 'x'},
            headers=self.auth(self.token),
        ).get_json()
        self.assertEqual(body['code'], 2)

    def test_modify_without_fields_is_a_no_op(self):
        dish = self.make_cuisine('番茄炒蛋', '12.50')
        body = self.client.post(
            '/cuisine/modify', data={'c_id': dish.c_id}, headers=self.auth(self.token)
        ).get_json()
        self.assertEqual(body['code'], 1)
        self.db.session.refresh(dish)
        self.assertEqual(dish.c_name, '番茄炒蛋')

    def test_price_column_holds_realistic_values(self):
        # DECIMAL(2,2) only spanned 0.00-0.99 and could not store a price.
        dish = self.make_cuisine('佛跳墙', '888.00')
        self.db.session.refresh(dish)
        self.assertEqual(dish.c_price, Decimal('888.00'))

    def test_add_rolls_back_when_enrollment_fails(self):
        # No orphan dish row may survive a failed enrollment.
        import io

        from payment.models import Cuisine

        with mock.patch('payment.views.cuisine.cuisine_detect') as detector:
            detector.store_many.side_effect = RuntimeError('unreadable image')
            body = self.client.post(
                '/cuisine/add',
                data={
                    'c_name': '新菜',
                    'c_price': '10.00',
                    'img': (io.BytesIO(b'not really a png'), 'a.png'),
                },
                headers=self.auth(self.token),
                content_type='multipart/form-data',
            ).get_json()
        self.assertEqual(body['code'], 3)
        self.assertIsNone(Cuisine.query.filter_by(c_name='新菜').first())

    def test_add_requires_an_image(self):
        body = self.client.post(
            '/cuisine/add',
            data={'c_name': '新菜', 'c_price': '10.00'},
            headers=self.auth(self.token),
        ).get_json()
        self.assertEqual(body['code'], 2)


class DetectTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.make_admin('canteen')
        self.token = self.login_admin('canteen')

    @staticmethod
    def image():
        from PIL import Image
        stream = io.BytesIO()
        Image.new('RGB', (100, 80), 'red').save(stream, 'PNG')
        stream.seek(0)
        return stream

    @staticmethod
    def result(ids):
        return {'image_width': 100, 'image_height': 80, 'matches': [
            {'box': [0, 0, 50, 80], 'dish_id': str(c_id) if c_id else None,
             'status': 'accepted' if c_id else 'unknown',
             'candidates': [{'dish_id': str(c_id), 'similarity': .9}] if c_id else []}
            for c_id in ids]}

    def test_duplicates_are_preserved_and_priced_twice(self):
        # The old /admin/detect collapsed these with IN (...) and undercharged.
        import io

        dish = self.make_cuisine('番茄炒蛋', '12.50')
        with mock.patch('payment.views.admin.cuisine_detect') as detector:
            detector.recognize.return_value = self.result([dish.c_id, dish.c_id])
            body = self.client.post(
                '/admin/detect',
                data={'img': (self.image(), 'tray.png')},
                headers=self.auth(self.token),
                content_type='multipart/form-data',
            ).get_json()
        self.assertEqual(body['code'], 0)
        self.assertEqual(len(body['regions']), 2)
        self.assertEqual([r['selected']['c_id'] for r in body['regions']], [dish.c_id, dish.c_id])

    def test_no_image_is_code_2(self):
        body = self.client.post(
            '/admin/detect', headers=self.auth(self.token)
        ).get_json()
        self.assertEqual(body['code'], 2)

    def test_unrecognized_tray_preserves_unknown_for_review(self):
        import io

        with mock.patch('payment.views.admin.cuisine_detect') as detector:
            detector.recognize.return_value = self.result([None])
            body = self.client.post(
                '/admin/detect',
                data={'img': (self.image(), 'tray.png')},
                headers=self.auth(self.token),
                content_type='multipart/form-data',
            ).get_json()
        self.assertEqual(body['code'], 0)
        self.assertEqual(body['regions'][0]['status'], 'unknown')

    def test_upload_is_deleted_even_when_recognition_raises(self):
        import glob
        import io

        before = set(glob.glob('static/*.png'))
        with mock.patch('payment.views.admin.cuisine_detect') as detector:
            detector.recognize.side_effect = RuntimeError('bad image')
            body = self.client.post(
                '/admin/detect',
                data={'img': (io.BytesIO(b'fake'), 'tray.png')},
                headers=self.auth(self.token),
                content_type='multipart/form-data',
            ).get_json()
        self.assertEqual(body['code'], 2)
        self.assertEqual(set(glob.glob('static/*.png')), before)


class ErrorHandlerTest(ApiTestCase):
    def test_404_is_json_not_html(self):
        # Both Flutter clients json.decode every response; an HTML error page
        # freezes the screen at the parse step.
        response = self.client.get('/no/such/route')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()['code'], 404)

    def test_405_is_json(self):
        response = self.client.get('/user/login')
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.get_json()['code'], 405)


class HealthTest(ApiTestCase):
    def test_healthz_is_public_and_reports_ok(self):
        body = self.client.get('/healthz').get_json()
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['database'], 'ok')

    def test_healthz_does_not_build_the_recognizer(self):
        # A liveness probe must never be the thing that loads ResNet50.
        body = self.client.get('/healthz').get_json()
        self.assertIn('loaded', body['recognizer'])

    def test_degraded_detector_is_a_warning_not_a_failure(self):
        with mock.patch('payment.views.health.legacy_api') as api:
            api.status.return_value = {
                'loaded': True,
                'detector': 'FullImageDetector',
                'dishes': 3,
                'vectors': 9,
            }
            response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any('multi-dish' in w for w in response.get_json()['warnings'])
        )


if __name__ == '__main__':
    unittest.main()
