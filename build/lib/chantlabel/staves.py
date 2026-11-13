"""Staff-line detection on the red (or dark) ruling map.

1. Estimate the line spacing from the autocorrelation of horizontal profiles.
2. Find line peaks in vertical strips, track them across strips, fit a curve.
3. Group lines into staves; interpolate an internal line that was too faint.
4. Refine each line locally (polyline every ~0.3 sp), using the stave's common
   shape where the pigment is missing.
"""
import warnings

import numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter
from scipy.signal import find_peaks


def estimate_spacing(red):
    """Median staff-line spacing (px) of a ruling map."""
    H, W = red.shape
    acs = []
    for x in np.linspace(W * 0.2, W * 0.8, 9).astype(int):
        p = red[:, max(0, x - W // 40):x + W // 40].astype(np.float32).mean(1)
        p = p - p.mean()
        ac = np.correlate(p, p, 'full')[len(p) - 1:]
        acs.append(ac / (ac[0] + 1e-9))
    ac = np.mean(acs, 0)
    lo = max(4, H // 400)
    pk, _ = find_peaks(ac[lo:H // 8], prominence=0.02)
    if not len(pk):
        raise RuntimeError("could not estimate staff-line spacing (no periodic ruling found)")
    return float(pk[0] + lo)


def thin_horizontal(red, sp):
    """Keep thin horizontal strokes only (drops colour-chart patches, initials, rubric blocks)."""
    import cv2
    thick = cv2.morphologyEx(red, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(3, int(0.3 * sp)))))
    thin = cv2.subtract(red, thick)
    return cv2.morphologyEx(thin, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, int(2 * sp)), 1)))


def text_block_x(red, frac=0.3, sp=50):
    """Horizontal extent of the ruled area."""
    col = (thin_horizontal(red, sp) > 40).mean(0)
    col = gaussian_filter1d(col, red.shape[1] / 200)
    on = np.where(col > col.max() * frac)[0]
    return int(on.min()), int(on.max())


def detect_staves(red, cfg):
    q = cfg.target_spacing_px / 50.0
    H, W = red.shape
    X0, X1 = text_block_x(red, sp=cfg.target_spacing_px)
    SW = max(8, int(cfg.strip_width_sp * cfg.target_spacing_px))
    centers, peaks = [], []
    for x in range(X0, X1 - SW + 1, SW // 2):
        p = gaussian_filter1d(red[:, x:x + SW].astype(np.float32).mean(1), 2 * q)
        pk, _ = find_peaks(p, distance=max(3, int(28 * q)), prominence=6)
        centers.append(x + SW / 2)
        peaks.append([int(k) for k in pk])
    centers = np.array(centers)
    if len(centers) < 4:
        raise RuntimeError("ruled area too narrow")
    mid = len(centers) // 2
    rng = range(max(0, mid - 6), min(len(centers), mid + 6))
    best = max(rng, key=lambda i: len(peaks[i]))
    xmid = (X0 + X1) / 2
    lines = []
    for y0 in peaks[best]:
        pts = {best: y0}
        for direction in (1, -1):
            i, y, miss = best + direction, y0, 0
            while 0 <= i < len(centers) and miss < 6:
                cand = [k for k in peaks[i] if abs(k - y) <= (7 + 3 * miss) * q]
                if cand:
                    y = min(cand, key=lambda k: abs(k - y)); pts[i] = y; miss = 0
                else:
                    miss += 1
                i += direction
        if len(pts) >= len(centers) * 0.3:
            idx = sorted(pts)
            xs = centers[idx]; ys = np.array([pts[i] for i in idx], float)
            c = np.polyfit(xs, ys, 2)
            keep = np.abs(ys - np.polyval(c, xs)) < 6 * q
            c = np.polyfit(xs[keep], ys[keep], 2)
            lines.append({'coef': c, 'n': int(keep.sum()), 'y_mid': float(np.polyval(c, xmid))})
    lines.sort(key=lambda l: l['y_mid'])
    ded = []
    for l in lines:
        if ded and abs(l['y_mid'] - ded[-1]['y_mid']) < 15 * q:
            if l['n'] > ded[-1]['n']: ded[-1] = l
            continue
        ded.append(l)
    if not ded:
        raise RuntimeError("no staff lines found")
    # group into staves
    groups, cur = [], [ded[0]]
    for l in ded[1:]:
        if l['y_mid'] - cur[-1]['y_mid'] < cfg.stave_gap_sp * cfg.target_spacing_px: cur.append(l)
        else: groups.append(cur); cur = [l]
    groups.append(cur)
    staves = []
    for g in groups:
        ys = [l['y_mid'] for l in g]
        gaps = np.diff(ys)
        sp = float(np.median(gaps[gaps < 1.4 * cfg.target_spacing_px])) if (gaps < 1.4 * cfg.target_spacing_px).any() else cfg.target_spacing_px
        coefs, src = [g[0]['coef']], ['detected']
        for i in range(1, len(g)):
            n = int(round((ys[i] - ys[i - 1]) / sp))
            for k in range(1, n):
                coefs.append(g[i - 1]['coef'] + (g[i]['coef'] - g[i - 1]['coef']) * k / n); src.append('interpolated')
            coefs.append(g[i]['coef']); src.append('detected')
        if len(coefs) < 2:
            continue   # isolated line (decoration, text underline...)
        # a faint outer line: add it on the side with more red evidence
        xs_e = np.linspace(X0, X1, 60)

        def evidence(c):
            ys_e = np.polyval(c, xs_e)
            v = []
            for x, y in zip(xs_e.astype(int), ys_e):
                y = int(round(y))
                if 3 <= y < H - 3: v.append(red[y - 3:y + 4, x].max())
            return float(np.mean(v)) if v else 0.0
        while len(coefs) < cfg.lines_per_staff:
            up = coefs[0].copy(); up[-1] -= sp
            dn = coefs[-1].copy(); dn[-1] += sp
            if evidence(up) >= evidence(dn):
                coefs.insert(0, up); src.insert(0, 'interpolated')
            else:
                coefs.append(dn); src.append('interpolated')
        staves.append({'coefs': coefs, 'src': src, 'spacing': sp,
                       'complete': len(g) >= 2 and len(coefs) == cfg.lines_per_staff})
    return refine(red, staves, X0, X1, cfg)


def refine(red, staves, X0, X1, cfg):
    q = cfg.target_spacing_px / 50.0
    H, W = red.shape
    STEP = max(4, int(16 * q))
    XS = np.arange(max(0, X0 - int(150 * q)), min(W - 1, X1 + int(75 * q)), STEP)
    tol = int(9 * q); hw = int(24 * q)

    def track(c):
        ys0 = np.polyval(c, XS) if len(c) <= 4 else np.asarray(c)   # coefficients or a curve
        out = np.full(len(XS), np.nan)
        for i, (x, y0) in enumerate(zip(XS, ys0)):
            y0 = int(round(y0))
            a = max(0, y0 - tol - 3)
            win = red[a:y0 + tol + 4, max(0, x - hw):x + hw].astype(np.float32).mean(1)
            if len(win) < 7: continue
            win = gaussian_filter1d(win, 1.2)
            k = int(np.argmax(win))
            if win[k] > 18 and 3 <= k <= len(win) - 4:
                out[i] = a + k
        return out

    def fit_stave(s, seeds, follow=False):
        R = np.array([track(np.asarray(c)) for c in seeds])
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            shape = np.nanmean(R - np.nanmedian(R, 1, keepdims=True), 0)
        ok = ~np.isnan(shape)
        shape = np.interp(np.arange(len(shape)), np.where(ok)[0], shape[ok]) if ok.any() else np.zeros(len(shape))
        shape = gaussian_filter1d(median_filter(shape, 7), 3)
        lines = []
        for j, o in enumerate(R):
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)
                off = np.nanmedian(o - shape)
            if np.isnan(off):
                off = float(np.median(np.polyval(s['coefs'][j], XS) - shape))
            # first pass: lines follow the stave's common shape; later passes follow each line
            pred = np.asarray(seeds[j], float) if follow else shape + off
            good = ~np.isnan(o) & (np.abs(o - pred) < (10 if follow else 5) * q)
            d = np.where(good, o - pred, 0.0)
            wgt = gaussian_filter1d(good.astype(float), 4)
            y = pred + np.where(wgt > 0.15, gaussian_filter1d(d, 4) / np.maximum(wgt, 1e-3), 0)
            pres = np.zeros(len(XS))
            for i, x in enumerate(XS):
                yy = int(np.clip(round(y[i]), 2, H - 3))
                pres[i] = red[yy - 2:yy + 3, max(0, x - 8):x + 8].max(0).mean()
            idx = np.where(gaussian_filter1d((pres > 30).astype(float), 3) > 0.35)[0]
            i0, i1 = (int(idx.min()), int(idx.max())) if len(idx) else (0, len(XS) - 1)
            lines.append({'y': y, 'i0': i0, 'i1': i1, 'support': float(good.mean())})
        return lines

    for s in staves:
        s['lines'] = fit_stave(s, s['coefs'])
        # second pass, tracking around the first-pass curve (follows drift at the ends)
        for _ in range(2):
            s['lines'] = fit_stave(s, [l['y'] for l in s['lines']], follow=True)
        s['x0'] = int(XS[int(np.median([l['i0'] for l in s['lines']]))])
        s['x1'] = int(XS[int(np.median([l['i1'] for l in s['lines']]))])
    # a stave whose ruling has faded at one end keeps the text-block extent
    if staves:
        gx0 = int(np.median([s['x0'] for s in staves])); gx1 = int(np.median([s['x1'] for s in staves]))
        for s in staves:
            if s['x1'] < gx1 - 3 * cfg.target_spacing_px: s['x1'] = gx1; s['x1_extended'] = True
            if s['x0'] > gx0 + 3 * cfg.target_spacing_px: s['x0'] = gx0; s['x0_extended'] = True
    return {'XS': XS, 'staves': staves}


class StaffGeometry:
    """Convenience accessors on the detected staves (working-image coordinates)."""

    def __init__(self, det):
        self.XS = np.asarray(det['XS'])
        self.staves = det['staves']

    def line_y(self, si, j, x):
        """y of line j (0 = top) of stave si at x."""
        return float(np.interp(x, self.XS, self.staves[si]['lines'][j]['y']))

    def lines_at(self, si, x):
        ys = [float(np.interp(x, self.XS, l['y'])) for l in self.staves[si]['lines']]
        return ys, (ys[-1] - ys[0]) / (len(ys) - 1)

    def k_of(self, si, x, y):
        """Staff step of point (x,y): 0 = bottom line, 1 = space above it, -1 = space below."""
        ys, sp = self.lines_at(si, x)
        return (ys[-1] - y) / (sp / 2)
