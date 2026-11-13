"""End-to-end run on one page."""
import json
import os
import time

import cv2
import numpy as np

from . import corrections as C
from .clefs import guess_start_clefs
from .config import Config
from .encode import assemble, labels_json, markdown, mei
from .heads import detect_heads
from .io import load_page
from .neumes import build_neumes, drop_near_clefs
from .restore import ink_red_maps, restore_full
from .staves import StaffGeometry, detect_staves, estimate_spacing


def measure_spacing(src, cfg):
    H, W = src.shape[:2]
    f = 2000.0 / W
    small = cv2.resize(src, (2000, int(H * f)), interpolation=cv2.INTER_AREA)
    _, red = ink_red_maps(small, cfg)
    return estimate_spacing(red) / f


def run(input_path, outdir, corrections=None, cfg=None, title=None, restore=True, images=True, viewer=True,
        review=False, log=print):
    cfg = cfg or Config()
    t0 = time.time()
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    title = title or stem
    warnings = []
    warn = lambda m: (warnings.append(m), log('  warning: ' + m))

    src = load_page(input_path)
    H, W = src.shape[:2]
    spacing_full = measure_spacing(src, cfg)
    scale = cfg.working_scale if cfg.working_scale > 0 else cfg.target_spacing_px / spacing_full
    inv = 1.0 / scale
    work = cv2.resize(src, (int(round(W * scale)), int(round(H * scale))), interpolation=cv2.INTER_AREA)
    log(f"{stem}: {W}x{H}, staff spacing {spacing_full:.1f}px, working scale {scale:.3f}")

    ink, red = ink_red_maps(work, cfg)
    det = detect_staves(red, cfg)
    geo = StaffGeometry(det)
    for i, s in enumerate(geo.staves):
        if len(s['lines']) != cfg.lines_per_staff:
            warn(f"stave {i + 1} has {len(s['lines'])} lines (expected {cfg.lines_per_staff})")
        if 'interpolated' in s['src']:
            log(f"  stave {i + 1}: {s['src'].count('interpolated')} faint line(s) interpolated")
        if s.get('x0_extended'):
            warn(f"stave {i + 1}: ruling faint at the left end; extent taken from the other staves")
        if s.get('x1_extended'):
            warn(f"stave {i + 1}: ruling faded at the right end; extent taken from the other staves")
    bw = (ink > cfg.ink_threshold).astype(np.uint8)
    heads = detect_heads(bw, geo, cfg)
    log(f"  {len(geo.staves)} staves, {len(heads)} head candidates")

    corr = C.load(corrections) if isinstance(corrections, (str, type(None))) else corrections
    heads = C.apply_head_edits(heads, corr, scale, cfg.target_spacing_px, warn)

    clefs = guess_start_clefs(bw, geo, cfg) if cfg.auto_clefs else []
    manual = corr.get('clefs', [])
    manual_staves = {c['stave'] - 1 for c in manual}
    clefs = [c for c in clefs if c['stave'] not in manual_staves]
    for c in manual:
        clefs.append({'stave': c['stave'] - 1, 'shape': c.get('shape', 'C'), 'line': int(c['line']),
                      'x': c['x'] * scale, 'flag': c.get('flag', '')})
    flats = [{'stave': f['stave'] - 1, 'x': f['x'] * scale, 'k': int(f['pos']), 'flag': f.get('flag', 'flat sign')}
             for f in corr.get('flats', [])]
    heads = drop_near_clefs(heads, clefs, geo, cfg)
    ann = C.head_annotations(heads, corr, scale, cfg.target_spacing_px, warn)
    neumes = build_neumes(heads, bw, geo, cfg, ann)

    staves = assemble(geo, neumes, clefs, flats, inv)
    meta = {'source': os.path.basename(input_path), 'staff_spacing_px': round(spacing_full, 2),
            'working_scale': round(scale, 5), 'corrections': os.path.basename(corrections) if isinstance(corrections, str) else None,
            'warnings': warnings, 'config': cfg.to_dict()}
    lab = labels_json(staves, W, H, meta)
    base = os.path.join(outdir, stem)
    with open(base + '_labels.json', 'w') as f:
        json.dump(lab, f)
    with open(base + '_neumes.mei', 'w') as f:
        f.write(mei(staves, geo, inv, W, H, f"{title} - automatic neume labelling"))
    with open(base + '_labels.md', 'w') as f:
        f.write(markdown(lab, title, W, H))

    q = [cv2.IMWRITE_JPEG_QUALITY, cfg.jpeg_quality]
    layers = {'orig': src}
    if images or review:
        from .render import label_images, review_crops
        if images:
            for name, im in label_images(src, lab, spacing_full).items():
                cv2.imwrite(f"{base}_{name}.jpg", im, q)
        if review:
            rd = os.path.join(outdir, 'review'); os.makedirs(rd, exist_ok=True)
            for name, im in review_crops(src, lab, spacing_full).items():
                cv2.imwrite(os.path.join(rd, f"{stem}_{name}.jpg"), im, q)
    if restore:
        polys = [l['points'] for s in lab['staves'] for l in s['lines']]
        photo, redraw = restore_full(src, polys, spacing_full)
        cv2.imwrite(base + '_restored_photo.jpg', photo, [cv2.IMWRITE_JPEG_QUALITY, 80])
        cv2.imwrite(base + '_clean_redraw.jpg', redraw, q)
        layers.update(photo=photo, redraw=redraw)
    if viewer:
        from .viewer import build_viewer
        build_viewer(os.path.join(outdir, stem + '_viewer'), title, lab, layers, tile=cfg.viewer_tile)

    n_neumes = sum(1 for s in lab['staves'] for e in s['elements'] if e['type'] == 'neume')
    n_flag = sum(1 for s in lab['staves'] for e in s['elements'] if e.get('flag'))
    summary = {'page': stem, 'staves': len(lab['staves']), 'staff_lines': sum(len(s['lines']) for s in lab['staves']),
               'neumes': n_neumes, 'note_heads': lab['notes_total'], 'flagged': n_flag,
               'clefs': sum(1 for s in lab['staves'] for e in s['elements'] if e['type'] == 'clef'),
               'warnings': warnings, 'seconds': round(time.time() - t0, 1)}
    with open(base + '_summary.json', 'w') as f:
        json.dump(summary, f, indent=1)
    log(f"  {summary['note_heads']} heads in {n_neumes} neumes, {n_flag} flagged, {summary['seconds']}s")
    return summary
