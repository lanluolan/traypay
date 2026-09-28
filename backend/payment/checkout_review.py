"""Signed, short-lived checkout drafts and explicit operator review."""
from flask import current_app, g
from itsdangerous import BadData, URLSafeTimedSerializer
import uuid


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='tray-review-v1')


def issue_review(region_count):
    return _serializer().dumps({'admin': str(g.identity['id']), 'regions': region_count,
                                'nonce': uuid.uuid4().hex})


def reviewed_cuisines(token, rows, tray_confirmed):
    if not isinstance(token, str) or not token:
        raise ValueError('请先识别托盘或新建人工录单')
    try:
        draft = _serializer().loads(token, max_age=900)
    except (BadData, TypeError):
        raise ValueError('识别结果已过期，请重新识别或新建人工录单')
    if draft.get('admin') != str(g.identity['id']):
        raise ValueError('结算单不属于当前收银员')
    if tray_confirmed is not True:
        raise ValueError('请核对整盘菜品和份数后确认')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError('请添加菜品并确认识别结果')
    seen, ids = set(), []
    for row in rows:
        if not isinstance(row, dict) or row.get('confirmed') is not True:
            raise ValueError('仍有未确认的菜品')
        region = row.get('region_id')
        if region is not None:
            if type(region) is not int or not 0 <= region < draft['regions'] or region in seen:
                raise ValueError('识别区域无效或重复')
            seen.add(region)
        c_id, quantity = row.get('c_id'), row.get('quantity')
        if c_id is None:  # Explicitly dismissed region (e.g. cutlery).
            if region is None or type(quantity) is not int or quantity != 0:
                raise ValueError('忽略区域的份数必须为零')
            continue
        if type(c_id) is not int or c_id <= 0 or type(quantity) is not int or not 1 <= quantity <= 99:
            raise ValueError('菜品或份数无效')
        ids.extend([c_id] * quantity)
    if seen != set(range(draft['regions'])):
        raise ValueError('请处理每一个识别区域')
    if not ids or len(ids) > 100:
        raise ValueError('每单菜品份数须为 1–100')
    return ids
