"""Compare a predicted MEI with a corrected ("gold") MEI of the same page.

Both files must carry facsimile zones in the same pixel space (as files produced
here, or the same files after correction in Neon). Note heads are matched by the
distance between zone centres; reported:

- head detection precision / recall / F1
- pitch accuracy on matched heads (pname + oct)
- staff-position accuracy is implied by pitch accuracy when the clefs agree
- neume grouping: F1 over pairs of matched heads that share a neume
"""
import xml.etree.ElementTree as ET

NS = {'m': 'http://www.music-encoding.org/ns/mei'}
XMLID = '{http://www.w3.org/XML/1998/namespace}id'


def read_mei(path):
    root = ET.parse(path).getroot()
    zones = {}
    for z in root.iter('{%s}zone' % NS['m']):
        zones[z.get(XMLID)] = tuple(float(z.get(a)) for a in ('ulx', 'uly', 'lrx', 'lry'))
    heads = []
    for ni, neume in enumerate(root.iter('{%s}neume' % NS['m'])):
        for nc in neume.findall('m:nc', NS):
            z = zones.get((nc.get('facs') or '').lstrip('#'))
            if z is None: continue
            heads.append({'neume': ni, 'pitch': f"{nc.get('pname')}{nc.get('oct')}",
                          'cx': (z[0] + z[2]) / 2, 'cy': (z[1] + z[3]) / 2, 'size': max(z[2] - z[0], z[3] - z[1])})
    return heads


def match(pred, gold, tol=0.5):
    pairs = []
    for i, g in enumerate(gold):
        for j, p in enumerate(pred):
            d = ((g['cx'] - p['cx']) ** 2 + (g['cy'] - p['cy']) ** 2) ** 0.5
            if d < tol * max(g['size'], p['size']):
                pairs.append((d, i, j))
    pairs.sort()
    ug, up, m = set(), set(), []
    for d, i, j in pairs:
        if i in ug or j in up: continue
        ug.add(i); up.add(j); m.append((i, j))
    return m


def evaluate(pred_path, gold_path):
    pred, gold = read_mei(pred_path), read_mei(gold_path)
    m = match(pred, gold)
    tp = len(m)
    prec = tp / len(pred) if pred else 0.0
    rec = tp / len(gold) if gold else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    pitch_ok = sum(gold[i]['pitch'] == pred[j]['pitch'] for i, j in m)
    # grouping: pairs of matched heads that are neighbours in the gold reading order
    same_g, same_p, both = 0, 0, 0
    mm = sorted(m)
    for (i1, j1), (i2, j2) in zip(mm, mm[1:]):
        g = gold[i1]['neume'] == gold[i2]['neume']
        p = pred[j1]['neume'] == pred[j2]['neume']
        same_g += g; same_p += p; both += g and p
    gp = both / same_p if same_p else 0.0
    gr = both / same_g if same_g else 0.0
    return {'gold_heads': len(gold), 'pred_heads': len(pred), 'matched': tp,
            'head_precision': round(prec, 4), 'head_recall': round(rec, 4), 'head_f1': round(f1, 4),
            'pitch_accuracy_on_matched': round(pitch_ok / tp, 4) if tp else 0.0,
            'grouping_precision': round(gp, 4), 'grouping_recall': round(gr, 4),
            'grouping_f1': round(2 * gp * gr / (gp + gr), 4) if gp + gr else 0.0}
