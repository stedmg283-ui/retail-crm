"""Product catalog import from zip / directory (CSV, XLSX, JSON + photos)."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
import shutil
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from app.extensions import db
from app.models.product import Product

log = logging.getLogger(__name__)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DATA_EXTS = {".csv", ".xlsx", ".xls", ".json"}

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "sku": ("sku", "sku_code", "product_sku", "item_code", "code", "style_code"),
    "name": ("name", "product_name", "item_name", "title", "product", "item"),
    "fabric": ("fabric", "material", "cloth", "textile"),
    "unit_price": (
        "unit_price",
        "price",
        "mrp",
        "selling_price",
        "sale_price",
        "rate",
        "amount",
    ),
    "cost_price": ("cost_price", "cost", "purchase_price", "buy_price"),
    "size": ("size", "sizes", "size_chart"),
    "colors": ("colors", "color", "colour", "colours"),
    "stock_qty": ("stock_qty", "stock", "qty", "quantity", "inventory", "in_stock"),
    "category": ("category", "cat", "type", "collection"),
    "hsn": ("hsn", "hsn_code"),
    "gst_rate": ("gst_rate", "gst", "tax_rate"),
    "images": ("images", "image", "photo", "photos", "image_file", "filename", "file"),
    "is_active": ("is_active", "active", "status"),
}


@dataclass
class RowResult:
    row_num: int
    sku: str | None = None
    name: str | None = None
    action: str = "skip"  # created|updated|skip|error
    sku_generated: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_photo: bool = False
    missing_price: bool = False


@dataclass
class ImportReport:
    source: str
    started_at: str
    finished_at: str = ""
    rows_read: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    sku_generated_count: int = 0
    missing_photos: list[str] = field(default_factory=list)
    missing_prices: list[str] = field(default_factory=list)
    row_results: list[RowResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (h or "").strip().lower()).strip("_")


def map_headers(headers: Iterable[str]) -> dict[str, str]:
    """Map raw header -> canonical field name."""
    out: dict[str, str] = {}
    for raw in headers:
        key = _norm_header(raw)
        for canon, aliases in HEADER_ALIASES.items():
            if key in aliases or key == canon:
                out[raw] = canon
                break
    return out


def slugify(text: str, max_len: int = 24) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().upper()).strip("-")
    return (s or "ITEM")[:max_len]


def generate_sku(name: str, size: str | None = None) -> str:
    base = f"RC-{slugify(name)}"
    if size:
        base = f"{base}-{slugify(size, 8)}"
    return base[:40]


def _to_decimal(val: Any, default: Decimal | None = None) -> Decimal | None:
    if val is None or val == "":
        return default
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))
    text = str(val).strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "")
    text = re.sub(r"[^\d.\-]", "", text)
    if not text:
        return default
    try:
        return Decimal(text)
    except InvalidOperation:
        return default


def _to_bool(val: Any, default: bool = True) -> bool:
    if val is None or val == "":
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "y", "active", "in stock"):
        return True
    if s in ("0", "false", "no", "n", "inactive", "discontinued"):
        return False
    return default


def _split_multi(val: Any) -> list[str]:
    if val is None or val == "":
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    text = str(val).strip()
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except json.JSONDecodeError:
            pass
    for sep in ("|", ";", "/"):
        if sep in text:
            return [p.strip() for p in text.split(sep) if p.strip()]
    return [p.strip() for p in text.split(",") if p.strip()]


def _parse_sizes(val: Any) -> list[str | None]:
    parts = _split_multi(val)
    if not parts:
        return [None]
    return parts


def expand_row(mapped: dict[str, Any]) -> list[dict[str, Any]]:
    """One logical product row → one dict per size variant.

    Decision: if ``sizes`` lists multiple values, create one catalog row per size.
    SKU becomes ``{base}-{SIZE}`` when a base SKU is provided; otherwise
    ``RC-<slug>-<SIZE>``. Documented in ImportReport.notes.
    """
    sizes = _parse_sizes(mapped.get("size"))
    base_sku = (mapped.get("sku") or "").strip() or None
    out = []
    for sz in sizes:
        row = dict(mapped)
        row["size"] = sz
        if base_sku and sz and len(sizes) > 1:
            row["sku"] = f"{base_sku}-{slugify(sz, 8)}"[:40]
            row["_sku_from_variant"] = True
        elif base_sku:
            row["sku"] = base_sku[:40]
        else:
            row["sku"] = None
        out.append(row)
    return out


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    mapping = map_headers(reader.fieldnames)
    rows = []
    for r in reader:
        mapped: dict[str, Any] = {}
        for raw_h, canon in mapping.items():
            mapped[canon] = r.get(raw_h)
        if mapped:
            rows.append(mapped)
    return rows


def read_json_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if "products" in data:
            data = data["products"]
        elif "items" in data:
            data = data["items"]
        else:
            data = [data]
    if not isinstance(data, list):
        return []
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        mapping = map_headers(item.keys())
        mapped = {mapping[k]: item[k] for k in mapping}
        # also accept already-canonical keys
        for canon in HEADER_ALIASES:
            if canon in item and canon not in mapped:
                mapped[canon] = item[canon]
        if mapped:
            rows.append(mapped)
    return rows


def read_xlsx_rows(path: Path) -> list[dict[str, Any]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("openpyxl is required for XLSX import") from exc
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return []
    headers = [str(h) if h is not None else f"col{i}" for i, h in enumerate(header_row)]
    mapping = map_headers(headers)
    rows = []
    for values in rows_iter:
        raw = {headers[i]: values[i] if i < len(values) else None for i in range(len(headers))}
        mapped = {canon: raw[h] for h, canon in mapping.items()}
        if any(v not in (None, "") for v in mapped.values()):
            rows.append(mapped)
    return rows


def load_data_file(path: Path) -> list[dict[str, Any]]:
    ext = path.suffix.lower()
    if ext == ".csv":
        return read_csv_rows(path)
    if ext == ".json":
        return read_json_rows(path)
    if ext in (".xlsx", ".xls"):
        return read_xlsx_rows(path)
    return []


def index_images(root: Path) -> dict[str, list[Path]]:
    """Map stem / sku-ish keys → image paths under root."""
    index: dict[str, list[Path]] = {}
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
            continue
        stem = p.stem
        keys = {
            stem,
            stem.upper(),
            stem.lower(),
            re.sub(r"[^a-zA-Z0-9]+", "-", stem).upper(),
            re.sub(r"[^a-zA-Z0-9]+", "", stem).upper(),
        }
        # also parent folder name as key (photos/SKU123/1.jpg)
        if p.parent != root:
            keys.add(p.parent.name.upper())
            keys.add(re.sub(r"[^a-zA-Z0-9]+", "", p.parent.name).upper())
        for k in keys:
            if not k:
                continue
            index.setdefault(k, []).append(p)
    return index


def match_images(
    sku: str | None,
    name: str | None,
    explicit: list[str],
    image_index: dict[str, list[Path]],
    search_root: Path,
) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        key = str(p.resolve())
        if key not in seen and p.is_file():
            seen.add(key)
            found.append(p)

    for name_hint in explicit:
        hint = name_hint.strip()
        if not hint:
            continue
        direct = search_root / hint
        if direct.is_file():
            add(direct)
            continue
        # search by basename
        for p in search_root.rglob(Path(hint).name):
            if p.is_file():
                add(p)
        key = Path(hint).stem.upper()
        for p in image_index.get(key, []):
            add(p)

    if sku:
        sku_u = sku.upper()
        sku_compact = re.sub(r"[^A-Z0-9]+", "", sku_u)
        for key in (sku_u, sku_compact, sku):
            for p in image_index.get(key, []):
                add(p)
            for p in image_index.get(key.lower(), []):
                add(p)
        # prefix match
        for k, paths in image_index.items():
            if k.upper().startswith(sku_u) or sku_u.startswith(k.upper()):
                for p in paths:
                    add(p)

    if not found and name:
        slug = slugify(name)
        for p in image_index.get(slug, []):
            add(p)

    return found


def copy_product_images(sku: str, sources: list[Path], static_root: Path) -> list[str]:
    """Copy into app/static/products/<sku>/; return paths relative to static/."""
    dest_dir = static_root / "products" / sku
    dest_dir.mkdir(parents=True, exist_ok=True)
    rels: list[str] = []
    for i, src in enumerate(sources):
        safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", src.name)
        dest = dest_dir / safe_name
        if dest.exists() and dest.stat().st_size == src.stat().st_size:
            pass
        else:
            if dest.exists():
                dest = dest_dir / f"{i}_{safe_name}"
            shutil.copy2(src, dest)
        rels.append(f"products/{sku}/{dest.name}")
    return rels


def upsert_product(row: dict[str, Any], image_rels: list[str], result: RowResult) -> Product | None:
    name = (str(row.get("name") or "").strip())
    if not name:
        result.errors.append("missing name")
        result.action = "error"
        return None

    sku = (str(row.get("sku") or "").strip() or None)
    size = row.get("size")
    size_s = str(size).strip() if size not in (None, "") else None

    if not sku:
        sku = generate_sku(name, size_s)
        result.sku_generated = True
        result.warnings.append(f"generated SKU {sku}")

    result.sku = sku
    result.name = name

    price = _to_decimal(row.get("unit_price"), None)
    if price is None or price <= 0:
        result.missing_price = True
        result.errors.append("price missing or <= 0")
        result.action = "error"
        # still allow upsert if we want soft-fail? Task: validate every row must have price>0
        return None

    stock = _to_decimal(row.get("stock_qty"), Decimal("0")) or Decimal("0")
    # "in stock" as boolean-ish without qty → treat as 1
    if stock == 0 and isinstance(row.get("stock_qty"), str):
        if _to_bool(row.get("stock_qty"), False):
            stock = Decimal("1")

    colors = _split_multi(row.get("colors"))
    fabric = (str(row.get("fabric") or "").strip() or None)
    category = (str(row.get("category") or "").strip() or None)
    hsn = (str(row.get("hsn") or "").strip() or "6211")
    gst = _to_decimal(row.get("gst_rate"), Decimal("5")) or Decimal("5")
    cost = _to_decimal(row.get("cost_price"), None)
    active = _to_bool(row.get("is_active"), True)

    if not image_rels:
        result.missing_photo = True
        result.warnings.append("no photo matched")

    existing = Product.query.filter_by(sku=sku).first()
    if existing:
        product = existing
        result.action = "updated"
    else:
        product = Product(sku=sku)
        db.session.add(product)
        result.action = "created"

    product.name = name
    product.size = size_s
    product.fabric = fabric
    product.set_colors(colors)
    product.category = category
    product.hsn = hsn
    product.gst_rate = gst
    product.unit_price = price
    product.cost_price = cost
    product.stock_qty = stock
    product.is_active = active
    if image_rels:
        # merge with existing images
        merged = list(dict.fromkeys(product.images_list() + image_rels))
        product.set_images(merged)
    product.updated_at = datetime.utcnow()
    return product


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        # prevent path traversal
        for info in zf.infolist():
            target = (dest_dir / info.filename).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                raise ValueError(f"unsafe path in zip: {info.filename}")
        zf.extractall(dest_dir)
    return dest_dir


def find_data_files(root: Path) -> list[Path]:
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in DATA_EXTS:
            # skip macOS junk
            if "__MACOSX" in p.parts or p.name.startswith("."):
                continue
            files.append(p)
    return files



def _style_code_from_filename(name: str) -> str | None:
    """Extract supplier style code from names like '47653.jpg' or '47653 (2).jpg'."""
    stem = Path(name).stem
    base = re.sub(r"\s*\(\d+\)(\s*\(\d+\))?$", "", stem).strip()
    if re.fullmatch(r"\d{4,8}", base):
        return base
    return None


def collect_unique_photos(root: Path) -> list[dict[str, Any]]:
    """Deduplicate images by MD5; prefer numeric style-code filenames as SKU source.

    Returns list of dicts: sku_hint, name, paths (list[Path]), sku_generated.
    Never invents prices.
    """
    by_hash: dict[str, list[Path]] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
            continue
        if "__MACOSX" in p.parts or p.name.startswith("."):
            continue
        h = hashlib.md5(p.read_bytes()).hexdigest()
        by_hash.setdefault(h, []).append(p)

    items: list[dict[str, Any]] = []
    used_skus: set[str] = set()
    for h, paths in sorted(by_hash.items(), key=lambda kv: min(x.name for x in kv[1])):
        codes = []
        for path in paths:
            c = _style_code_from_filename(path.name)
            if c and c not in codes:
                codes.append(c)
        sku_generated = False
        if codes:
            # Prefer lowest numeric code when duplicates share content under multiple codes
            sku = sorted(codes, key=lambda x: int(x))[0]
            name = f"Abaya {sku}"
            if len(codes) > 1:
                alias_note = codes
            else:
                alias_note = []
        else:
            sku = f"RC-PHOTO-{h[:8].upper()}"
            sku_generated = True
            name = f"Abaya photo {h[:8]}"
            alias_note = []
        # ensure unique SKU within this batch
        base_sku = sku
        n = 2
        while sku in used_skus:
            sku = f"{base_sku}-{n}"[:40]
            n += 1
        used_skus.add(sku)
        items.append(
            {
                "sku": sku,
                "name": name,
                "paths": paths,
                "sku_generated": sku_generated,
                "alias_codes": alias_note,
                "content_hash": h,
            }
        )
    return items


def import_photo_catalog(
    work_dir: Path,
    static_root: Path,
    reports_dir: Path,
    report: ImportReport,
    commit: bool,
) -> ImportReport:
    """Import a photo-only catalog folder/zip (no CSV/XLSX/JSON).

    Creates inactive products with unit_price=0 when no price is present in the
    archive — prices are NEVER invented. Caller / staff must set prices later.
    Stock defaults to 0 (unknown) and is flagged.
    """
    report.notes.append(
        "Photo-only catalog mode: no CSV/XLSX/JSON found. "
        "Deduped images by MD5; numeric filenames used as SKUs; "
        "chat_camera_upload duplicates merged. Prices absent → unit_price=0, "
        "is_active=False (flagged missing_price). Stock default 0 (flagged)."
    )
    items = collect_unique_photos(work_dir)
    report.notes.append(f"unique photos after dedupe: {len(items)}")
    photos_matched = 0

    for i, item in enumerate(items, start=1):
        report.rows_read += 1
        result = RowResult(row_num=i, sku=item["sku"], name=item["name"])
        if item["sku_generated"]:
            result.sku_generated = True
            report.sku_generated_count += 1
            result.warnings.append(f"generated SKU {item['sku']} (no style code in filename)")
        if item["alias_codes"]:
            result.warnings.append(
                f"same image also named as style codes {item['alias_codes']}; kept SKU {item['sku']}"
            )

        image_rels = copy_product_images(item["sku"], item["paths"], static_root)
        photos_matched += len(image_rels)
        if not image_rels:
            result.missing_photo = True
            result.warnings.append("failed to copy photo")
            report.missing_photos.append(item["sku"])

        # Prices not in archive — do not invent; store inactive stub
        result.missing_price = True
        result.errors.append("price missing (photo-only catalog; not invented)")
        result.warnings.append("stock unknown; defaulted to 0")

        existing = Product.query.filter_by(sku=item["sku"]).first()
        if existing:
            product = existing
            result.action = "updated"
            report.updated += 1
        else:
            product = Product(sku=item["sku"])
            db.session.add(product)
            result.action = "created"
            report.created += 1

        product.name = item["name"]
        product.category = product.category or "Abaya"
        product.unit_price = Decimal("0")
        product.stock_qty = Decimal("0")
        product.is_active = False  # inactive until priced
        product.gst_rate = Decimal("5")
        product.hsn = product.hsn or "6211"
        if image_rels:
            merged = list(dict.fromkeys(product.images_list() + image_rels))
            product.set_images(merged)
        product.updated_at = datetime.utcnow()

        report.missing_prices.append(item["sku"])
        report.errors += 1  # validation: missing price
        report.row_results.append(result)

    report.notes.append(f"photo files copied into static: {photos_matched}")
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    report.finished_at = datetime.now(timezone.utc).isoformat()
    _write_reports(report, reports_dir)
    return report


def import_from_path(
    source: Path,
    *,
    static_root: Path | None = None,
    extract_root: Path | None = None,
    reports_dir: Path | None = None,
    commit: bool = True,
) -> ImportReport:
    """Import products from a zip file or an already-extracted directory."""
    started = datetime.now(timezone.utc)
    report = ImportReport(source=str(source), started_at=started.isoformat())
    report.notes.append(
        "Size policy: multiple sizes in one row expand to one Product per size "
        "(SKU = base-SIZE when base SKU given, else RC-<slug>-<SIZE>)."
    )

    from flask import current_app

    if static_root is None:
        static_root = Path(current_app.static_folder)
    if extract_root is None:
        extract_root = Path("/workspace/incoming/extracted")
    if reports_dir is None:
        reports_dir = Path("/workspace/incoming/reports")

    work_dir: Path
    if source.is_file() and source.suffix.lower() == ".zip":
        stamp = started.strftime("%Y%m%d-%H%M%S")
        work_dir = extract_root / f"{source.stem}-{stamp}"
        extract_zip(source, work_dir)
        report.notes.append(f"extracted zip to {work_dir}")
    elif source.is_dir():
        work_dir = source
    elif source.is_file() and source.suffix.lower() in DATA_EXTS:
        work_dir = source.parent
        data_files = [source]
        image_index = index_images(work_dir)
        return _run_import(
            data_files, work_dir, image_index, static_root, reports_dir, report, commit
        )
    else:
        report.notes.append(f"unsupported source: {source}")
        report.finished_at = datetime.now(timezone.utc).isoformat()
        _write_reports(report, reports_dir)
        return report

    data_files = find_data_files(work_dir)
    if not data_files:
        # Fall back to photo-only catalog (common for phone-captured abaya packs)
        image_count = sum(
            1
            for p in work_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS and "__MACOSX" not in p.parts
        )
        if image_count:
            report.notes.append(
                f"no CSV/XLSX/JSON found; {image_count} images present → photo-catalog import"
            )
            return import_photo_catalog(
                work_dir, static_root, reports_dir, report, commit
            )
        report.notes.append("no CSV/XLSX/JSON product files found and no images")
        report.finished_at = datetime.now(timezone.utc).isoformat()
        _write_reports(report, reports_dir)
        return report

    image_index = index_images(work_dir)
    return _run_import(
        data_files, work_dir, image_index, static_root, reports_dir, report, commit
    )


def _run_import(
    data_files: list[Path],
    work_dir: Path,
    image_index: dict[str, list[Path]],
    static_root: Path,
    reports_dir: Path,
    report: ImportReport,
    commit: bool,
) -> ImportReport:
    report.notes.append(f"data files: {[str(p.relative_to(work_dir)) for p in data_files]}")
    report.notes.append(f"indexed {sum(len(v) for v in image_index.values())} image path refs")

    for df in data_files:
        try:
            raw_rows = load_data_file(df)
        except Exception as exc:  # noqa: BLE001
            report.notes.append(f"failed reading {df.name}: {exc}")
            continue
        for i, mapped in enumerate(raw_rows, start=2):  # header is row 1
            for variant in expand_row(mapped):
                report.rows_read += 1
                result = RowResult(row_num=i, name=str(variant.get("name") or "") or None)
                explicit_imgs = _split_multi(variant.get("images"))
                sku_hint = variant.get("sku")
                paths = match_images(
                    str(sku_hint) if sku_hint else None,
                    str(variant.get("name") or "") or None,
                    explicit_imgs,
                    image_index,
                    work_dir,
                )
                image_rels: list[str] = []
                # need sku before copy — resolve tentatively
                tentative_sku = (str(sku_hint).strip() if sku_hint else None) or None
                if not tentative_sku and variant.get("name"):
                    tentative_sku = generate_sku(
                        str(variant["name"]),
                        str(variant["size"]) if variant.get("size") else None,
                    )
                if paths and tentative_sku:
                    image_rels = copy_product_images(tentative_sku, paths, static_root)

                product = upsert_product(variant, image_rels, result)
                if result.sku_generated:
                    report.sku_generated_count += 1
                if result.action == "error":
                    report.errors += 1
                    if result.missing_price and result.sku:
                        report.missing_prices.append(result.sku)
                    if result.missing_photo and result.sku:
                        report.missing_photos.append(result.sku)
                elif result.action == "created":
                    report.created += 1
                    if result.missing_photo and result.sku:
                        report.missing_photos.append(result.sku)
                elif result.action == "updated":
                    report.updated += 1
                    if result.missing_photo and result.sku:
                        report.missing_photos.append(result.sku)
                else:
                    report.skipped += 1
                report.row_results.append(result)
                _ = product  # hush linter

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    report.finished_at = datetime.now(timezone.utc).isoformat()
    _write_reports(report, reports_dir)
    return report


def _write_reports(report: ImportReport, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    md_path = reports_dir / f"import-{stamp}.md"
    json_path = reports_dir / f"import-{stamp}.json"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")

    lines = [
        f"# Product import report — {stamp}",
        "",
        f"- Source: `{report.source}`",
        f"- Started: {report.started_at}",
        f"- Finished: {report.finished_at}",
        f"- Rows read: **{report.rows_read}**",
        f"- Created: **{report.created}** · Updated: **{report.updated}** · "
        f"Errors: **{report.errors}** · Skipped: **{report.skipped}**",
        f"- SKUs auto-generated: **{report.sku_generated_count}**",
        "",
        "## Missing prices",
    ]
    if report.missing_prices:
        lines += [f"- `{s}`" for s in report.missing_prices]
    else:
        lines.append("- (none)")
    lines += ["", "## Missing photos"]
    if report.missing_photos:
        lines += [f"- `{s}`" for s in report.missing_photos]
    else:
        lines.append("- (none)")
    lines += ["", "## Notes"]
    for n in report.notes:
        lines.append(f"- {n}")
    lines += ["", "## Row details"]
    for r in report.row_results:
        flag = []
        if r.missing_price:
            flag.append("NO_PRICE")
        if r.missing_photo:
            flag.append("NO_PHOTO")
        if r.sku_generated:
            flag.append("SKU_GEN")
        flag_s = (" [" + ",".join(flag) + "]") if flag else ""
        err = ("; ".join(r.errors + r.warnings)) if (r.errors or r.warnings) else ""
        lines.append(
            f"- row {r.row_num}: {r.action} `{r.sku}` {r.name or ''}{flag_s}"
            + (f" — {err}" if err else "")
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report.notes.append(f"report written: {md_path}")
    # refresh json with final notes
    json_path.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    return md_path
