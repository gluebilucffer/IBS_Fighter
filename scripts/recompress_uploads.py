#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ibs_fighter.config import UPLOADS_DIR
from ibs_fighter.uploads import recompress_uploads_directory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recompress existing meal photo uploads in place.")
    parser.add_argument(
        "--uploads-dir",
        type=Path,
        default=UPLOADS_DIR,
        help=f"Uploads directory to process. Default: {UPLOADS_DIR}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without rewriting files.",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Print per-file details instead of only the summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = recompress_uploads_directory(args.uploads_dir, dry_run=args.dry_run)
    output = result if args.details else {key: value for key, value in result.items() if key != "files"}
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
