# chantlabel

Staff lines, neumes and staff positions for square-notation chant leaves, with
Neon-compatible MEI output.

Given one page image (a PDF wrapping a scan, or a JPEG/PNG/TIFF), `chantlabel`:

1. **restores** the page: flattens the parchment background to lift stains, and
   writes a clean redraw (ink and red pigment on an even parchment tone);
2. **labels neumes** with bounding boxes and standard names (punctum, virga, pes,
   clivis, torculus, porrectus, climacus, scandicus, distropha, tristropha,
   `compound (…)` with its contour);
3. **traces staff lines** and groups them into staves;
4. **labels every note head with its staff position**: S0 = space below the bottom
   line, L1 = bottom line, S1, L2, … S4 = space above the top line of a four-line
   staff; extra lines continue the scheme (L0/S-1 below, L5/S5 above);

and writes:

| file | contents |
|---|---|
| `<page>_neumes.mei` | MEI 5.1 in the layout Neon uses: facsimile zones, `<sb>` per staff (zone with `@rotate`), `<clef>`, `<accid>`, one `<syllable>` per neume, `<nc>` with `@pname/@oct` (virga `tilt="s"`, climacus lozenges `tilt="se"`) |
| `<page>_labels.json` | everything above in full-resolution pixel coordinates, including staff-line polylines |
| `<page>_labels.md` | human-readable transcription: positions and pitches per staff, boxes, flagged items |
| `<page>_step2_neume_labels.jpg`, `_step3_staff_lines.jpg`, `_step4_staff_positions.jpg` | labelled full-resolution images |
| `<page>_restored_photo.jpg`, `<page>_clean_redraw.jpg` | the two restorations |
| `<page>_viewer/` | static zoomable review page (open `index.html` through any web server) |
| `<page>_summary.json` | counts, warnings, timing |

It was developed on AM 241 b III fol. 5 (0002v), a 14th-century Icelandic leaf with
red four-line staves; see `examples/`.

## Install

```bash
pip install .            # or: pip install -e .[test]
# PDFs: poppler-utils (pdfimages) or `pip install .[pdf]` for PyMuPDF
# optional checks: libxml2-utils (xmllint) for schema validation,
#                  Node.js + `npm install` in tools/ for the Verovio check
```

Python ≥ 3.9; depends on numpy, scipy, opencv-python-headless, scikit-image.

## Use

```bash
# one page
chantlabel run page.pdf -o out/ [--corrections page.corrections.json] [--title "..."]

# a folder (.pdf .jpg .png .tif); picks up <stem>.corrections.json beside each page
chantlabel batch pages/ -o out/ --no-restore --no-viewer      # fast pass: MEI/JSON/MD/images
#   -> out/batch_summary.csv with staves, heads, neumes, flagged, warnings per page

# checks
chantlabel validate out/page/page_neumes.mei --labels out/page/page_labels.json
#   schema: MEI 5.1 RELAX NG (downloaded once, or --rng path)
#   verovio positions: renders with Verovio (as Neon does) and checks that every
#   encoded pitch, read through its clef, lands on the labelled staff position

# accuracy against a corrected file (e.g. the same MEI after fixing it in Neon)
chantlabel evaluate out/page/page_neumes.mei corrected/page_neumes.mei
```

Options: `--no-restore`, `--no-images`, `--no-viewer`, `--review` (one labelled crop
per staff), `--config cfg.json` (override any field of `chantlabel/config.py`).

### Viewer

`<page>_viewer/` is self-contained (tiles, `labels.json`, `index.html`). Serve it
(`python -m http.server` inside the folder) or upload it as a static site. Click a
box to see its label, positions, pitches and the coordinates to use in a
corrections file; click empty space to get the coordinates of any point.

## Corrections

Automatic output is a draft. Corrections are a JSON file of **full-resolution page
coordinates** (the pixel space of the MEI facsimile, `labels.json` and the viewer),
so they stay valid when the detector changes. A head reference is matched to the
nearest detected head within half a staff space.

```json
{
  "clefs":  [{"stave": 5, "shape": "C", "line": 3, "x": 3348, "flag": "small c, read as C on line 3"}],
  "flats":  [{"stave": 10, "x": 3208, "pos": 3}],
  "drop":   [{"stave": 1, "x": 2402, "y": 1152}],
  "add":    [{"stave": 2, "x": 4016, "y": 1688, "flag": "added by hand"}],
  "group":  [[{"x": 2698, "y": 6150}, {"x": 2730, "y": 6210}, {"x": 2760, "y": 6250}]],
  "flag":   [{"x": 2350, "y": 3416, "note": "faint mark in stain"}],
  "pos":    [{"x": 4006, "y": 1746, "k": 0}],
  "stem":   [{"x": 5000, "y": 2000, "virga": false}]
}
```

- `clefs`: listing any clef for a staff replaces the automatic guess for that staff;
  list every clef of that staff (start and mid-staff). `line` counts from the bottom (1).
- `flats`: `pos` is the staff step of the flat (0 = bottom line, 1 = space above …).
- `drop` / `add`: remove a false head (text, initial, stain) / add a missed one.
- `group`: force heads into one neume (all other grouping stays automatic).
- `flag`: mark a head as uncertain (shown dashed orange, listed in the markdown).
- `pos`: override a head's staff step `k`. `stem`: override punctum/virga.
- `stave` is optional on head references but makes matching safer.

Workflow: run → review in the viewer → write corrections (copy references from the
viewer) → run again with `--corrections`. For a larger set, correct in Neon instead
and use `chantlabel evaluate` to measure the automatic pass against your corrected
MEI.

## How it works

All thresholds are in units of the staff-line spacing `sp`, measured on each page
(autocorrelation of the ruling); the page is rescaled to a working image with
`sp ≈ 50 px` (`Config.target_spacing_px`) and results are mapped back to full
resolution.

- **Restoration** (`restore.py`): a large grey closing at low resolution estimates
  the background; dividing it out removes low-frequency stains. Ink = dark after
  flattening; red pigment = Lab a* above threshold. The redraw draws the traced
  staff lines under the pigment so faded ruling stays continuous. Nothing is
  painted in where a stain hides the ink.
- **Staff lines** (`staves.py`): thin horizontal red strokes define the ruled area
  (this ignores colour charts and initials); line peaks are found in vertical strips,
  tracked across strips, grouped into staves (an internal or outer line that is too
  faint is interpolated and marked), then refined as polylines in three passes,
  first following the staff's common shape, then each line on its own.
- **Note heads** (`heads.py`): opening with a ~0.26 sp square removes stems and
  hairlines; distance-transform peaks are head centres. Candidates must lie in the
  staff band (from 0.78 sp above the top line to just above the measured top of the
  text below); blobs reaching into the text body, or tall solid blobs (initials),
  are rejected.
- **Clefs** (`clefs.py`): the leftmost tall, narrow shape at each staff start is a C
  clef on the line nearest its mouth. Margin ruling is ignored and broken strokes
  are merged. Mid-staff clefs, F clefs and flats come from corrections.
- **Neumes** (`neumes.py`): staff step `k = round((y_bottom_line − y) / (sp/2))`;
  two peaks on one wide head are merged; heads are grouped when connected by ink
  inside the staff band (stems are allowed to touch text below without merging
  neumes) or when they form a descending lozenge chain; groups split at horizontal
  gaps > 0.72 sp; stacked heads read bottom-up (pes). Names come from the contour;
  a single head with a descending tail > 0.45 sp is a virga.
- **Pitches** (`encode.py`): from the most recent clef to the left (C line = c4,
  F line = f3).

## Accuracy on the development leaf

AM 241 b III fol. 5 (0002v), 14 staves, 622 note heads in the hand-checked version:

| | heads P / R | pitch (matched heads) | grouping F1 | staff-start clefs |
|---|---|---|---|---|
| automatic, no corrections | 0.86 / 0.99 | 0.74 | 1.00 | 14 / 14 |
| with `examples/…corrections.json` | 0.995 / 0.994 | 0.998 | 1.00 | (given) |

The automatic pass finds almost every head; its false positives are mostly tops of
text letters, initials and abbreviation strokes, and its pitch errors come almost
entirely from the mid-staff clef changes this scribe uses (C on lines 2, 3 and 4
within one staff), which are not detected automatically. Staff lines lie within
1 px of the red ruling at the working scale (95th percentile). These figures are
from one leaf; measure on your own set with `chantlabel evaluate`.

## Known limitations

- Built for **red** staff lines. `"staff_color": "ink"` (dark ruling) is
  experimental and untested.
- Text is not transcribed or aligned: each neume is its own `<syllable>` with no
  `<syl>`; syllable grouping is left to Neon.
- Neume boundaries where stems of neighbouring notes touch, and the punctum/virga
  distinction, are the least reliable labels.
- No custos, division-line, liquescent, quilisma or oriscus detection.
- Verovio's Node build ignores the staff zones in facsimile mode (also for Neon's
  own sample files), so `validate` checks pitch/position consistency rather than
  Neon's exact on-screen layout. Open the MEI in Neon to confirm the layout.
- `validate --labels` uses `tools/` and therefore runs from a repository checkout.

## Layout

```
chantlabel/
  config.py        parameters (all in staff spaces)
  io.py            PDF / image loading
  restore.py       background flattening, ink/red maps, restorations
  staves.py        spacing estimate, line tracking, grouping, refinement
  heads.py         note-head candidates
  clefs.py         staff-start C clef guess
  corrections.py   coordinate-based corrections
  neumes.py        staff positions, grouping, names
  encode.py        pitches, labels.json, MEI 5.1, markdown
  render.py        labelled images, per-staff review crops
  viewer.py        static zoomable viewer (template in viewer_template/)
  evaluate.py      compare predicted vs corrected MEI
  validate.py      schema + Verovio checks
  pipeline.py      one-page run
  cli.py           command line
tools/             Verovio (Node) renderer used by `validate`
examples/          corrections and config for the development leaf
tests/             synthetic end-to-end test (pytest)
```
