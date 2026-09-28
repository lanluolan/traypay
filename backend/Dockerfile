# Build from the REPOSITORY ROOT (the recognition package must be in context):
#   docker build -f backend/Dockerfile -t smart-checkout-backend .

FROM python:3.12-slim

WORKDIR /srv

COPY recognition/ recognition/
COPY backend/requirements.txt backend/requirements.txt

# CPU-only torch, installed FIRST and from PyTorch's own index. On Linux the
# default PyPI wheel is the CUDA build and drags in ~2 GB of nvidia-* runtime
# libraries that a CPU deployment never executes.
#
# It has to be a separate step: that index only serves torch packages, so
# using it for the whole install would fail to find Flask. Installing torch
# up front means the next command sees the requirement already satisfied and
# leaves this build in place.
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision

# [yolo] pulls ultralytics (AGPL-3.0). Without it the detector degrades to
# enrollment only; automatic tray recognition rejects the fallback detector.
#
# The opencv swap is required, not cosmetic. ultralytics depends on
# opencv-python, whose wheel links against desktop graphics libraries
# (libxcb, libGL) that python:*-slim does not ship. Importing ultralytics
# then fails with ImportError — which default_detector() treats as "the
# optional dep is absent" and silently degrades to whole-image recognition.
# The container stays available for manual checkout, but automatic recognition
# reports detector unavailability until this dependency problem is resolved.
#
# opencv-python-headless is the same library without the GUI backends, which
# is what a server wants anyway. pip will note that ultralytics' declared
# opencv-python requirement is unmet; both packages provide the same `cv2`
# module, so this is a metadata complaint, not a runtime one. Installing the
# GUI libs instead would add ~100 MB of X11 stack to a headless image.
RUN pip install --no-cache-dir -e "recognition[yolo]" -r backend/requirements.txt \
 && pip uninstall -y opencv-python \
 && pip install --no-cache-dir opencv-python-headless

# Bake the ResNet50 weights into the image. torchvision otherwise fetches
# ~100 MB into ~/.cache/torch on first use — which is not a mounted volume,
# so every container restart re-downloads it, the first /admin/detect blows
# past even the 120 s timeout, and the checkout host needs outbound internet
# it may not have. Warming through our own embedder guarantees the cached
# file is exactly the one the app loads.
RUN python -c "from dish_recognition.embedder import ResNet50Embedder; ResNet50Embedder('cpu')"

COPY backend/ backend/

# WORKDIR must stay backend/: the views save uploads to CWD-relative paths
# (static/cuisine/...), and gunicorn inherits this directory.
WORKDIR /srv/backend
# static/ is excluded via .dockerignore (runtime uploads); the app expects
# the directories to exist
RUN mkdir -p static/cuisine
EXPOSE 5000

# Serve with gunicorn, never `python manage.py` — that is Flask's development
# server, and with APP_ENV=dev it exposes the Werkzeug debugger (RCE).
#
#   --workers 1:   MUST stay 1, and this is not a performance knob. The feature
#                  store is an in-process singleton (dish_recognition.legacy_api)
#                  read from disk once when the recognizer is built. With 2+
#                  workers, a dish enrolled through /cuisine/add is written to
#                  disk but only lands in *that* worker's memory; the others
#                  keep serving a stale store and cannot recognize the new dish
#                  until they restart. Which worker answers a request is random,
#                  so the symptom is "enrollment works, then intermittently
#                  doesn't" — expensive to diagnose, easy to avoid.
#                  Scaling out requires a shared store (reload-on-mtime, or an
#                  external index), NOT more workers.
#   --threads 4:   gunicorn switches to gthread automatically. Gives the
#                  DB-bound endpoints (login, queries, purchase) concurrency so
#                  a ~1s /admin/detect does not block them. Recognition itself
#                  is serialized by a lock in legacy_api — the model and the
#                  store are shared mutable state.
#   --timeout 120: the first /admin/detect loads (and may download) ResNet50,
#                  which easily exceeds gunicorn's 30s default and would get
#                  the worker killed mid-request.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "120", "manage:app"]
