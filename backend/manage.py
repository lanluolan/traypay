"""Local development entry point.

Run from the `backend/` directory (uploads use CWD-relative paths):

    APP_ENV=dev python manage.py

Production uses gunicorn against the module-level `app` below, never this
__main__ block — see Dockerfile:

    gunicorn --bind 0.0.0.0:5000 manage:app
"""

import os

from payment import create_app


app = create_app()

if __name__ == '__main__':
    app.run(
        host=os.environ.get('FLASK_RUN_HOST', '127.0.0.1'),
        port=int(os.environ.get('FLASK_RUN_PORT', '5000')),
    )
