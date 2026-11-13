"""Manual corrections, keyed by position in the full-resolution image.

Coordinates refer to the full-resolution page (the same pixel space as the MEI
facsimile and labels.json), so a corrections file stays valid when the detector
changes. Head references match the nearest detected head within ``tol_sp``
staff spaces. See README for the format.
"""
import json


def load(path):
    if not path:
        return {}
    with open(path) as f:
        return json.load(f)


class Resolver:
    def __init__(self, heads, scale, sp, tol_sp=0.5):
        self.heads, self.scale, self.tol = heads, scale, tol_sp * sp

    def to_work(self, ref):
        return ref['x'] * self.scale, ref['y'] * self.scale

    def find(self, ref, stave=None):
        x, y = self.to_work(ref)
        st = ref.get('stave', stave)
        best, bd = None, 1e18
        for h in self.heads:
            if st is not None and h['stave'] != st - 1: continue
            d = (h['cx'] - x) ** 2 + (h['cy'] - y) ** 2
            if d < bd: best, bd = h, d
        if best is None or bd ** 0.5 > self.tol:
            return None
        return best


def apply_head_edits(heads, corr, scale, sp, warn):
    """Drop / add heads. Returns new head list (ids preserved, added heads get new ids)."""
    res = Resolver(heads, scale, sp)
    drop = set()
    for ref in corr.get('drop', []):
        h = res.find(ref)
        if h is None: warn(f"drop: no head near {ref}")
        else: drop.add(h['id'])
    heads = [h for h in heads if h['id'] not in drop]
    nid = max([h['id'] for h in heads] + [-1]) + 1
    for a in corr.get('add', []):
        heads.append({'id': nid, 'stave': a['stave'] - 1, 'cx': int(a['x'] * scale), 'cy': int(a['y'] * scale),
                      'dt': 0.0, 'added': True,
                      'flag': a.get('flag', 'added by hand; position uncertain')})
        nid += 1
    return heads


def head_annotations(heads, corr, scale, sp, warn):
    """Flags, position overrides, stem overrides and forced groups, resolved to head ids."""
    res = Resolver(heads, scale, sp)
    out = {'flag': {}, 'pos': {}, 'stem': {}, 'groups': []}
    for f in corr.get('flag', []):
        h = res.find(f)
        if h is None: warn(f"flag: no head near {f}")
        else: out['flag'][h['id']] = f.get('note', 'flagged')
    for p in corr.get('pos', []):
        h = res.find(p)
        if h is None: warn(f"pos: no head near {p}")
        else: out['pos'][h['id']] = int(p['k'])
    for s in corr.get('stem', []):
        h = res.find(s)
        if h is None: warn(f"stem: no head near {s}")
        else: out['stem'][h['id']] = bool(s.get('virga', True))
    for g in corr.get('group', []):
        ids = []
        for ref in g:
            h = res.find(ref)
            if h is None: warn(f"group: no head near {ref}")
            else: ids.append(h['id'])
        if ids: out['groups'].append(ids)
    return out
