"""App configuration, read from the environment (.env is loaded if present).

Never commit real credentials — copy .env.example to .env and fill it in.
"""

import os
from urllib.parse import quote

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional; plain env vars still work
    pass


def _database_uri():
    explicit = os.environ.get('DATABASE_URL')
    if explicit:
        return explicit
    # user/password are percent-encoded so credentials containing
    # @ : / # ? etc. don't break URI parsing. quote (not quote_plus):
    # SQLAlchemy decodes %20 as space but leaves '+' literal.
    user = quote(os.environ.get('DB_USER', 'checkout'), safe='')
    password = quote(os.environ.get('DB_PASSWORD', ''), safe='')
    host = os.environ.get('DB_HOST', '127.0.0.1')
    port = os.environ.get('DB_PORT', '3306')
    name = os.environ.get('DB_NAME', 'payment')
    return f'mysql+pymysql://{user}:{password}@{host}:{port}/{name}'


class Config:
    static_folder = 'static/'
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 24 * 1024 * 1024

    # Signs auth tokens. Deliberately has no fallback value: a shipped
    # default is a published key, and anyone holding it can mint a token for
    # any account. create_app() generates a throwaway one under DEBUG and
    # refuses to start without it otherwise.
    SECRET_KEY = os.environ.get('SECRET_KEY')

    # A checkout terminal stays logged in all day; a week keeps staff from
    # re-authenticating constantly without letting a leaked token live
    # forever. Tokens are stateless, so shortening this is the only
    # revocation mechanism there is short of rotating SECRET_KEY.
    AUTH_TOKEN_MAX_AGE = int(os.environ.get('AUTH_TOKEN_MAX_AGE', 7 * 24 * 3600))


class DevConfig(Config):
    DEBUG = True


class ProConfig(Config):
    DEBUG = False


config_map = {
    'dev': DevConfig,
    'pro': ProConfig,
}
