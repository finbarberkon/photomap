# AGENTS.md

A static, build-free website that shows a map of the places Finbar has
photographed. `README.md` is the user-facing guide; this file covers what an
agent needs to work on the repo without breaking things.

## Commands

```bash
make setup     # one time: create .venv and install Pillow + pillow-heif
make prep      # encode new photos and regenerate photos.json
make serve     # preview at http://localhost:8000 (must be HTTP, not file://)
```

Underlying tool:

```bash
.venv/bin/python tools/prep.py [--force] [--prune] [--dry-run] [--allow-empty]
```

`.venv/` is gitignored and machine-local. If it is missing or its interpreter
does not match the host (e.g. it was created on macOS and is now on Linux),
recreate it with `make setup`. On macOS, `make setup` needs Python 3 from the
Command Line Tools or Homebrew.

## Layout

```
index.html            page shell + photo overlay markup
assets/app.js         Leaflet map, thumbnail markers, clusters, viewer
assets/styles.css     markers, cluster stacks, viewer, status
photos.json           GENERATED index (id, src, file, thumb, lat, lon, date, width, height)
photos/web/*.jpg      GENERATED 1600px web copies (committed)
photos/web/thumbs/    GENERATED 144px square markers (committed)
photos/source/        originals (gitignored, not committed)
tools/prep.py         the only script: EXIF -> web copies, thumbs, photos.json
vendor/               vendored Leaflet 1.9.4 + Leaflet.markercluster 1.5.3
```

## Hard rules

- **Do not hand-edit `photos.json` or anything under `photos/web/`.** They are
  produced by `tools/prep.py`. Change the script or its inputs, then run
  `make prep`.
- **Do not edit `vendor/`.** It is vendored third-party JS/CSS; there is no
  package manager and no update process here.
- **Do not edit `photos/source/`.** Those are the user's irreplaceable
  originals and are gitignored. They are never committed; the user keeps their
  own backup.
- **Only `photos/web/` and `photos.json` are committed** for the library.
  Adding a source photo means running `make prep` so the generated pair exists.
- There is no build step, no `package.json`, and no bundler. Static files only.

## Conventions

- **Front end**: plain dependency-free JavaScript, an IIFE with `'use strict'`
  and `var` (ES5 style), no framework, no modules. DOM is queried by id via the
  small `$` helper; state lives in one `state` object. Keep it in that style.
  Leaflet and the cluster plugin are loaded globally from `vendor/`.
- **Python**: stdlib plus Pillow; `pillow-heif` is optional (HEIC/HEIF support
  degrades gracefully). Uses `from __future__ import annotations`, type hints,
  `pathlib`, and `snake_case`. Keep it compatible with Python 3.9 (the venv
  version). Tuning constants (`MAX_EDGE`, `JPEG_QUALITY`, `THUMB_SIZE`,
  `THUMB_QUALITY`) live at the top of `tools/prep.py`.
- **`photos.json` formatting is deliberate**: one entry per line, keys sorted
  (`sort_keys=True`), two-space indent, entries sorted by `(date, id)`. Let
  `dump_manifest()` produce it; don't reformat by hand.
- **No captions or place names, by design.** A photo is just its image, so
  there is nothing to keep in sync as the library grows. Don't add metadata
  fields to the UI unless the design is intentionally changing.
- Adding a field to a manifest entry means updating `tools/prep.py`, the
  `app.js` header comment, and any consumption in `app.js`.

## `make prep` behaviour worth knowing

- Scans `photos/source/` recursively; reuses previous output names so new
  photos don't renumber old ones.
- If `photos/source/` is empty but `photos.json` has entries, it **refuses to
  wipe the manifest** unless `--allow-empty` is passed. This is intentional.
- `--force` re-encodes everything (use after changing size/quality constants).
- `--prune` deletes web copies and manifest entries whose source is gone. A
  moved/renamed source looks like a new photo, so run `--prune` after one.
- `--dry-run` reports without writing.
- Photos without GPS land in `photos/skipped.txt` (also gitignored) rather than
  disappearing silently.

## Testing / verifying changes

There is **no automated test suite and no CI**. Verify by exercising the real
paths:

- For `tools/prep.py`: run `.venv/bin/python tools/prep.py --dry-run` first,
  then `make prep`, and confirm the counts and `photos.json` output.
- For the front end: `make serve` and check `http://localhost:8000`, including
  `` /#<id> `` deep links (e.g. `/#img-1620`), clicking a marker to open the
  viewer, and Esc/click-to-close. An empty map with a status message usually
  means `photos.json` was fetched over `file://` instead of HTTP.

Report what you actually ran and its result before claiming completion.
