"""Authentication and authorization, tested without a real database.

These run anywhere: SQLite in memory, no MySQL, no seeded rows, no network.
They cover the part that is a security boundary rather than business logic —
who gets a 401, who gets a 403, and whose records an identity may touch.

    cd backend && python -m unittest discover -s tests -t .
"""

import unittest

from flask import Flask, g, jsonify

from payment.auth import (
    ADMIN,
    USER,
    acting_for_admin,
    acting_for_user,
    issue_token,
    require_auth,
)


def build_app(max_age=3600):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-key-not-a-real-secret'
    app.config['AUTH_TOKEN_MAX_AGE'] = max_age

    @app.route('/user-only')
    @require_auth(USER)
    def user_only():
        return jsonify({'kind': g.identity['kind'], 'id': g.identity['id']})

    @app.route('/admin-only')
    @require_auth(ADMIN)
    def admin_only():
        return jsonify({'ok': True})

    @app.route('/either')
    @require_auth(USER, ADMIN)
    def either():
        return jsonify({'kind': g.identity['kind']})

    return app


class RequireAuthTest(unittest.TestCase):
    def setUp(self):
        self.app = build_app()
        self.client = self.app.test_client()

    def _token(self, kind, ident):
        with self.app.test_request_context():
            return issue_token(kind, ident)

    def _get(self, path, token=None, raw_header=None):
        headers = {}
        if raw_header is not None:
            headers['Authorization'] = raw_header
        elif token is not None:
            headers['Authorization'] = f'Bearer {token}'
        return self.client.get(path, headers=headers)

    def test_no_header_is_401(self):
        response = self._get('/user-only')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()['code'], 401)

    def test_missing_bearer_prefix_is_401(self):
        token = self._token(USER, 1)
        self.assertEqual(self._get('/user-only', raw_header=token).status_code, 401)

    def test_garbage_token_is_401(self):
        self.assertEqual(self._get('/user-only', token='not-a-token').status_code, 401)

    def test_token_signed_with_another_key_is_401(self):
        other = build_app()
        other.config['SECRET_KEY'] = 'a-different-key'
        with other.test_request_context():
            foreign = issue_token(USER, 1)
        self.assertEqual(self._get('/user-only', token=foreign).status_code, 401)

    def test_expired_token_is_401(self):
        app = build_app(max_age=-1)  # already past its lifetime
        with app.test_request_context():
            token = issue_token(USER, 1)
        response = app.test_client().get(
            '/user-only', headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(response.status_code, 401)

    def test_valid_token_reaches_the_view(self):
        response = self._get('/user-only', token=self._token(USER, 7))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'kind': 'user', 'id': 7})

    def test_wrong_kind_is_403_not_401(self):
        # 401 means "log in again"; 403 means "logging in will not help".
        # Merging them would tell a customer to re-authenticate forever.
        response = self._get('/admin-only', token=self._token(USER, 7))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['code'], 403)

    def test_multi_kind_endpoint_accepts_both(self):
        for kind in (USER, ADMIN):
            response = self._get('/either', token=self._token(kind, 1))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()['kind'], kind)


class ActingForTest(unittest.TestCase):
    """A token says who you are; these say what you may touch."""

    def setUp(self):
        self.app = build_app()

    def _as(self, kind, ident):
        ctx = self.app.test_request_context()
        ctx.push()
        g.identity = {'kind': kind, 'id': ident}
        return ctx

    def test_user_may_act_on_themselves(self):
        ctx = self._as(USER, 7)
        self.assertTrue(acting_for_user(7))
        ctx.pop()

    def test_user_may_not_act_on_another_user(self):
        # The bug this whole module exists to close: without it any logged-in
        # customer could recharge or read anyone else's account.
        ctx = self._as(USER, 7)
        self.assertFalse(acting_for_user(8))
        ctx.pop()

    def test_id_comparison_is_type_insensitive(self):
        # u_id arrives as a string from request.form and as an int from the
        # URL converter; both must compare equal to the token's int.
        ctx = self._as(USER, 7)
        self.assertTrue(acting_for_user('7'))
        ctx.pop()

    def test_admin_may_act_on_any_user(self):
        # The canteen app tops up customers and shows their receipts.
        ctx = self._as(ADMIN, 1)
        self.assertTrue(acting_for_user(7))
        ctx.pop()

    def test_admin_may_act_only_as_themselves(self):
        ctx = self._as(ADMIN, 1)
        self.assertTrue(acting_for_admin(1))
        self.assertTrue(acting_for_admin('1'))
        self.assertFalse(acting_for_admin(2))
        ctx.pop()

    def test_user_is_never_an_admin(self):
        ctx = self._as(USER, 1)
        self.assertFalse(acting_for_admin(1))
        ctx.pop()


if __name__ == '__main__':
    unittest.main()
