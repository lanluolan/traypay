"""JSON error handlers.

Both Flutter clients parse every response with json.decode. Flask's defaults
answer with HTML error pages, so any 404/405/500 crashes the app at the parse
step instead of showing a message — the user sees a frozen screen and the
real cause never reaches anyone.

Response shape matches the rest of the API (`code` + `message`), using the
HTTP status as `code`. Business codes are small integers where 0 means
success, so a three-digit code can never be mistaken for one.
"""

import logging

from flask import jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def _http_error(exc: HTTPException):
    # 404/405/413... — the client asked for something that does not exist or
    # is not allowed. Not worth a stack trace, but it should still be JSON.
    return jsonify({
        'code': exc.code,
        'message': exc.name.lower(),
    }), exc.code


def _unhandled_error(exc: Exception):
    from . import db
    db.session.rollback()
    logger.exception('unhandled exception')
    # Deliberately vague: the client is a checkout terminal, not an operator
    # console. Details go to the log, where they are actionable.
    return jsonify({
        'code': 500,
        'message': 'internal server error',
    }), 500


def register_error_handlers(app):
    app.register_error_handler(HTTPException, _http_error)

    # Registering a handler for Exception would otherwise bypass the Werkzeug
    # debugger, which is the entire point of running with APP_ENV=dev.
    if not app.debug:
        app.register_error_handler(Exception, _unhandled_error)
