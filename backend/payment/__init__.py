"""Flask application factory.

The app used to be built at import time (`app = Flask(__name__)` as a module
global), which meant importing `payment` had side effects, the config could
only ever come from the environment, and tests/WSGI servers could not build
their own instance. `create_app()` replaces that.

Two things callers must know:

- **Working directory matters.** The views save uploads to CWD-relative paths
  (`static/cuisine/...`), so whatever runs this — gunicorn, manage.py, the
  test suite — must have `backend/` as its working directory.
- **APP_ENV defaults to 'pro'.** An unconfigured deployment gets DEBUG=False;
  you have to opt *into* the debugger, not out of it. Set APP_ENV=dev locally.
"""

import logging
import os
import secrets

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from .config import config_map


db = SQLAlchemy()

logger = logging.getLogger(__name__)


def _resolve_secret_key(app):
    """Auth tokens are signed with SECRET_KEY, so it must be a real secret.

    Under DEBUG a throwaway key is generated: tokens stop working across
    restarts, which is mildly annoying and entirely local. Anywhere else a
    missing key is fatal — falling back to a constant would mean anyone
    reading this repository could mint a token for any account, and the
    failure would be completely silent.
    """
    if app.config.get('SECRET_KEY'):
        return
    if app.config['DEBUG']:
        app.config['SECRET_KEY'] = secrets.token_urlsafe(32)
        logger.warning(
            'SECRET_KEY is unset; generated a throwaway one for this process. '
            'Auth tokens will not survive a restart. Set SECRET_KEY in .env.'
        )
        return
    raise RuntimeError(
        'SECRET_KEY is not set. It signs authentication tokens, so there is '
        'no safe default. Generate one with '
        '`python -c "import secrets; print(secrets.token_urlsafe(32))"` '
        'and put it in .env (or the container environment).'
    )


def create_app(env=None, config_overrides=None):
    """Build a configured app. `env` defaults to $APP_ENV, then 'pro'."""
    app = Flask(__name__)
    app.config.from_object(config_map[env or os.environ.get('APP_ENV', 'pro')])
    if config_overrides:
        app.config.update(config_overrides)

    _resolve_secret_key(app)
    db.init_app(app)

    # Imported here, not at module level: the view modules import `db` from
    # this module, so importing them any earlier would be circular.
    from .views import register_blueprints
    register_blueprints(app)

    # Both clients json.decode every response, so errors must be JSON too.
    from .errors import register_error_handlers
    register_error_handlers(app)

    # `flask --app manage init-db` builds the schema and seeds an admin.
    from .commands import register_commands
    register_commands(app)

    return app
