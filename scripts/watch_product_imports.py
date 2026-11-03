#!/usr/bin/env python3
"""Watch for new product catalog zips and import them.

Watches (in order):
  /workspace/incoming
  /workspace/uploads  (if present)
  /workspace          (only top-level *.zip matching product-ish names, to avoid noise)

Usage:
  cd /workspace/retail-crm && .venv/bin/python scripts/watch_product_imports.py
  # or one-shot:
  .venv/bin/python scripts/watch_product_imports.py --once
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

INCOMING = Path("/workspace/incoming")
UPLOADS = Path("/workspace/uploads")
WORKSPACE = Path("/workspace")
PROCESSED = INCOMING / "processed"
EXTRACTED = INCOMING / "extracted"
REPORTS = INCOMING / "reports"

log = logging.getLogger("watch_product_imports")


def candidate_zips() -> list[Path]:
    found: list[Path] = []
    for folder in (INCOMING, UPLOADS):
        if not folder.is_dir():
            continue
        for p in folder.glob("*.zip"):
            if p.is_file():
                found.append(p)
    # top-level /workspace only — avoid scanning huge trees / nested project zips
    if WORKSPACE.is_dir():
        for p in WORKSPACE.glob("*.zip"):
            name = p.name.lower()
            if any(k in name for k in ("product", "catalog", "abaya", "rabya", "rabiya", "inventory", "sku")):
                found.append(p)
    # de-dupe
    seen = set()
    out = []
    for p in found:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def process_zip(zip_path: Path) -> None:
    from app import create_app
    from app.services.product_import import import_from_path
    from app.services.top_sellers import export_top_sellers

    app = create_app()
    with app.app_context():
        log.info("Importing %s", zip_path)
        report = import_from_path(
            zip_path,
            static_root=Path(app.static_folder),
            extract_root=EXTRACTED,
            reports_dir=REPORTS,
            commit=True,
        )
        export_top_sellers(Path(app.config["EXPORTS_DIR"]))
        log.info(
            "Done %s: created=%s updated=%s errors=%s",
            zip_path.name,
            report.created,
            report.updated,
            report.errors,
        )
    PROCESSED.mkdir(parents=True, exist_ok=True)
    dest = PROCESSED / zip_path.name
    if dest.exists():
        dest = PROCESSED / f"{zip_path.stem}-{int(time.time())}{zip_path.suffix}"
    try:
        shutil.move(str(zip_path), str(dest))
        log.info("Moved to %s", dest)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not move %s: %s", zip_path, exc)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Scan once and exit")
    parser.add_argument("--interval", type=int, default=15, help="Poll seconds")
    args = parser.parse_args()

    INCOMING.mkdir(parents=True, exist_ok=True)
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)

    seen_mtime: dict[str, float] = {}

    def scan() -> None:
        for z in candidate_zips():
            key = str(z.resolve())
            try:
                mtime = z.stat().st_mtime
            except FileNotFoundError:
                continue
            # skip if unchanged since last process attempt in this process
            if seen_mtime.get(key) == mtime:
                continue
            # wait until file size stable (upload finishing)
            try:
                s1 = z.stat().st_size
                time.sleep(0.5)
                s2 = z.stat().st_size
                if s1 != s2:
                    continue
            except FileNotFoundError:
                continue
            seen_mtime[key] = mtime
            try:
                process_zip(z)
            except Exception:
                log.exception("Failed importing %s", z)

    if args.once:
        scan()
        return 0
    log.info("Watching for product zips every %ss", args.interval)
    while True:
        scan()
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
