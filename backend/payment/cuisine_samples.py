"""Enrollment images and feature updates, serialized within the serving process."""
import logging
import re
import threading
import uuid
import functools
from pathlib import Path

from dish_recognition import legacy_api
from dish_recognition.embedder import load_image
from flask import current_app

sample_lock = threading.RLock()
logger = logging.getLogger(__name__)


def serialize_samples(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        with sample_lock:
            return view(*args, **kwargs)
    return wrapped


def image_dir():
    root = Path(current_app.config.get('CUISINE_IMAGE_DIR', 'static/cuisine')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def sample_paths(c_id):
    pattern = re.compile(rf'{int(c_id)}(?:_\d+|_sample_[0-9a-f]{{32}})?\.png')
    return sorted(p for p in image_dir().iterdir() if p.is_file() and pattern.fullmatch(p.name))


def sample_path(c_id, name):
    return next((p for p in sample_paths(c_id) if p.name == name), None)


def rebuild(c_id, paths):
    return legacy_api.replace_samples(c_id, [(p, '_sample_' in p.name) for p in paths])


def append_samples(c_id, uploads):
    """Uploads are operator-confirmed crops; never crop these a second time."""
    with sample_lock:
        old = sample_paths(c_id)
        added = []
        try:
            for upload in uploads:
                path = image_dir() / f'{int(c_id)}_sample_{uuid.uuid4().hex}.png'
                added.append(path)
                load_image(upload.stream).save(path, format='PNG')
            report = rebuild(c_id, old + added)
        except Exception:
            for path in added:
                path.unlink(missing_ok=True)
            raise
        return report


def remove_sample(c_id, name):
    with sample_lock:
        path = sample_path(c_id, name)
        if path is None:
            raise FileNotFoundError(name)
        paths = sample_paths(c_id)
        if len(paths) <= 1:
            raise ValueError('请先补拍正确照片，再删除最后一张样本')
        # Stage removal before updating vectors. Restore on any failure.
        staged = path.with_suffix('.removed')
        path.replace(staged)
        try:
            report = rebuild(c_id, [p for p in paths if p != path])
        except Exception:
            staged.replace(path)
            raise
        try:
            staged.unlink()
        except OSError:
            logger.warning('could not clean removed sample %s', staged)
        return report
