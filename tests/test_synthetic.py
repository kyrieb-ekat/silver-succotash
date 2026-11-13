"""End-to-end test on a synthetic leaf with known staff lines, clef and note positions."""
import json

import cv2
import numpy as np
import pytest

from chantlabel.config import Config
from chantlabel.encode import pitch_of
from chantlabel.evaluate import evaluate
from chantlabel.neumes import pos_label
from chantlabel.pipeline import run

SP = 60          # staff-line spacing in the synthetic image (px)
TOP = [400, 900]  # y of the top line of each staff
X0, X1 = 300, 2300
# (x, k) per note: k = 0 bottom line, -1 space below, 7 space above the top line
NOTES = [(520, 0), (680, 2), (840, 4), (1000, 5), (1160, 7), (1320, -1), (1480, 3), (1640, 6), (1800, 1)]


def make_leaf(path):
    H, W = 1500, 2600
    rng = np.random.default_rng(0)
    im = np.full((H, W, 3), (182, 214, 232), np.uint8)
    im = cv2.add(im, rng.integers(0, 12, (H, W, 3), dtype=np.uint8))
    # a stain
    cv2.circle(im, (1500, 500), 260, (120, 160, 190), -1)
    im = cv2.GaussianBlur(im, (0, 0), 1.2)
    for top in TOP:
        for j in range(4):
            y = top + j * SP
            cv2.line(im, (X0, y), (X1, y + 6), (60, 70, 200), 4, cv2.LINE_AA)   # slight tilt
        bot = top + 3 * SP
        # C clef on line 3 (second from top): two bulges around y = top + SP
        cy = top + SP
        cv2.ellipse(im, (X0 + 40, cy), (int(0.35 * SP), int(0.85 * SP)), 0, 40, 320, (25, 25, 25), int(0.28 * SP))
        for x, k in NOTES:
            y = bot - k * SP / 2 + (x - X0) * 6 / (X1 - X0)
            h = int(0.32 * SP)
            cv2.rectangle(im, (x - h, int(y - h)), (x + h, int(y + h)), (25, 25, 25), -1)
            cv2.line(im, (x + h - 2, int(y + h)), (x + h - 2, int(y + h + 0.8 * SP)), (25, 25, 25), 3)  # virga tail
    cv2.imwrite(path, im)


@pytest.fixture(scope='module')
def result(tmp_path_factory):
    d = tmp_path_factory.mktemp('syn')
    p = str(d / 'leaf.png')
    make_leaf(p)
    summary = run(p, str(d / 'out'), cfg=Config(), restore=False, images=False, viewer=False, log=lambda *a: None)
    lab = json.load(open(d / 'out' / 'leaf_labels.json'))
    return summary, lab, d


def test_staves_and_lines(result):
    summary, lab, _ = result
    assert summary['staves'] == 2
    assert all(len(s['lines']) == 4 for s in lab['staves'])


def test_every_note_found_on_its_position(result):
    _, lab, _ = result
    for s in lab['staves']:
        notes = [(n['box'], n['k']) for e in s['elements'] if e['type'] == 'neume' for n in e['notes']]
        assert len(notes) == len(NOTES)
        found = sorted(((b[0] + b[2]) / 2 / lab['image']['width'], k) for b, k in notes)
        assert [k for _, k in found] == [k for _, k in NOTES]


def test_clef_and_pitches(result):
    _, lab, _ = result
    for s in lab['staves']:
        clefs = [e for e in s['elements'] if e['type'] == 'clef']
        assert clefs and clefs[0]['label'] == 'C clef, line 3'
        first = next(e for e in s['elements'] if e['type'] == 'neume')
        assert first['notes'][0]['pitch'] == 'f3'     # bottom line under a C clef on line 3


def test_mei_self_evaluation(result):
    _, _, d = result
    mei = str(d / 'out' / 'leaf_neumes.mei')
    r = evaluate(mei, mei)
    assert r['head_f1'] == 1.0 and r['pitch_accuracy_on_matched'] == 1.0


def test_position_scheme():
    assert [pos_label(k) for k in (-1, 0, 1, 2, 7, 8)] == ['space 0', 'line 1', 'space 1', 'line 2', 'space 4', 'line 5']
    assert pitch_of(6, 'C', 4) == ('c', 4)
    assert pitch_of(0, 'C', 4) == ('d', 3)
    assert pitch_of(2, 'F', 2) == ('f', 3)
