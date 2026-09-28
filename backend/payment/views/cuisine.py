import glob
import logging
import os
import base64
import io
from decimal import Decimal

from dish_recognition import legacy_api as cuisine_detect
from flask import Blueprint, jsonify, request, send_file

from .. import db
from ..auth import ADMIN, require_auth
from ..models import Cuisine, Record
from ..cuisine_samples import (append_samples, rebuild, remove_sample,
                               sample_lock, sample_path, sample_paths, serialize_samples)

logger = logging.getLogger(__name__)

cuisine = Blueprint('cuisine', __name__)


@cuisine.route('/query/all/<int:page>', methods=['GET'])
@require_auth(ADMIN)
def query_all(page):
    # 按行位置分页，不能按主键值：/cuisine/delete 会让 c_id 出现空洞，
    # 用 c_id >= (page-1)*10 会漏掉整段菜品。
    rows = Cuisine.query.order_by(Cuisine.c_id).offset((page - 1) * 10).limit(10).all()
    res = {'cuisine': []}
    if not rows:
        res['code'] = 1
        res['message'] = 'no cuisine'
    else:
        res['code'] = 0
        res['message'] = 'success'
        res['cuisine'] = [
            {'c_id': c.c_id, 'c_name': c.c_name, 'c_price': c.c_price}
            for c in rows
        ]
    return jsonify(res)


@cuisine.route('/modify', methods=['POST'])
@require_auth(ADMIN)
def modify():
    c_id = request.form.get('c_id')
    c_name = request.form.get('c_name')
    c_price = request.form.get('c_price')
    row = Cuisine.query.filter_by(c_id=c_id).first()
    if not row:
        return jsonify({'code': 2, 'message': 'cuisine does not exist'})

    changed = False
    if c_name:
        row.c_name = c_name
        changed = True
    if c_price:
        row.c_price = Decimal(c_price)
        changed = True
    if not changed:
        return jsonify({'code': 1, 'message': 'no modify'})

    db.session.commit()
    return jsonify({'code': 0, 'message': 'success'})


@cuisine.route('/add', methods=['POST'])
@require_auth(ADMIN)
@serialize_samples
def add():
    c_name = request.form.get('c_name')
    c_price = request.form.get('c_price')
    # Multi-view enrollment: several photos of the same dish from different
    # angles make retrieval much more robust. The old app sends one 'img';
    # getlist keeps that working while allowing more.
    imgs = [f for f in request.files.getlist('img') if f and f.filename]
    res = {}
    if Cuisine.query.filter_by(c_name=c_name).first():
        res['code'] = 1
        res['message'] = 'cuisine already exists'
        return jsonify(res)
    if not imgs or len(imgs) > 20:
        res['code'] = 2
        res['message'] = 'at least one image is required'
        return jsonify(res)

    if request.form.get('crops_confirmed') == 'true':
        try:
            price = Decimal(c_price or '')
            if (not c_name or len(c_name) > 20 or not price.is_finite()
                    or not 0 <= price <= Decimal('9999.99')
                    or price != price.quantize(Decimal('0.01'))):
                raise ValueError('invalid cuisine')
        except Exception:
            return jsonify({'code': 2, 'message': '请填写有效的菜名和价格'}), 400
        with sample_lock:
            row = Cuisine(c_name=c_name, c_price=price)
            db.session.add(row)
            db.session.flush()
            c_id = row.c_id
            try:
                report = append_samples(c_id, imgs)
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception('confirmed enrollment failed')
                # If SQL commit failed after feature persistence, compensate.
                try:
                    rebuild(c_id, [])
                    for path in sample_paths(c_id):
                        path.unlink(missing_ok=True)
                except Exception:
                    logger.exception('enrollment compensation failed')
                return jsonify({'code': 3, 'message': '样本保存失败，请重试'}), 500
        return jsonify({'code': 0, 'message': '添加成功', **_conflict_names(report)})

    row = Cuisine(c_name=c_name, c_price=c_price)
    db.session.add(row)
    db.session.flush()  # assigns c_id; nothing is visible until commit
    c_id = row.c_id
    img_paths = []
    try:
        for idx, img in enumerate(imgs):
            suffix = '' if idx == 0 else f'_{idx}'
            path = f'static/cuisine/{c_id}{suffix}.png'
            img.save(path)
            img_paths.append(path)
        report = cuisine_detect.store_many(img_paths, c_id)
    except Exception:
        # Atomic add: leave no orphan dish row, image files or feature
        # vectors behind when any step fails (e.g. an unreadable image).
        # Log first — 'image processing failed' alone gives the operator
        # nothing to act on, and hides server-side faults entirely.
        logger.exception('enrolling cuisine %s (%s) failed', c_id, c_name)
        db.session.rollback()
        for path in img_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            cuisine_detect.delete(f'static/cuisine/{c_id}.png')
        except Exception:
            pass
        return jsonify({'code': 3, 'message': 'image processing failed'})

    db.session.commit()
    res['code'] = 0
    res['message'] = 'success'
    # Existing dishes the new one is visually close to; surface them so
    # the operator can re-shoot with more distinctive angles/tableware.
    if report.get('conflicts'):
        res['conflicts'] = report['conflicts']
    return jsonify(res)


def _conflict_names(report):
    for conflict in report.get('conflicts', []):
        row = db.session.get(Cuisine, int(conflict['dish_id'])) if str(conflict['dish_id']).isdigit() else None
        conflict['c_name'] = row.c_name if row else str(conflict['dish_id'])
    return report


@cuisine.route('/samples/preview', methods=['POST'])
@require_auth(ADMIN)
def preview_sample():
    img = request.files.get('img')
    if not img:
        return jsonify({'code': 2, 'message': '请选择照片'}), 400
    try:
        original, crop = cuisine_detect.preview(img.stream)
        def encode(image):
            image.thumbnail((1600, 1600))
            output = io.BytesIO()
            image.save(output, format='PNG')
            return base64.b64encode(output.getvalue()).decode('ascii')
        return jsonify({'code': 0, 'original': encode(original), 'crop': encode(crop)})
    except Exception:
        logger.exception('sample preview failed')
        return jsonify({'code': 3, 'message': '照片无法处理，请重拍或检查识别服务'}), 422


@cuisine.route('/<int:c_id>/samples', methods=['GET', 'POST'])
@require_auth(ADMIN)
def samples(c_id):
    with sample_lock:
        if db.session.get(Cuisine, c_id) is None:
            return jsonify({'code': 2, 'message': '菜品不存在'}), 404
        if request.method == 'GET':
            return jsonify({'code': 0, 'samples': [
                {'id': p.name, 'confirmed_crop': '_sample_' in p.name,
                 'url': f'/cuisine/{c_id}/samples/{p.name}'} for p in sample_paths(c_id)]})
        imgs = [f for f in request.files.getlist('img') if f and f.filename]
        if not imgs or len(imgs) > 20 or request.form.get('crops_confirmed') != 'true':
            return jsonify({'code': 2, 'message': '请先确认 1–20 张照片的裁剪区域'}), 400
        try:
            report = append_samples(c_id, imgs)
            return jsonify({'code': 0, 'message': '样本已更新', **_conflict_names(report)})
        except Exception:
            logger.exception('sample append failed')
            return jsonify({'code': 3, 'message': '更新失败，原有样本仍保留'}), 500


@cuisine.route('/<int:c_id>/samples/<sample_id>', methods=['GET', 'DELETE'])
@require_auth(ADMIN)
def sample(c_id, sample_id):
    with sample_lock:
        if db.session.get(Cuisine, c_id) is None:
            return jsonify({'code': 2, 'message': '菜品不存在'}), 404
        path = sample_path(c_id, sample_id)
        if path is None:
            return jsonify({'code': 2, 'message': '样本不存在'}), 404
        if request.method == 'GET':
            return send_file(path, mimetype='image/png')
        try:
            report = remove_sample(c_id, sample_id)
            return jsonify({'code': 0, 'message': '样本已删除', **_conflict_names(report)})
        except ValueError as exc:
            return jsonify({'code': 2, 'message': str(exc)}), 400
        except Exception:
            logger.exception('sample deletion failed')
            return jsonify({'code': 3, 'message': '删除失败，原有样本仍保留'}), 500


@cuisine.route('/delete', methods=['POST'])
@require_auth(ADMIN)
@serialize_samples
def delete():
    c_id = request.form.get('c_id')
    row = Cuisine.query.filter_by(c_id=c_id).first()
    res = {}
    if not row:
        res['code'] = 1
        res['message'] = 'cuisine does not exist'
        return jsonify(res)

    sold = Record.query.filter_by(c_id=row.c_id).count()
    if sold:
        # record.c_id references cuisine, so deleting a dish that has ever
        # been sold used to raise IntegrityError and come back as a 500.
        #
        # Refusing is the conservative half of the fix. Cascading the delete
        # the way /user/delete does would destroy sales history and silently
        # shrink the takings in /admin/query/data/*, and that is not
        # reversible. Soft-delete (a c_active flag filtered out of listings)
        # is the real answer and needs a schema change — see ISSUES.md B6.
        res['code'] = 2
        res['message'] = f'cuisine has {sold} sales record(s) and cannot be deleted'
        return jsonify(res)

    db.session.delete(row)
    db.session.commit()
    cuisine_detect.delete(f'static/cuisine/{c_id}.png')
    for path in (glob.glob(f'static/cuisine/{c_id}.png')
                 + glob.glob(f'static/cuisine/{c_id}_*.png')):
        os.remove(path)
    res['code'] = 0
    res['message'] = 'success'
    return jsonify(res)
