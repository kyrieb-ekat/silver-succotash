"""Note-head candidates: distance-transform peaks of the opened ink mask, kept only
inside each staff's band and filtered against text and initials."""
import cv2
import numpy as np
from skimage.feature import peak_local_max


def measure_text_tops(bw, geo):
    """For each stave, the offset (in sp) below its bottom line where the text body starts."""
    out = []
    n = len(geo.staves)
    for si in range(n):
        if si == n - 1:
            out.append(None); continue
        s = geo.staves[si]
        xa, xb = s['x0'] + 0.2 * (s['x1'] - s['x0']), s['x1'] - 0.2 * (s['x1'] - s['x0'])
        xs = np.arange(int(xa), int(xb), 16)
        bot = np.array([geo.line_y(si, -1, x) for x in xs])
        top = np.array([geo.line_y(si + 1, 0, x) for x in xs])
        sp = float(np.median([geo.lines_at(si, x)[1] for x in xs[::10]]))
        gap = int((top - bot).min())
        if gap < 4:
            out.append(None); continue
        prof = np.array([np.mean([bw[int(b) + off, x - 8:x + 8].mean() for b, x in zip(bot, xs)]) for off in range(gap)])
        on = np.where(prof > prof.max() * 0.5)[0]
        out.append(float(on.min() / sp) if len(on) else None)
    vals = [v for v in out if v is not None]
    med = float(np.median(vals)) if vals else 0.9
    return [v if v is not None else med for v in out]


def detect_heads(bw, geo, cfg):
    """Return list of head dicts {id, stave, cx, cy, dt} in working coordinates."""
    op = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (cfg.head_open_px,) * 2))
    dt = cv2.distanceTransform(op, cv2.DIST_L2, 5)
    _, blab, bst, _ = cv2.connectedComponentsWithStats(op, 8)
    pk = peak_local_max(dt, min_distance=cfg.head_peak_min_dist, threshold_abs=cfg.head_peak_min_dt, exclude_border=False)
    textstart = measure_text_tops(bw, geo)
    sp0 = cfg.target_spacing_px
    heads = []
    for (py, px) in pk:
        for si, s in enumerate(geo.staves):
            if not (s['x0'] - 2.8 * sp0 <= px <= s['x1'] + 1.2 * sp0): continue
            ys, sp = geo.lines_at(si, px)
            top, bot = ys[0], ys[-1]
            lo = top - cfg.band_above_sp * sp
            hi = bot + max(cfg.band_below_min_sp, textstart[si] - cfg.band_below_text_margin_sp) * sp
            if lo <= py <= hi:
                b = bst[blab[py, px]]
                bx, by, bwid, bh, area = [int(v) for v in b]
                fill = area / max(1, bwid * bh)
                if by + bh > bot + cfg.text_reach_sp * sp: break          # touches the text body
                if bh > cfg.tall_blob_sp * sp and fill > cfg.tall_blob_fill: break   # initial / text stroke
                heads.append({'stave': si, 'cx': int(px), 'cy': int(py), 'dt': float(dt[py, px])})
                break
    heads.sort(key=lambda h: (h['stave'], h['cx']))
    keep = []
    for h in heads:
        if any(k['stave'] == h['stave'] and abs(k['cx'] - h['cx']) < 10 and abs(k['cy'] - h['cy']) < 10 for k in keep[-6:]):
            continue
        keep.append(h)
    for i, h in enumerate(keep):
        h['id'] = i
    return keep
