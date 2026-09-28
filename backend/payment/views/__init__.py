from .admin import admin
from .cuisine import cuisine
from .health import health
from .user import user


def register_blueprints(app):
    app.register_blueprint(user, url_prefix='/user')
    app.register_blueprint(admin, url_prefix='/admin')
    app.register_blueprint(cuisine, url_prefix='/cuisine')
    # no prefix: probes expect /healthz at the root
    app.register_blueprint(health)
