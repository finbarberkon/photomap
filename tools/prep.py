#!/usr/bin/env python3
"""Build web-sized photo copies and photos.json.

Usage:
    python tools/prep.py [--force] [--prune] [--dry-run] [--allow-empty]

Photos are read from photos/source/ (any nesting depth, originals ignored by
git). Served copies are written to photos/web/ and the map index to
photos.json. Photos without GPS are listed in photos/skipped.txt.

Hand-edited "title" values in photos.json survive re-runs; delete the value
(or the whole entry) to fall back to the folder name.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageCms, ImageOps
except ImportError:
    sys.exit(
        "Pillow is not installed.\n"
        "Run `make setup` (or `pip install -r tools/requirements.txt`) first."
    )

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:  # pragma: no cover - optional dependency
    HEIF_SUPPORT = False


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "photos" / "source"
WEB_DIR = ROOT / "photos" / "web"
MANIFEST = ROOT / "photos.json"
SKIPPED_FILE = ROOT / "photos" / "skipped.txt"

IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".heif",
    ".tif",
    ".tiff",
    ".webp",
}

MAX_EDGE = 1600
JPEG_QUALITY = 80
MTIME_SLACK = 1e-6


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or "photo"


def to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(value.numerator) / float(value.denominator)
        except (AttributeError, ValueError, ZeroDivisionError):
            return None


def dms_to_degrees(value, ref) -> float | None:
    if not value or len(value) != 3:
        return None
    parts = [to_float(part) for part in value]
    if any(part is None for part in parts):
        return None
    degrees = parts[0] + parts[1] / 60.0 + parts[2] / 3600.0
    if isinstance(ref, str) and ref.strip().upper() in ("S", "W"):
        degrees = -degrees
    return round(degrees, 6)


def read_metadata(path: Path) -> dict:
    """Return {"lat", "lon", "date"} for an image. Raises if unreadable."""
    with Image.open(path) as image:
        exif = image.getexif()
        gps = {}
        if exif:
            try:
                gps = exif.get_ifd(0x8825) or {}
            except Exception:
                gps = {}

        lat = dms_to_degrees(gps.get(2), gps.get(1))
        lon = dms_to_degrees(gps.get(4), gps.get(3))
        if lat == 0 and lon == 0:
            lat = lon = None

        raw_date = None
        try:
            exif_ifd = exif.get_ifd(0x8769) if exif else {}
            raw_date = exif_ifd.get(36867) or exif_ifd.get(36868)
        except Exception:
            raw_date = None
        if not raw_date and exif:
            raw_date = exif.get(306)

    date = None
    if raw_date:
        try:
            date = datetime.strptime(str(raw_date).strip()[:19], "%Y:%m:%d %H:%M:%S")
            date = date.date().isoformat()
        except ValueError:
            date = None

    return {"lat": lat, "lon": lon, "date": date}


def derived_title(path: Path) -> str:
    """Use the nearest parent folder inside photos/source as a title."""
    try:
        folder = path.parent.relative_to(SOURCE_DIR)
    except ValueError:
        return ""
    if str(folder) in ("", "."):
        return ""
    name = folder.parts[-1]
    return name.replace("_", " ").replace("-", " ").strip()


def write_image(source: Path, destination: Path) -> tuple[int, int]:
    with Image.open(source) as opened:
        opened.seek(0)
        icc = opened.info.get("icc_profile")
        image = ImageOps.exif_transpose(opened)

        if image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        ):
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Downscale first: the colour conversion below is per-pixel, so doing it
        # on the small image is much faster across a large library.
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

        # Wide-gamut phone photos (Display P3) look oversaturated when a
        # browser assumes sRGB, so convert to sRGB when a profile is present.
        if icc:
            try:
                source_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
                description = (source_profile.profile.profile_description or "").lower()
                if "srgb" in description:
                    icc = None
                else:
                    image = ImageCms.profileToProfile(
                        image,
                        source_profile,
                        ImageCms.createProfile("sRGB"),
                        outputMode="RGB",
                    )
                    icc = None
            except Exception:
                pass  # unreadable profile: keep the pixels and embed the original

        destination.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs = {
            "format": "JPEG",
            "quality": JPEG_QUALITY,
            "optimize": True,
            "progressive": True,
        }
        if icc:
            save_kwargs["icc_profile"] = icc
        image.save(destination, **save_kwargs)
        return image.size


def load_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"photos.json is not valid JSON: {exc}")
    return data if isinstance(data, list) else []


def collect_sources() -> list[Path]:
    if not SOURCE_DIR.exists():
        return []
    files = [
        path
        for path in SOURCE_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and not path.name.startswith(".")
    ]
    return sorted(files, key=lambda path: path.relative_to(SOURCE_DIR).as_posix())


def dump_manifest(entries: list[dict]) -> str:
    if not entries:
        return "[]\n"
    lines = [json.dumps(entry, ensure_ascii=False, sort_keys=True) for entry in entries]
    return "[\n  " + ",\n  ".join(lines) + "\n]\n"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-encode every photo, even if the web copy is current",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="delete web copies and entries whose source photo was removed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen without writing anything",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="allow running with no photos in photos/source (protects the manifest)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if not SOURCE_DIR.exists():
        SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    previous_list = load_manifest()
    previous = {entry["src"]: entry for entry in previous_list if "src" in entry}

    sources = collect_sources()
    if not sources and previous_list and not args.allow_empty:
        sys.exit(
            "No photos found in photos/source, but photos.json has entries.\n"
            "Refusing to wipe the manifest. Copy your originals into "
            "photos/source, or pass --allow-empty if you really want an empty site."
        )

    # Reuse existing output names so adding photos does not renumber old ones.
    used_names: set[str] = set()
    for entry in previous.values():
        stem = Path(entry.get("file", "")).stem
        if stem:
            used_names.add(stem)

    plan: list[tuple[Path, str, str]] = []
    for source in sources:
        rel = source.relative_to(SOURCE_DIR).as_posix()
        old = previous.get(rel)
        old_stem = Path(old.get("file", "")).stem if old else ""
        if old_stem:
            name = old_stem
        else:
            base = slugify(source.stem)
            name = base
            counter = 2
            while name in used_names:
                name = f"{base}-{counter}"
                counter += 1
        used_names.add(name)
        plan.append((source, rel, name))

    skipped: list[tuple[str, str]] = []
    entries: list[dict] = []
    pending: list[tuple[Path, str, dict]] = []

    for source, rel, name in plan:
        try:
            meta = read_metadata(source)
        except Exception as exc:
            skipped.append((rel, f"cannot read image ({exc.__class__.__name__})"))
            continue

        if meta["lat"] is None or meta["lon"] is None:
            skipped.append((rel, "no GPS coordinates in EXIF"))
            continue

        output = WEB_DIR / f"{name}.jpg"
        old = previous.get(rel, {})

        auto_title = derived_title(source)
        old_title = (old.get("title") or "").strip()
        old_auto = old.get("autoTitle")
        if old_title and (old_auto is None or old_title != old_auto):
            title = old_title  # hand-edited: keep it
            auto_title = None
        else:
            title = auto_title

        entry = {
            "id": name,
            "src": rel,
            "file": f"photos/web/{name}.jpg",
            "lat": meta["lat"],
            "lon": meta["lon"],
            "date": meta["date"]
            or datetime.fromtimestamp(source.stat().st_mtime).date().isoformat(),
            "title": title,
        }
        if auto_title:
            entry["autoTitle"] = auto_title
        if old.get("width") and old.get("height"):
            entry["width"] = old["width"]
            entry["height"] = old["height"]
        entries.append(entry)

        fresh = (
            output.exists()
            and output.stat().st_mtime
            >= source.stat().st_mtime - MTIME_SLACK
        )
        if args.force or not fresh:
            pending.append((source, name, entry))

    # Encode the photos that need work.
    failures: list[tuple[str, str]] = []
    encoded = 0
    if pending and args.dry_run:
        print(f"\nWould encode {len(pending)} photo(s):")
        for _source, name, entry in pending:
            print(f"  {entry['src']} -> photos/web/{name}.jpg")
    elif pending:
        workers = min(8, (os.cpu_count() or 4))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(write_image, source, WEB_DIR / f"{name}.jpg"): (
                    source,
                    name,
                    entry,
                )
                for source, name, entry in pending
            }
            done = 0
            total = len(futures)
            for future, (source, name, entry) in futures.items():
                rel = entry["src"]
                try:
                    width, height = future.result()
                except Exception as exc:
                    failures.append((rel, f"could not encode ({exc.__class__.__name__})"))
                    if entry in entries:
                        entries.remove(entry)
                    continue
                entry["width"] = width
                entry["height"] = height
                done += 1
                encoded += 1
                print(f"  [{done}/{total}] {rel} -> photos/web/{name}.jpg")

    for rel, reason in failures:
        skipped.append((rel, reason))

    # Drop entries whose served copy is missing; optionally prune removed sources.
    pending_ids = {entry["id"] for _source, _name, entry in pending}
    pruned = 0
    kept: list[dict] = []
    for entry in entries:
        web_path = ROOT / entry["file"]
        if web_path.exists() or entry["id"] in pending_ids:
            kept.append(entry)
        else:
            skipped.append((entry["src"], "web copy missing; re-run to rebuild"))
            pruned += 1
    entries = kept

    if args.prune:
        live_sources = {entry["src"] for entry in entries}
        for rel, entry in previous.items():
            if rel in live_sources:
                continue
            web_path = ROOT / entry.get("file", "")
            if web_path.exists():
                print(f"  prune {entry['file']}")
                if not args.dry_run:
                    web_path.unlink()
                pruned += 1

        referenced = {entry["file"] for entry in entries}
        if WEB_DIR.exists():
            for web_path in WEB_DIR.glob("*.jpg"):
                rel_web = web_path.relative_to(ROOT).as_posix()
                if rel_web not in referenced:
                    print(f"  prune orphan {rel_web}")
                    if not args.dry_run:
                        web_path.unlink()
                    pruned += 1

    entries.sort(key=lambda entry: (entry.get("date") or "", entry["id"]))
    unchanged = sum(1 for entry in entries if entry["id"] not in pending_ids)

    if args.dry_run:
        print("\nDry run: nothing written.")
    else:
        WEB_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(dump_manifest(entries), encoding="utf-8")
        if skipped:
            SKIPPED_FILE.parent.mkdir(parents=True, exist_ok=True)
            lines = [f"{rel}\t{reason}" for rel, reason in skipped]
            SKIPPED_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        elif SKIPPED_FILE.exists():
            SKIPPED_FILE.unlink()

    if args.dry_run:
        work = f"{len(pending)} would be encoded, {unchanged} already current"
    else:
        work = f"{encoded} ({unchanged} already current)"
    print(
        "\n"
        f"photos:    {len(entries)} on the map\n"
        f"encoded:   {work}\n"
        f"skipped:   {len(skipped)}\n"
        f"pruned:    {pruned}"
    )
    if not HEIF_SUPPORT and any(
        str(source.suffix).lower() in (".heic", ".heif") for source in sources
    ):
        print("hint: install pillow-heif (see tools/requirements.txt) to read HEIC files")
    if skipped:
        print(f"details:   {SKIPPED_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
