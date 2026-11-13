"""Clef guessing at the start of each staff.

Heuristic only: the leftmost tall, narrow ink shape at the start of a staff is
taken as a C clef, sitting on the staff line nearest its mouth (the gap between
its two bulges). The search is cropped to the staff band, so a clef touching the
text above still counts, and small vertical gaps are bridged, so a clef broken
into two strokes counts as one shape.

F clefs, mid-staff clef changes and flats are not detected; supply them in the
corrections file. Every automatic clef is flagged for review.
"""
import cv2
import numpy as np


def _shapes(raw, sp):
    """Ink shapes in a crop: connected pieces, hairline pieces dropped (margin ruling,
    dotted lines), pieces stacked with a small vertical gap merged (broken strokes)."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(raw, 8)
    pieces = [[int(v) for v in st[k][:4]] + [[k]] for k in range(1, n)
              if st[k][2] >= 0.15 * sp and st[k][4] >= 0.02 * sp * sp]
    merged = True
    while merged:
        merged = False
        for i in range(len(pieces)):
            for j in range(i + 1, len(pieces)):
                a, b = pieces[i], pieces[j]
                ov = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
                gap = max(a[1], b[1]) - min(a[1] + a[3], b[1] + b[3])
                if ov >= 0.5 * min(a[2], b[2]) and gap < 0.3 * sp:
                    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
                    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
                    pieces[i] = [x0, y0, x1 - x0, y1 - y0, a[4] + b[4]]
                    del pieces[j]; merged = True; break
            if merged: break
    singles = [[int(v) for v in st[k][:4]] + [[k]] for k in range(1, n) if st[k][2] >= 0.15 * sp]
    out = []
    for x, y, w, h, ks in pieces + [p for p in singles if [p[4]] not in [q[4] for q in pieces]]:
        mask = np.isin(lab, ks).astype(np.uint8)
        out.append((x, y, w, h, mask))
    return out


def guess_start_clefs(bw, geo, cfg):
    H, W = bw.shape
    clefs = []
    for si, s in enumerate(geo.staves):
        ys, sp = geo.lines_at(si, s['x0'])
        top, bot = ys[0], ys[-1]
        xa, xb = int(max(0, s['x0'] - 2.8 * sp)), int(min(W, s['x0'] + 1.6 * sp))
        ya, yb = int(max(0, top - 1.0 * sp)), int(min(H, bot + 0.5 * sp))
        raw = bw[ya:yb, xa:xb]
        cands = []
        for x, y, w, h, mask in _shapes(raw, sp):
            if not (1.0 * sp <= h <= 2.8 * sp and 0.25 * sp <= w <= 1.4 * sp): continue
            if mask.sum() / float(w * h) < 0.2: continue
            cands.append((x, y, w, h, mask))
        if not cands:
            clefs.append({'stave': si, 'shape': 'C', 'line': len(ys), 'x': float(s['x0']),
                          'flag': 'no clef found at staff start; assumed C on top line', 'auto': True})
            continue
        x, y, w, h, mask = min(cands, key=lambda c: c[0])
        cx = x + w / 2 + xa
        cy = _mouth_y(mask, (x, y, w, h, 0), y + h / 2) + ya
        ys, sp = geo.lines_at(si, cx)
        j = int(np.argmin([abs(cy - yy) for yy in ys]))      # 0 = top line
        clefs.append({'stave': si, 'shape': 'C', 'line': len(ys) - j, 'x': float(cx),
                      'flag': 'automatic clef guess', 'auto': True})
    return clefs


def _mouth_y(mask, stat, fallback):
    """y (in the crop) of the C clef's mouth: the row in the middle of the glyph where
    its right edge is furthest left (measured on the unbridged ink)."""
    x, y, w, h, _ = [int(v) for v in stat]
    m = mask[y:y + h, x:x + w] > 0
    right = np.array([np.max(np.where(r)[0]) if r.any() else -1 for r in m], float)
    lo, hi = int(h * 0.25), int(h * 0.75)
    if hi - lo < 3:
        return fallback
    seg = np.where(right[lo:hi] < 0, -1e9, right[lo:hi])
    i = int(np.argmin(np.convolve(seg, np.ones(3) / 3, 'same')))
    return float(y + lo + i)
