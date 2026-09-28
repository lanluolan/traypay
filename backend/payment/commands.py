"""Flask CLI commands.

    flask --app manage init-db

Registered from create_app(), so every entry point that builds the app gets
them — manage.py, gunicorn, the test suite. Run from the `backend/`
directory like everything else (the app reads .env relative to CWD).
"""

import secrets
import string

import click
from flask.cli import with_appcontext
from sqlalchemy import inspect
from werkzeug.security import generate_password_hash

from . import db
# Importing the models is what registers them on db.metadata; create_all()
# would otherwise find nothing to build.
from .models import Admin


def _random_password(length=16):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@click.command('init-db')
@click.option('--admin-name', default='admin', show_default=True,
              help='食堂端登录账号。')
@click.option('--admin-password', default=None,
              help='不指定则随机生成，并且只打印这一次。')
@click.option('--store-name', default='示例食堂', show_default=True,
              help='门店名，登录后显示在食堂端。')
@click.option('--address', default=None, help='门店地址，可留空。')
@with_appcontext
def init_db(admin_name, admin_password, store_name, address):
    """建表，并确保存在一个食堂端账号。

    可以重复执行：create_all() 只补建缺失的表，已存在的管理员不会被覆盖 ——
    尤其不会重置其密码。
    """
    db.create_all()
    tables = sorted(inspect(db.engine).get_table_names())
    click.echo(f'库中现有 {len(tables)} 张表: {", ".join(tables)}')

    existing = Admin.query.filter_by(a_name=admin_name).first()
    if existing:
        click.echo(f'管理员 {admin_name!r} 已存在 (a_id={existing.a_id})，未改动。')
        return

    generated = admin_password is None
    if generated:
        admin_password = _random_password()

    db.session.add(Admin(
        a_name=admin_name,
        a_password=generate_password_hash(admin_password),
        a_store_name=store_name,
        a_address=address,
    ))
    db.session.commit()

    click.echo(f'已创建管理员 {admin_name!r}（门店：{store_name}）。')
    if generated:
        # Printed once and never stored in plaintext anywhere. Losing it
        # means re-running with an explicit --admin-password under a new
        # name, or updating the row by hand.
        click.echo(f'  随机密码：{admin_password}')
        click.echo('  ^ 只显示这一次，立刻存到密码管理器里。')


def register_commands(app):
    app.cli.add_command(init_db)
