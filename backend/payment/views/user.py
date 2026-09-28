from datetime import datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request
from sqlalchemy import and_, func
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db
from ..auth import ADMIN, USER, acting_for_user, forbidden, issue_token, require_auth
from ..models import Admin, Cuisine, Record, User

user = Blueprint('user', __name__)


@user.route('/login', methods=['POST'])
def login():
    u_name = request.form.get('u_name')
    u_password = request.form.get('u_password')
    account = User.query.filter_by(u_name=u_name).first()
    res = {}
    if not account:
        res['code'] = 1
        res['message'] = 'user does not exist'
    elif not u_password or not check_password_hash(account.u_password, u_password):
        # `not u_password` guards check_password_hash against None, which
        # would raise instead of returning a plain "wrong password".
        # Rows still holding legacy plaintext simply fail the check.
        res['code'] = 2
        res['message'] = 'wrong password'
    else:
        res['code'] = 0
        res['message'] = 'success'
        # Additive: clients that ignore `token` keep working against the
        # unprotected endpoints (login/register), they just cannot reach
        # anything else.
        res['token'] = issue_token(USER, account.u_id)
        res['data'] = {
            'u_id': account.u_id,
            'u_name': account.u_name,
            'u_money': account.u_money,
        }
    return jsonify(res)


@user.route('/register', methods=['POST'])
def register():
    u_name = request.form.get('u_name')
    u_password = request.form.get('u_password')
    res = {}
    if not u_name or not u_password:
        # hashing None raises; a missing field must not become a 500
        res['code'] = 2
        res['message'] = 'u_name and u_password are required'
    elif User.query.filter_by(u_name=u_name).first():
        res['code'] = 1
        res['message'] = 'user already exists'
    else:
        account = User(u_name=u_name, u_password=generate_password_hash(u_password))
        db.session.add(account)
        db.session.commit()
        res['code'] = 0
        res['message'] = 'success'
        res['token'] = issue_token(USER, account.u_id)
        res['data'] = {
            'u_id': account.u_id,
            'u_name': account.u_name,
            'u_money': account.u_money,
        }
    return jsonify(res)


# Admin-only: destroys a customer account and their receipts, and neither app
# calls it. Nothing about it should be reachable with a customer's own token.
@user.route('/delete', methods=['POST'])
@require_auth(ADMIN)
def delete():
    u_name = request.form.get('u_name')
    account = User.query.filter_by(u_name=u_name).first()
    res = {}
    if not account:
        res['code'] = 1
        res['message'] = 'user do not exist'
    else:
        # Delete the user's records first. record.u_id is a foreign key, so
        # dropping the user while receipts still point at it raises
        # IntegrityError. (The original passed the whole list to
        # session.delete(), which crashed for any user that had records.)
        Record.query.filter_by(u_id=account.u_id).delete()
        db.session.delete(account)
        db.session.commit()
        res['code'] = 0
        res['message'] = 'success'
    return jsonify(res)


# Both apps call this: a customer tops up their own balance, and the canteen
# app tops up a customer's at the counter. Hence USER *or* ADMIN, with
# acting_for_user deciding whose balance may be touched.
@user.route('/recharge', methods=['POST'])
@require_auth(USER, ADMIN)
def recharge():
    u_id = request.form.get('u_id')
    amount = request.form.get('recharge')
    if not acting_for_user(u_id):
        return forbidden()
    account = User.query.filter_by(u_id=u_id).first()
    res = {}
    if not account:
        res['code'] = 1
        res['message'] = 'user does not exist'
    else:
        account.u_money = account.u_money + Decimal(amount)
        db.session.commit()
        res['code'] = 0
        res['message'] = 'success'
    return jsonify(res)


def _receipt_subquery(*extra_filters):
    """One row per purchase: timestamp, canteen, and the summed price.

    a_store_name / a_address must appear in GROUP BY: MySQL 8 enables
    ONLY_FULL_GROUP_BY by default and rejects selecting them otherwise
    (error 1055), which took these endpoints down with a 500. They are not
    functionally dependent on a timestamp, so the server cannot infer them
    the way it does for the c_id-keyed grouping in admin.py.

    Side effect, and a correct one: two purchases made in the same second at
    different canteens now list separately instead of being merged.
    """
    return db.session.query(
        Record.r_create_time,
        Admin.a_store_name,
        Admin.a_address,
        func.sum(Cuisine.c_price).label('total_price'),
        func.rank().over(order_by=Record.r_create_time.desc()).label('rank'),
    ).join(
        Cuisine, Cuisine.c_id == Record.c_id
    ).join(
        Admin, Admin.a_id == Record.a_id
    ).filter(
        and_(*extra_filters)
    ).group_by(
        Record.r_create_time, Admin.a_store_name, Admin.a_address
    ).subquery()


def _page_of_receipts(sub_query, page):
    rows = db.session.query(
        sub_query.c.r_create_time,
        sub_query.c.a_store_name,
        sub_query.c.a_address,
        sub_query.c.total_price,
    ).filter(
        sub_query.c.rank > (page - 1) * 10
    ).limit(10).all()

    if not rows:
        return {'code': 1, 'message': 'no record'}
    return {
        'code': 0,
        'message': 'success',
        'record': [
            {
                'r_create_time': datetime.strftime(r[0], '%Y-%m-%d %H:%M:%S'),
                'a_store_name': r[1],
                'a_address': r[2],
                'total_price': r[3],
            }
            for r in rows
        ],
    }


@user.route('/query/record/all/<int:u_id>/<int:page>', methods=['GET'])
@require_auth(USER, ADMIN)
def query_all(u_id, page):
    if not acting_for_user(u_id):
        return forbidden()
    sub_query = _receipt_subquery(Record.u_id == u_id)
    return jsonify(_page_of_receipts(sub_query, page))


@user.route('/query/record/detail/<int:u_id>/<date>', methods=['GET'])
@require_auth(USER, ADMIN)
def query_recordInfo(u_id, date):
    if not acting_for_user(u_id):
        return forbidden()
    rows = db.session.query(Cuisine.c_name, Cuisine.c_price).join(
        Record, Record.c_id == Cuisine.c_id
    ).filter(and_(
        Record.u_id == u_id,
        Record.r_create_time == datetime.strptime(date, '%Y-%m-%d %H:%M:%S'),
    )).all()

    res = {}
    if not rows:
        res['code'] = 1
        res['message'] = 'no record'
    else:
        res['code'] = 0
        res['message'] = 'success'
        res['cuisine'] = [{'c_name': r[0], 'c_price': r[1]} for r in rows]
        res['total_price'] = sum(r[1] for r in rows)
    return jsonify(res)


@user.route(
    '/query/record/range/<int:u_id>/<start_date>/<end_date>/<int:page>',
    methods=['GET'],
)
@require_auth(USER, ADMIN)
def query_record_by_time(u_id, start_date, end_date, page):
    if not acting_for_user(u_id):
        return forbidden()
    sub_query = _receipt_subquery(
        Record.u_id == u_id,
        Record.r_create_time >= datetime.strptime(start_date, '%Y-%m-%d'),
        Record.r_create_time <= datetime.strptime(end_date, '%Y-%m-%d'),
    )
    return jsonify(_page_of_receipts(sub_query, page))
