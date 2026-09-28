"""Bearer-token authentication and authorization.

Login hands out a signed token; every protected endpoint requires it in an
`Authorization: Bearer <token>` header. Tokens are stateless (itsdangerous,
which ships with Flask — no extra dependency, no session table), so the only
way to revoke one early is to shorten AUTH_TOKEN_MAX_AGE or rotate
SECRET_KEY. That is an acceptable trade here: the alternative is a token
table plus a cleanup job for a two-app deployment.

**A token alone is not authorization.** Knowing who is calling does not say
whether they may touch the record they named. Every endpoint that takes a
`u_id` or `a_id` must also call `acting_for_user` / `acting_for_admin`,
otherwise any logged-in account can still operate on anyone else's money —
which is the actual bug this module exists to close.

Who may act on a user's record is not simply "themselves": the canteen app
tops up customer balances and inspects their receipts, so an authenticated
admin legitimately operates on other people's user records. See
`acting_for_user`.
"""

import functools

from flask import current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

USER = 'user'
ADMIN = 'admin'

# Namespaces the signature: a token minted for some other purpose with the
# same SECRET_KEY cannot be replayed as a login.
_SALT = 'checkout-auth'


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=_SALT)


def issue_token(kind: str, identity_id) -> str:
    """Mint a token for `kind` ('user' or 'admin') and a primary key."""
    return _serializer().dumps({'kind': kind, 'id': identity_id})


def _read_identity():
    """Decode the Authorization header, or None if absent/invalid/expired."""
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None
    try:
        payload = _serializer().loads(
            header[len('Bearer '):],
            max_age=current_app.config['AUTH_TOKEN_MAX_AGE'],
        )
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict) or payload.get('kind') not in (USER, ADMIN):
        return None
    return payload


def unauthorized():
    return jsonify({'code': 401, 'message': 'authentication required'}), 401


def forbidden():
    return jsonify({'code': 403, 'message': 'forbidden'}), 403


def require_auth(*kinds):
    """Reject callers without a valid token of one of `kinds`.

    401 means "no usable token"; 403 means "valid token, wrong kind" — a
    customer calling an admin endpoint. Keeping them distinct lets the app
    tell "log in again" apart from "you cannot do this".
    """
    def decorator(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            identity = _read_identity()
            if identity is None:
                return unauthorized()
            if identity['kind'] not in kinds:
                return forbidden()
            g.identity = identity
            return view(*args, **kwargs)
        return wrapper
    return decorator


def acting_for_user(u_id) -> bool:
    """May the caller operate on user `u_id`?

    True for the user themselves, and for any authenticated admin — the
    canteen app calls /user/recharge to top up a customer and
    /user/query/record/detail to show their receipt. Restricting this to
    "self only" would lock the admin app out of both.
    """
    identity = g.identity
    if identity['kind'] == ADMIN:
        return True
    return str(identity['id']) == str(u_id)


def acting_for_admin(a_id) -> bool:
    """May the caller act as canteen `a_id`? Only that admin themselves.

    Unlike users, there is no cross-admin case: one canteen has no business
    booking sales against another's account or reading its takings.
    """
    identity = g.identity
    return identity['kind'] == ADMIN and str(identity['id']) == str(a_id)
