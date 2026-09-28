"""Command-line interface for enrolling and recognizing dishes.

Examples (run from recognition/):
    python -m dish_recognition enroll --id 3 photos/tomato_egg_*.jpg
    python -m dish_recognition recognize photos/tray.jpg
    python -m dish_recognition list
    python -m dish_recognition remove --id 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import RecognizerConfig
from .recognizer import DishRecognizer


def _build_recognizer(args: argparse.Namespace) -> DishRecognizer:
    config = RecognizerConfig(store_dir=Path(args.store))
    if args.no_detector:
        config.detector_weights = None
    elif args.weights:
        config.detector_weights = args.weights
    if args.accept_threshold is not None:
        config.accept_threshold = args.accept_threshold
    if args.ambiguity_margin is not None:
        config.ambiguity_margin = args.ambiguity_margin
    config.__post_init__()
    return DishRecognizer(config)


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="dish_recognition", description="Dish enrollment & recognition"
    )
    parser.add_argument(
        "--store",
        default="dish_feature_store",
        help="feature store directory (default: ./dish_feature_store)",
    )
    parser.add_argument(
        "--weights", default=None, help="YOLO detector weights path/name"
    )
    parser.add_argument(
        "--no-detector",
        action="store_true",
        help="use whole-image enrollment (checkout recognition requires a detector)",
    )
    parser.add_argument(
        "--accept-threshold", type=float, default=None, help="match cutoff"
    )
    parser.add_argument('--ambiguity-margin', type=float, default=None,
                        help='minimum score gap between top two candidates')
    sub = parser.add_subparsers(dest="command", required=True)

    p_enroll = sub.add_parser("enroll", help="register a dish from photos")
    p_enroll.add_argument("--id", required=True, help="dish id (c_id)")
    p_enroll.add_argument("images", nargs="+", help="one or more photos")
    p_enroll.add_argument(
        "--replace",
        action="store_true",
        help="drop the dish's existing vectors first",
    )
    p_enroll.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when similarity conflicts are found",
    )

    p_rec = sub.add_parser("recognize", help="recognize dishes in a photo")
    p_rec.add_argument("image")

    sub.add_parser("list", help="show enrolled dishes and vector counts")

    p_rm = sub.add_parser("remove", help="delete a dish from the store")
    p_rm.add_argument("--id", required=True)

    args = parser.parse_args(argv)
    recognizer = _build_recognizer(args)

    if args.command == "enroll":
        report = recognizer.enroll(args.id, args.images, replace=args.replace)
        _print(report.to_dict())
        if report.conflicts:
            print(
                "WARNING: hard to distinguish from existing dish(es) above — "
                "add more distinctive photos or use distinctive tableware.",
                file=sys.stderr,
            )
            if args.strict:
                return 2
        return 0

    if args.command == "recognize":
        from .recognizer import DetectorUnavailable, NoDishesDetected
        try:
            _print(recognizer.recognize(args.image).to_dict())
        except (DetectorUnavailable, NoDishesDetected) as exc:
            _print({'error': str(exc), 'requires_manual_entry': True})
            return 3
        return 0

    if args.command == "list":
        _print(
            {
                "store": str(recognizer.config.store_dir),
                "total_vectors": len(recognizer.store),
                "dishes": recognizer.store.counts,
            }
        )
        return 0

    if args.command == "remove":
        removed = recognizer.remove(args.id)
        _print({"dish_id": str(args.id), "vectors_removed": removed})
        return 0 if removed else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
