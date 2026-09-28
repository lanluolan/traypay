import json
import logging
import os
import tempfile
import base64
import io
from datetime import datetime
from decimal import Decimal

from dish_recognition import legacy_api as cuisine_detect
from dish_recognition.recognizer import DetectorUnavailable, NoDishesDetected
from dish_recognition.embedder import load_image
from flask import Blueprint, jsonify, request
from sqlalchemy import and_, extract, func
from werkzeug.security import check_password_hash

from .. import db
from ..auth import ADMIN, acting_for_admin, forbidden, issue_token, require_auth
from ..models import Admin, Cuisine, Record, User
from ..checkout_review import issue_review, reviewed_cuisines
from ..utils import time

logger = logging.getLogger(__name__)

admin = Blueprint('admin', __name__)


@admin.route('/login', methods=['POST'])
def login():
    a_name = request.form.get('a_name')
    a_password = request.form.get('a_password')
    account = Admin.query.filter_by(a_name=a_name).first()
    res = {}
    if not account:
        res['code'] = 1
        res['message'] = 'admin does not exist'
    elif not a_password or not check_password_hash(account.a_password, a_password):
        # see user.login: guards against None, and legacy plaintext rows
        # simply fail the check rather than crashing
        res['code'] = 2
        res['message'] = 'wrong password'
    else:
        res['code'] = 0
        res['message'] = 'success'
        res['token'] = issue_token(ADMIN, account.a_id)
        res['admin'] = {
            'a_id': account.a_id,
            'a_name': account.a_name,
            'a_address': account.a_address,
            'a_store_name': account.a_store_name,
        }
    return jsonify(res)


@admin.route('/detect', methods=['POST'])
@require_auth(ADMIN)
def detect():
    img = request.files.get('img')
    if not img or not img.filename:
        return jsonify({'code': 2, 'message': 'no image uploaded'})
    fd, img_path = tempfile.mkstemp(suffix='.png')
    os.close(fd)
    try:
        img.save(img_path)
        result = cuisine_detect.recognize(img_path)
        preview = load_image(img_path)
        preview.thumbnail((1200, 1200))
        output = io.BytesIO()
        preview.save(output, format='JPEG')
        image_preview = base64.b64encode(output.getvalue()).decode('ascii')
    except DetectorUnavailable:
        return jsonify({'code': 3, 'message': '菜品检测器不可用，请人工录单或联系管理员'}), 503
    except NoDishesDetected:
        return jsonify({'code': 4, 'message': '未检测到菜品，请重拍或人工录单'})
    except Exception:
        # An unreadable upload is the common case, so the operator gets a
        # useful message instead of a 500 — but this also swallows genuine
        # server-side faults (ResNet50 weights failing to download on first
        # use, for one). Log before answering, or those become invisible and
        # get misread as a camera problem.
        logger.exception('recognition failed for %s', img_path)
        return jsonify({'code': 2, 'message': 'invalid image'})
    finally:
        # the file only exists to hand a path to the recognizer; never
        # keep it, or static/ grows without bound
        try:
            os.remove(img_path)
        except OSError:
            pass

    candidate_ids = {int(c['dish_id']) for m in result['matches']
                     for c in m['candidates'] if str(c['dish_id']).isdigit()}
    cuisines = {c.c_id: c for c in Cuisine.query.filter(Cuisine.c_id.in_(candidate_ids)).all()}
    regions = []
    for index, match in enumerate(result['matches']):
        candidates = []
        for candidate in match['candidates']:
            row = cuisines.get(int(candidate['dish_id'])) if str(candidate['dish_id']).isdigit() else None
            if row:
                candidates.append({'c_id': row.c_id, 'c_name': row.c_name,
                                   'c_price': row.c_price, 'similarity': candidate['similarity']})
        accepted_id = int(match['dish_id']) if str(match['dish_id']).isdigit() else None
        selected = next((c for c in candidates if c['c_id'] == accepted_id), None)
        regions.append({'region_id': index, 'box': match['box'],
                        'status': match['status'] if selected or match['status'] != 'accepted' else 'unknown',
                        'selected': selected, 'candidates': candidates})
    return jsonify({'code': 0, 'message': '请核对菜品和份数', 'regions': regions,
                    'image_preview': image_preview,
                    'image_width': result['image_width'], 'image_height': result['image_height'],
                    'review_token': issue_review(len(regions))})


@admin.route('/checkout/manual', methods=['POST'])
@require_auth(ADMIN)
def manual_checkout():
    return jsonify({'code': 0, 'review_token': issue_review(0)})


def _sales_subquery(*extra_filters):
    """Per-dish sold counts for one canteen, ranked for pagination.

    Grouping by Record.c_id is enough for MySQL's ONLY_FULL_GROUP_BY here:
    c_name and c_price are functionally dependent on the cuisine primary key
    the join is on. That is not true of the timestamp grouping in user.py.
    """
    return db.session.query(
        Cuisine.c_name,
        Cuisine.c_price,
        func.count(Record.c_id).label('count'),
        func.rank().over(order_by=Cuisine.c_id).label('rank'),
    ).join(
        Cuisine, Record.c_id == Cuisine.c_id
    ).filter(
        and_(*extra_filters)
    ).group_by(Record.c_id).subquery()


def _page_of_sales(sub_query, page):
    rows = db.session.query(
        sub_query.c.c_name, sub_query.c.c_price, sub_query.c.count
    ).filter(
        sub_query.c.rank > (page - 1) * 10
    ).limit(10).all()

    if not rows:
        return {'code': 1, 'message': 'no record'}
    return {
        'code': 0,
        'message': 'success',
        'cuisine': [{'c_name': r[0], 'count': r[2]} for r in rows],
        'total_price': sum(r[1] * r[2] for r in rows),
    }


@admin.route('/query/data/month/<int:a_id>/<date>/<int:page>', methods=['GET'])
@require_auth(ADMIN)
def query_month(a_id, date, page):
    if not acting_for_admin(a_id):
        return forbidden()
    year, month, _ = time.getDate(date)
    sub_query = _sales_subquery(
        Record.a_id == a_id,
        extract('year', Record.r_create_time) == year,
        extract('month', Record.r_create_time) == month,
    )
    return jsonify(_page_of_sales(sub_query, page))


@admin.route('/query/data/day/<int:a_id>/<date>/<int:page>', methods=['GET'])
@require_auth(ADMIN)
def query_day(a_id, date, page):
    if not acting_for_admin(a_id):
        return forbidden()
    year, month, day = time.getDate(date)
    sub_query = _sales_subquery(
        Record.a_id == a_id,
        extract('year', Record.r_create_time) == year,
        extract('month', Record.r_create_time) == month,
        extract('day', Record.r_create_time) == day,
    )
    return jsonify(_page_of_sales(sub_query, page))


@admin.route('/query/data/range/<int:a_id>/<start_date>/<end_date>/<int:page>')
@require_auth(ADMIN)
def query_from(a_id, start_date, end_date, page):
    if not acting_for_admin(a_id):
        return forbidden()
    sub_query = _sales_subquery(
        Record.a_id == a_id,
        Record.r_create_time > datetime.strptime(start_date, '%Y-%m-%d'),
        Record.r_create_time < datetime.strptime(end_date, '%Y-%m-%d'),
    )
    return jsonify(_page_of_sales(sub_query, page))


@admin.route('/purchase', methods=['POST'])
@require_auth(ADMIN)
def purchase():
    try:
        c_ids = reviewed_cuisines(
            request.form.get('review_token'), json.loads(request.form.get('review', 'null')),
            request.form.get('tray_confirmed') == 'true',
        )
    except (ValueError, TypeError) as exc:
        return jsonify({'code': 3, 'message': str(exc)}), 400
    u_id = request.form.get('u_id')
    a_id = request.form.get('a_id')
    # Books the sale against a_id's takings, so it must be the caller's own
    # canteen. Otherwise one store can bill customers into another's ledger.
    if not acting_for_admin(a_id):
        return forbidden()
    dishes = {c.c_id: c for c in Cuisine.query.filter(Cuisine.c_id.in_(set(c_ids))).all()}
    if set(dishes) != set(c_ids):
        return jsonify({'code': 3, 'message': '菜品已删除，请重新核对'}), 400
    total_price = sum((dishes[c_id].c_price for c_id in c_ids), Decimal('0'))
    if not total_price.is_finite() or any(dishes[c_id].c_price < 0 for c_id in c_ids):
        return jsonify({'code': 3, 'message': '菜品价格无效，请先修正价格'}), 400
    try:
        quoted = Decimal(request.form.get('total_price', ''))
        if not quoted.is_finite() or quoted != total_price:
            return jsonify({'code': 4, 'message': '菜价已变化，请重新选择菜品并核对金额'}), 409
    except Exception:
        return jsonify({'code': 3, 'message': '请核对金额'}), 400
    account = User.query.filter_by(u_id=u_id).with_for_update().first()
    res = {}
    if not account:
        res['code'] = 2
        res['message'] = 'user does not exist'
        return jsonify(res)

    if account.u_money < total_price:
        res['code'] = 1
        res['message'] = 'credit is running low'
    else:
        res['code'] = 0
        res['message'] = 'success'
        # Deduction and records commit as ONE transaction: a failure while
        # writing records must roll the deduction back too. The original
        # committed the deduction first, so a crash mid-loop took the money
        # and left no order behind it.
        account.u_money -= total_price
        date = datetime.now()
        for c_id in c_ids:
            db.session.add(
                Record(u_id=u_id, c_id=c_id, a_id=a_id, r_create_time=date)
            )
        db.session.commit()

    return jsonify(res)
