"""Command line interface.

  chantlabel run PAGE.pdf -o out/ [--corrections PAGE.corrections.json]
  chantlabel batch pages/ -o out/            # every .pdf/.jpg/.png/.tif; picks up <stem>.corrections.json
  chantlabel validate out/PAGE_neumes.mei [--labels out/PAGE_labels.json]
  chantlabel evaluate pred.mei gold.mei
"""
import argparse
import csv
import glob
import json
import os
import sys

from .config import Config

EXTS = ('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff')


def _cfg(path):
    cfg = Config()
    if path:
        for k, v in json.load(open(path)).items():
            if not hasattr(cfg, k):
                sys.exit(f"unknown config key: {k}")
            setattr(cfg, k, tuple(v) if isinstance(v, list) else v)
    return cfg


def _flags(p):
    p.add_argument('--config', help='JSON file overriding Config fields')
    p.add_argument('--no-restore', action='store_true', help='skip the full-resolution restorations')
    p.add_argument('--no-images', action='store_true', help='skip the labelled step images')
    p.add_argument('--no-viewer', action='store_true', help='skip the zoomable viewer')
    p.add_argument('--review', action='store_true', help='also write one labelled crop per stave')


def main(argv=None):
    ap = argparse.ArgumentParser(prog='chantlabel', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run', help='label one page')
    r.add_argument('input'); r.add_argument('-o', '--out', required=True)
    r.add_argument('--corrections'); r.add_argument('--title'); _flags(r)
    b = sub.add_parser('batch', help='label every page in a folder')
    b.add_argument('folder'); b.add_argument('-o', '--out', required=True); _flags(b)
    v = sub.add_parser('validate', help='schema-validate an MEI file; optional Verovio position check')
    v.add_argument('mei'); v.add_argument('--labels'); v.add_argument('--rng')
    e = sub.add_parser('evaluate', help='compare a predicted MEI with a corrected one')
    e.add_argument('pred'); e.add_argument('gold')
    a = ap.parse_args(argv)

    if a.cmd in ('run', 'batch'):
        from .pipeline import run
        cfg = _cfg(a.config)
        kw = dict(cfg=cfg, restore=not a.no_restore, images=not a.no_images, viewer=not a.no_viewer, review=a.review)
        if a.cmd == 'run':
            run(a.input, a.out, corrections=a.corrections, title=a.title, **kw)
            return
        files = sorted(f for f in glob.glob(os.path.join(a.folder, '*')) if f.lower().endswith(EXTS))
        rows = []
        for f in files:
            stem = os.path.splitext(f)[0]
            corr = stem + '.corrections.json'
            try:
                rows.append(run(f, os.path.join(a.out, os.path.basename(stem)),
                                corrections=corr if os.path.exists(corr) else None, **kw))
            except Exception as ex:      # keep going on a large set
                print(f"  FAILED {f}: {ex}")
                rows.append({'page': os.path.basename(stem), 'error': str(ex)})
        keys = ['page', 'staves', 'staff_lines', 'neumes', 'note_heads', 'flagged', 'clefs', 'seconds', 'error']
        with open(os.path.join(a.out, 'batch_summary.csv'), 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=keys, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
        print(f"wrote {os.path.join(a.out, 'batch_summary.csv')}")
    elif a.cmd == 'validate':
        from . import validate as V
        ok, msg = V.schema(a.mei, a.rng)
        print('schema:', {True: 'valid', False: 'INVALID', None: 'skipped'}[ok], msg)
        if a.labels:
            ok2, msg2 = V.verovio_positions(a.mei, a.labels)
            print('verovio positions:', {True: 'ok', False: 'MISMATCH', None: 'skipped'}[ok2], msg2)
    elif a.cmd == 'evaluate':
        from .evaluate import evaluate
        print(json.dumps(evaluate(a.pred, a.gold), indent=1))


if __name__ == '__main__':
    main()
