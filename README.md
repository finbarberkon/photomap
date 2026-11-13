# where

A small map of the places I've photographed. Dots on a world map; click one and
the photo opens full screen, Quick Look style. Click again (or press Esc) and
you're back on the map.

No framework, no build step, no API keys. Leaflet and its clustering plugin are
vendored in `vendor/`, and the site is a few static files that GitHub Pages can
serve directly.

## Preview locally

```bash
make setup     # one time: creates .venv and installs Pillow
make serve     # http://localhost:8000
```

`python3 -m http.server` works too, but the page must be served over HTTP —
opening `index.html` directly blocks `photos.json` and the images.

`make setup` needs Python 3. On macOS that means the Command Line Tools
(`xcode-select --install`) or `brew install python`.

## Adding photos

1. Copy the originals into `photos/source/` — subfolders are fine and anything
   nested is picked up (`photos/source/Japan/Kyoto/IMG_1234.HEIC`).
2. Run:

   ```bash
   make prep
   ```

3. Reload the page. Commit and push when you're happy.

`make prep` rescans `photos/source/`, encodes anything new into
`photos/web/`, reads the GPS and capture date from EXIF, and rewrites
`photos.json`. Already-encoded photos are skipped, so adding a few files is
quick even with hundreds in the library.

It handles:

- JPG, PNG, HEIC/HEIF, TIFF and WebP, including iPhone HEIC and Live Photo
  stills (first frame only)
- EXIF orientation, so sideways phone shots come out upright
- Display P3 photos, converted to sRGB so colours don't look oversaturated
- filenames with spaces, accents or duplicates across folders
- photos with no GPS: they are listed in `photos/skipped.txt` instead of
  silently disappearing

Useful flags:

| Command | What it does |
| --- | --- |
| `make prep` | encode new photos, rebuild `photos.json` |
| `.venv/bin/python tools/prep.py --dry-run` | show what would happen, write nothing |
| `.venv/bin/python tools/prep.py --force` | re-encode everything (e.g. after changing the size below) |
| `.venv/bin/python tools/prep.py --prune` | also delete web copies whose source is gone |

Size and quality live at the top of `tools/prep.py` (`MAX_EDGE`, `JPEG_QUALITY`).

### Titles

By default a photo is titled after its parent folder (`Japan/Kyoto/...` becomes
"Kyoto"). Edit `"title"` in `photos.json` to change it; hand-written titles
survive `make prep`. Photos with no title just show their date and coordinates.

Moving or renaming a source file makes it look like a new photo on the next run
(it gets a new entry and web copy). Run `--prune` afterwards to remove the old
copy.

### What gets committed

Only `photos/web/` and `photos.json` are committed. `photos/source/` is
ignored, so the repo stays around 200–400 KB per photo instead of several
megabytes, and your original files stay where they are. Keep your own backup of
the originals — they are not in the repo.

## Publishing on GitHub Pages

The site is entirely static, so any static host works. For GitHub Pages:

1. Create a public repository named `fmb-where` (or anything else).
2. Push this repo to it.
3. In the repository: **Settings → Pages → Build and deployment**, set
   **Source** to **Deploy from a branch**, branch **main**, folder **/ (root)**.
4. Wait a minute, then open `https://<username>.github.io/<repo>/`.

`.nojekyll` is included so GitHub serves the files as-is.

## How it fits together

```
index.html            page shell and photo overlay
assets/app.js         load photos.json, draw dots, open/close photos
assets/styles.css     map dots, clusters, overlay
photos.json           generated index: id, file, lat, lon, date, title
photos/web/*.jpg      generated 1600px web copies (committed)
photos/source/        your originals (not committed)
tools/prep.py         the only script: EXIF -> web copies + photos.json
vendor/               Leaflet 1.9.4 + Leaflet.markercluster 1.5.3
```

Map tiles are OpenStreetMap's public tiles (no API key), desaturated with CSS
so the dots stand out. Each photo also has a linkable address: `/#img-1620`
opens that photo directly.
