"""Liveness/readiness endpoint for containers and load balancers.

Registered at the root, not under a blueprint prefix, so probes hit
`GET /healthz`.

Two rules this endpoint follows:

- **Cheap.** One `SELECT 1` and a read of already-resident state. It never
  builds the recognizer (see `legacy_api.status`), so probing a cold
  container does not trigger a ResNet50 load.
- **Only fail on what makes the service unable to answer.** A dead database
  is a 503 — every endpoint is broken, so the load balancer should pull this
  instance. A degraded detector is *not*: the service still serves, it just
  supports manual checkout and sample enrollment. Automatic tray recognition
  rejects a degraded detector. It is reported in `warnings` for monitoring.
"""

import logging

from dish_recognition import legacy_api
from flask import Blueprint, jsonify
from sqlalchemy import text

from .. import db

logger = logging.getLogger(__name__)

health = Blueprint('health', __name__)


@health.route('/healthz', methods=['GET'])
def healthz():
    warnings = []

    try:
        db.session.execute(text('SELECT 1'))
        database = 'ok'
    except Exception as exc:
        logger.exception('health check: database unreachable')
        database = f'{type(exc).__name__}: {exc}'

    recognizer = legacy_api.status()
    if recognizer.get('detector') == 'FullImageDetector':
        warnings.append(
            'multi-dish detector unavailable; automatic recognition is blocked, '
            'use manual checkout'
        )
    if recognizer.get('loaded') and not recognizer.get('vectors'):
        warnings.append('feature store is empty; no dish can be recognized')

    healthy = database == 'ok'
    return jsonify({
        'status': 'ok' if healthy else 'unhealthy',
        'database': database,
        'recognizer': recognizer,
        'warnings': warnings,
    }), (200 if healthy else 503)
