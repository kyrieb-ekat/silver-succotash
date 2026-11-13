"""Background flattening, ink/red separation and the two restorations.

Purely photometric: the parchment background is estimated with a large grey
closing (which removes dark ink) and divided out, so low-frequency stains
disappear while ink keeps its shape. Nothing is painted in where a stain hides
the ink.
"""
import cv2
import numpy as np

TARGET = np.array([182, 214, 232], np.float32)      # BGR parchment tone
INK = np.array([28, 24, 22], np.float32)
RED = np.array([45, 60, 190], np.float32)


def _lab_L(bgr):
    return float(cv2.cvtColor(bgr.reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2LAB)[0, 0, 0])


def estimate_background(im, k):
    """Low-resolution background estimate; ``k`` is the downsampling factor."""
    h, w = im.shape[:2]
    small = cv2.resize(im, (max(1, w // k), max(1, h // k)), interpolation=cv2.INTER_AREA).astype(np.float32)
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    bg = cv2.medianBlur(bg.astype(np.uint8), 7).astype(np.float32)
    return cv2.GaussianBlur(bg, (0, 0), 3)


def _upsample_band(bg_small, W, y0, y1, k):
    """Upsample rows y0..y1 of the full-size background from bg_small."""
    sx = bg_small.shape[1] / W
    M = np.float32([[sx, 0, 0], [0, 1.0 / k, y0 / k]])
    return cv2.warpAffine(bg_small, M, (W, y1 - y0), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE)


def ink_red_maps(work, cfg):
    """Ink (black) and red-pigment maps (uint8, 0..255) for the working image."""
    k = max(2, int(round(cfg.target_spacing_px / 6)))
    bg_small = estimate_background(work, k)
    bg = np.maximum(cv2.resize(bg_small, (work.shape[1], work.shape[0]), interpolation=cv2.INTER_CUBIC), 1)
    flat = np.clip(work.astype(np.float32) / bg * TARGET, 0, 255).astype(np.uint8)
    lab = cv2.cvtColor(flat, cv2.COLOR_BGR2LAB).astype(np.float32)
    Lbg = _lab_L(TARGET)
    darkness = np.clip((Lbg - lab[..., 0]) / Lbg, 0, 1)
    redness = np.clip((lab[..., 1] - cfg.red_a_threshold) / cfg.red_a_range, 0, 1)
    ink = np.clip((darkness - 0.30) / 0.30, 0, 1) * (1 - 0.8 * redness)
    ink = cv2.GaussianBlur(ink, (0, 0), 0.6)
    red = np.clip(redness * np.clip((darkness - 0.05) / 0.2, 0, 1), 0, 1)
    red = cv2.GaussianBlur(red, (0, 0), 0.6)
    if cfg.staff_color == "ink":
        # experimental: dark ruling. Extract long horizontal structures from the ink map.
        L = int(cfg.target_spacing_px * 3)
        lines = cv2.morphologyEx((ink * 255).astype(np.uint8), cv2.MORPH_OPEN,
                                 cv2.getStructuringElement(cv2.MORPH_RECT, (L, 1)))
        red = lines.astype(np.float32) / 255
        ink = np.clip(ink - red, 0, 1)
    return (ink * 255).astype(np.uint8), (red * 255).astype(np.uint8)


def restore_full(src, staff_polylines, spacing_full, quality=82):
    """Return (restored_photo, clean_redraw) at full resolution, processed in strips.

    ``staff_polylines``: list of Nx2 arrays (full-res) drawn into the redraw so the
    ruling stays continuous where the pigment has faded.
    """
    H, W = src.shape[:2]
    k = max(4, int(round(spacing_full / 6)))
    bg_small = estimate_background(src, k)
    Lbg = _lab_L(TARGET)
    ab_t = cv2.cvtColor(TARGET.reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2LAB)[0, 0, 1:].astype(np.float32)
    linemask = np.zeros((H, W), np.uint8)
    lw = max(2, int(round(spacing_full / 20)))
    for pts in staff_polylines:
        cv2.polylines(linemask, [np.asarray(pts, np.int32)], False, 255, lw, cv2.LINE_AA)
    photo = np.zeros_like(src)
    redraw = np.zeros_like(src)
    STRIP, PAD = 1024, 64
    for y0 in range(0, H, STRIP):
        a, b = max(0, y0 - PAD), min(H, y0 + STRIP + PAD)
        im = src[a:b].astype(np.float32)
        bg = np.maximum(_upsample_band(bg_small, W, a, b, k), 1)
        flat = np.clip(im / bg * TARGET, 0, 255)
        flat = cv2.medianBlur(flat.astype(np.uint8), 3).astype(np.float32)
        lab = cv2.cvtColor(flat.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
        L = lab[..., 0]
        t = np.clip(L / Lbg, 0, 1.2)
        labp = lab.copy()
        labp[..., 0] = np.where(t < 1, Lbg * t ** 1.35, L)
        red = np.clip((lab[..., 1] - 140) / 30, 0, 1)
        wgt = np.clip(1 - red * 1.5, 0, 1)[..., None] * 0.6
        labp[..., 1:] = labp[..., 1:] * (1 - wgt) + ab_t * wgt
        p = cv2.cvtColor(np.clip(labp, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
        darkness = np.clip((Lbg - L) / Lbg, 0, 1)
        ink = cv2.GaussianBlur(np.clip((darkness - 0.30) / 0.30, 0, 1) * (1 - 0.8 * red), (0, 0), 1.0)
        redm = np.clip(red * np.clip((darkness - 0.05) / 0.2, 0, 1), 0, 1)
        redm = np.maximum(redm, linemask[a:b].astype(np.float32) / 255 * 0.85)
        redm = cv2.GaussianBlur(redm, (0, 0), 1.0)
        c = np.ones_like(im) * TARGET
        c = c * (1 - redm[..., None]) + RED * redm[..., None]
        c = c * (1 - ink[..., None]) + INK * ink[..., None]
        oa = y0 - a
        n = min(STRIP, H - y0)
        photo[y0:y0 + n] = p[oa:oa + n]
        redraw[y0:y0 + n] = c[oa:oa + n].astype(np.uint8)
    return photo, redraw
