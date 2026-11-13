"""Labelled full-resolution images for steps 2-4, and per-stave review crops."""
import cv2
import numpy as np

F = cv2.FONT_HERSHEY_SIMPLEX
COL = {'punctum': (0, 0, 220), 'virga': (0, 110, 255), 'pes': (0, 150, 0), 'clivis': (200, 100, 0), 'climacus': (160, 0, 160),
       'torculus': (0, 140, 140), 'porrectus': (120, 60, 0), 'scandicus': (80, 0, 200), 'distropha': (90, 90, 90)}


def _col(lbl):
    return COL.get(lbl.split(' ')[0], (40, 40, 40))


def _put(im, txt, org, c, sc, th):
    cv2.putText(im, txt, org, F, sc, (255, 255, 255), th + 4, cv2.LINE_AA)
    cv2.putText(im, txt, org, F, sc, c, th, cv2.LINE_AA)


def _short(pos):
    return ('L' if pos.startswith('line') else 'S') + pos.split()[1]


def label_images(src, lab, spacing_full):
    """Return dict name -> image for neumes (step 2), staff lines (step 3), positions (step 4)."""
    u = spacing_full / 100.0                     # scale text/strokes to the page resolution
    sc, th = max(0.4, 0.85 * u), max(1, int(round(2 * u)))
    out = {}
    im = src.copy()
    for s in lab['staves']:
        for e in s['elements']:
            b = e['box']
            if e['type'] == 'neume':
                c = _col(e['label'])
                cv2.rectangle(im, (b[0] - 4, b[1] - 4), (b[2] + 4, b[3] + 4), c, th + 1)
                _put(im, e['label'].replace('compound ', 'cmp '), (b[0] - 4, b[3] + int(30 * u)), c, sc, th)
                if e['flag']: cv2.circle(im, (b[2] + 10, b[1] - 6), int(9 * u) + 1, (0, 200, 255), -1)
            else:
                cv2.rectangle(im, (b[0], b[1]), (b[2], b[3]), (200, 0, 200), th + 1)
                _put(im, e['label'], (b[0] - 10, b[1] - 10), (200, 0, 200), sc, th)
    out['step2_neume_labels'] = im
    im = src.copy()
    for s in lab['staves']:
        for l in s['lines']:
            c = (255, 120, 0) if l['source'] == 'detected' else (0, 200, 0)
            pts = np.array(l['points'], np.int32)
            cv2.polylines(im, [pts], False, c, th + 1, cv2.LINE_AA)
            _put(im, f"L{l['line']}", (int(pts[-1][0] + 12 * u), int(pts[-1][1] + 10 * u)), c, sc, th)
        xs0 = min(l['points'][0][0] for l in s['lines']); x1 = max(l['points'][-1][0] for l in s['lines'])
        top = int(min(min(p[1] for p in l['points']) for l in s['lines']) - 18 * u)
        bot = int(max(max(p[1] for p in l['points']) for l in s['lines']) + 18 * u)
        cv2.rectangle(im, (int(xs0 - 30 * u), top), (int(x1 + 120 * u), bot), (0, 0, 200), th + 1)
        _put(im, f"Stave {s['n']}", (int(xs0 - 330 * u), (top + bot) // 2 + 15), (0, 0, 200), sc * 1.6, th + 1)
    out['step3_staff_lines'] = im
    im = src.copy(); ov = im.copy()
    for s in lab['staves']:
        for l in s['lines']:
            cv2.polylines(ov, [np.array(l['points'], np.int32)], False, (255, 90, 0), th + 1, cv2.LINE_AA)
    im = cv2.addWeighted(ov, 0.75, im, 0.25, 0)
    for s in lab['staves']:
        for e in s['elements']:
            if e['type'] != 'neume':
                b = e['box']; cv2.rectangle(im, (b[0], b[1]), (b[2], b[3]), (200, 0, 200), th)
                _put(im, e['label'].replace(' clef, line ', '-clef L'), (b[0] - 10, b[1] - 10), (200, 0, 200), sc * 0.9, th)
                continue
            for i, n in enumerate(e['notes']):
                b = n['box']; c = (0, 140, 255) if n['flag'] else (0, 0, 220)
                cv2.rectangle(im, (b[0], b[1]), (b[2], b[3]), c, th)
                dy = int((-8 if i % 2 == 0 else 30) * u)
                _put(im, _short(n['pos']), (b[2] + 2, b[1] + dy + int(10 * u)), c, sc * 0.9, th)
    out['step4_staff_positions'] = im
    return out


def review_crops(src, lab, spacing_full, max_width=2200):
    """One image per stave (original + neume labels + head positions), for quick checking."""
    imgs = label_images(src, lab, spacing_full)
    base = imgs['step2_neume_labels']
    out = {}
    for s in lab['staves']:
        xs = [p[0] for l in s['lines'] for p in l['points']]; ys = [p[1] for l in s['lines'] for p in l['points']]
        x0, x1 = int(min(xs) - 3 * spacing_full), int(max(xs) + 1.5 * spacing_full)
        y0, y1 = int(min(ys) - 2 * spacing_full), int(max(ys) + 1.6 * spacing_full)
        crop = base[max(0, y0):y1, max(0, x0):x1]
        f = min(1.0, max_width / crop.shape[1])
        out[f"stave_{s['n']:02d}"] = cv2.resize(crop, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return out
