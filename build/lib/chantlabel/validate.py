"""MEI checks: RELAX NG schema validation and a Verovio pitch/position cross-check."""
import json
import os
import re
import shutil
import subprocess
import tempfile

SCHEMA_URL = "https://raw.githubusercontent.com/music-encoding/schema/main/5.1/mei-all.rng"
HERE = os.path.dirname(__file__)


def schema(mei_path, rng_path=None):
    """Validate with xmllint (needs libxml2-utils). Downloads the MEI 5.1 schema if no path is given."""
    if shutil.which('xmllint') is None:
        return None, 'xmllint not installed'
    if rng_path is None:
        rng_path = os.path.join(tempfile.gettempdir(), 'mei-all-5.1.rng')
        if not os.path.exists(rng_path):
            import urllib.request
            urllib.request.urlretrieve(SCHEMA_URL, rng_path)
    r = subprocess.run(['xmllint', '--noout', '--relaxng', rng_path, mei_path], capture_output=True, text=True)
    return r.returncode == 0, (r.stderr.strip().splitlines() or [''])[-1]


def verovio_positions(mei_path, labels_path):
    """Render with Verovio (Node + the npm 'verovio' package) and check that every encoded
    pitch, read through its clef, falls on the staff position in labels.json.

    Verovio's neume layout puts staff lines 180 units apart at y = 0..540 for a
    four-line staff, so a note's step above the bottom line is (540 - y) / 90.
    """
    if shutil.which('node') is None:
        return None, 'node not installed'
    script = os.path.join(HERE, '..', 'tools', 'verovio_render.mjs')
    with tempfile.TemporaryDirectory() as td:
        svg = os.path.join(td, 'out.svg')
        r = subprocess.run(['node', script, mei_path, svg], capture_output=True, text=True, cwd=os.path.join(HERE, '..', 'tools'))
        if r.returncode != 0:
            return None, r.stderr.strip()[-400:]
        s = open(svg).read()
    ys = [int(m) for m in re.findall(r'class="nc">\s*<use xlink:href="#[^"]+" transform="translate\(-?\d+, (-?\d+)\)', s)]
    lab = json.load(open(labels_path))
    ks = [n['k'] for st in lab['staves'] for e in st['elements'] if e['type'] == 'neume' for n in e['notes']]
    nl = len(lab['staves'][0]['lines']) if lab['staves'] else 4
    bottom = (nl - 1) * 180
    if len(ys) != len(ks):
        return False, f'Verovio drew {len(ys)} notes, labels have {len(ks)}'
    bad = sum(abs((bottom - y) / 90 - k) > 0.01 for y, k in zip(ys, ks))
    return bad == 0, f'{len(ks) - bad}/{len(ks)} notes on their labelled position'
