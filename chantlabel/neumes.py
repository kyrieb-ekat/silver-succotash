"""Staff positions, neume grouping and naming."""
import cv2
import numpy as np

NAMES = {'': 'punctum', 'u': 'pes', 'd': 'clivis', 's': 'distropha', 'uu': 'scandicus', 'dd': 'climacus',
         'ud': 'torculus', 'du': 'porrectus', 'ss': 'tristropha', 'udd': 'torculus (pes subbipunctis)',
         'ddd': 'climacus', 'dud': 'porrectus flexus', 'udu': 'torculus resupinus', 'ddu': 'climacus resupinus',
         'uud': 'scandicus flexus', 'uuu': 'scandicus', 'dddd': 'climacus'}


def pos_label(k):
    """Your scheme: 0 = bottom line = 'line 1'; -1 = 'space 0'; 1 = 'space 1' ..."""
    return f"line {k // 2 + 1}" if k % 2 == 0 else f"space {(k + 1) // 2}"


def drop_near_clefs(heads, clefs, geo, cfg):
    out = []
    for h in heads:
        hit = False
        for c in clefs:
            if c['stave'] != h['stave']: continue
            ys, sp = geo.lines_at(c['stave'], c['x'])
            cy = ys[len(ys) - c['line']]
            if abs(h['cx'] - c['x']) < cfg.clef_drop_rx_sp * sp and abs(h['cy'] - cy) < cfg.clef_drop_ry_sp * sp:
                hit = True; break
        if not hit: out.append(h)
    return out


def build_neumes(heads, bw, geo, cfg, ann):
    H, W = bw.shape
    for h in heads:
        if ann['flag'].get(h['id']): h['flag'] = ann['flag'][h['id']]
        ys, sp = geo.lines_at(h['stave'], h['cx'])
        kf = (ys[-1] - h['cy']) / (sp / 2)
        h['k'] = ann['pos'].get(h['id'], int(round(kf)))
        h['resid'] = float(kf - h['k'])
        h['sp'] = sp
        hs = int(round(sp * 0.36))
        h['box'] = [int(h['cx'] - hs), int(h['cy'] - hs), int(h['cx'] + hs), int(h['cy'] + hs)]
    # merge two peaks found on one wide head
    heads = sorted(heads, key=lambda h: (h['stave'], h['cx']))
    merged = []
    for h in heads:
        m = merged[-1] if merged else None
        if m and m['stave'] == h['stave'] and m['k'] == h['k'] and abs(h['cx'] - m['cx']) < cfg.duplicate_dx_sp * h['sp'] \
                and abs(h['cy'] - m['cy']) < 0.3 * h['sp']:
            x0 = min(m['box'][0], h['box'][0]); x1 = max(m['box'][2], h['box'][2])
            m['box'] = [x0, m['box'][1], x1, m['box'][3]]; m['cx'] = (x0 + x1) // 2; m['wide'] = True
            if h.get('flag') and not m.get('flag'): m['flag'] = h['flag']
            continue
        merged.append(h)
    heads = merged
    # descending tail (virga)
    for h in heads:
        sp = h['sp']; best = 0
        for dx in range(-int(0.45 * sp), int(0.45 * sp) + 1):
            x = int(np.clip(h['cx'] + dx, 1, W - 2)); y = int(h['cy'] + 0.3 * sp); n = 0
            while y < H and n < 2 * sp and bw[y, x - 1:x + 2].max():
                y += 1; n += 1
            best = max(best, n)
        h['tail'] = best / sp
    # connectivity inside the staff bands only (stems touch the text below)
    band = np.zeros_like(bw)
    for si, s in enumerate(geo.staves):
        for x in range(max(0, int(s['x0'] - 3.2 * cfg.target_spacing_px)), min(W, int(s['x1'] + 1.6 * cfg.target_spacing_px))):
            ys, sp = geo.lines_at(si, x)
            band[max(0, int(ys[0] - 1.6 * sp)):min(H, int(ys[-1] + 0.62 * sp)), x] = 1
    _, lab = cv2.connectedComponents(bw * band, 8)
    for h in heads:
        h['comp'] = int(lab[min(H - 1, h['cy']), min(W - 1, h['cx'])])

    parent = {h['id']: h['id'] for h in heads}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a

    forced = {}
    for gi, g in enumerate(ann['groups']):
        for i in g: forced[i] = gi
    cmin, cmax = cfg.climacus_dx_sp
    for si in range(len(geo.staves)):
        ns = sorted([h for h in heads if h['stave'] == si and h['id'] not in forced], key=lambda h: h['cx'])
        for i, a in enumerate(ns):
            for b in ns[i + 1:i + 6]:
                if b['cx'] - a['cx'] > 1.6 * a['sp']: break
                same = a['comp'] == b['comp'] and a['comp'] != 0
                diag = (cmin * a['sp'] < b['cx'] - a['cx'] < cmax * a['sp']) and (1 <= a['k'] - b['k'] <= 2) \
                    and abs(b['cy'] - a['cy']) < 0.75 * a['sp']
                if same or diag:
                    parent[find(a['id'])] = find(b['id'])
    groups = {}
    for h in heads:
        key = ('f', forced[h['id']]) if h['id'] in forced else ('a', find(h['id']))
        groups.setdefault(key, []).append(h)

    def order(g):
        g = sorted(g, key=lambda h: h['cx'])
        out, i = [], 0
        while i < len(g):
            col, j = [g[i]], i + 1
            while j < len(g) and g[j]['cx'] - g[i]['cx'] < cfg.stack_dx_sp * g[i]['sp']:
                col.append(g[j]); j += 1
            out += sorted(col, key=lambda h: h['k']); i = j
        return out

    final = []
    for key, g in groups.items():
        g = order(g)
        if key[0] == 'f':
            final.append(g); continue
        cur = [g[0]]
        for a, b in zip(g, g[1:]):
            if b['cx'] - a['cx'] > cfg.group_gap_sp * a['sp']:
                final.append(cur); cur = [b]
            else:
                cur.append(b)
        final.append(cur)

    neumes = []
    for g in final:
        contour = ''.join('u' if b['k'] > a['k'] else 'd' if b['k'] < a['k'] else 's' for a, b in zip(g, g[1:]))
        name = NAMES.get(contour, f'compound ({contour})')
        if len(g) == 1:
            h = g[0]
            virga = ann['stem'].get(h['id'], h['tail'] > cfg.virga_tail_sp)
            name = 'virga' if virga else 'punctum'
        if len(g) >= 3 and set(contour) == {'d'}:
            name = 'climacus'
        box = [min(h['box'][0] for h in g), min(h['box'][1] for h in g), max(h['box'][2] for h in g), max(h['box'][3] for h in g)]
        flags = sorted({h.get('flag', '') for h in g} - {''})
        neumes.append({'stave': g[0]['stave'], 'name': name, 'contour': contour, 'heads': g, 'box': box, 'flags': flags})
    neumes.sort(key=lambda n: (n['stave'], n['box'][0]))
    return neumes
