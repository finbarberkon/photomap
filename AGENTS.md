# AGENTS.md

Finbar's Photo Map is a static, build-free website that shows a map of the
places Finbar has photographed. It is live at https://finbar.dev/photomap/.
`README.md` is the user-facing guide; this file covers what an agent needs to
work on the repo without breaking things.

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

## Hosting

The site is served by GitHub Pages at https://finbar.dev/photomap/. The
`finbar.dev` custom domain is configured on the user Pages site, so there is no
`CNAME` file here. `.nojekyll` must stay in the repo root: it stops GitHub from
running the static files through Jekyll.

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
- **Only the capture date is shown, no captions or place names.** The viewer
  puts the date under the photo; the map thumbnails stay bare. Don't add other
  metadata fields to the UI unless the design is intentionally changing.
- **Clicking a stack opens its photos as an album in the viewer**, it does not
  zoom the map. `zoomToBoundsOnClick`/`spiderfyOnMaxZoom` are off and
  `onClusterClick` in `assets/app.js` handles `clusterclick`/`clusterkeypress`.
- Adding a field to a manifest entry means updating `tools/prep.py`, the
  `app.js` header comment, and any consumption in `app.js`.

## Cluster animation (front end)

Clustering, joins/splits and their fade live in vendored markercluster, which
models a photo (`L.Marker`) and a stack (`L.MarkerCluster`) as different node
types. On a zoom-out join its own fade only reaches an incoming cluster's direct
markers and child clusters exactly one level down, so a nested stack or a lone
photo under a single-parent chain stays opaque until the plugin's 300ms cleanup
timer removes it. `assets/app.js` patches
`L.MarkerCluster.prototype._recursivelyAnimateChildrenIn` to recurse over both
`_childClusters` and `_markers`, so every outgoing descendant is moved and faded
the same way.

That patch monkeypatches a plugin internal, so it is pinned to the vendored
markercluster version and must be re-checked if `vendor/` is ever updated. A
cleaner long-term direction is to replace markercluster's model/render pass
with our own uniform node tree, where a photo and an n-cluster are genuinely
the same object and the animation recurses over one `children()` accessor. That
deletes the patch and the last node-type special cases, and is the natural fit
for the planned n-cluster (shown as a 3-card stack with a count). The cost is owning clustering, visibility, pruning
and the animation details markercluster currently handles. Not scheduled.

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
