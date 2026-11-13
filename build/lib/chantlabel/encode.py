"""Pitches, labels.json, Neon-style MEI 5.1 and the markdown transcription."""
import math
import re
import uuid
from collections import Counter

import numpy as np

from .neumes import pos_label

STEPS = 'cdefgab'


def pitch_of(k, clef_shape, clef_line):
    base = 4 * 7 + 0 if clef_shape == 'C' else 3 * 7 + 3   # c4 / f3 on the clef line
    p = base + (k - 2 * (clef_line - 1))
    return STEPS[p % 7], p // 7


def short(pos):
    return ('L' if pos.startswith('line') else 'S') + pos.split()[1]


def assemble(geo, neumes, clefs, flats, inv):
    """Reading-order element lists per stave in full-resolution coordinates.

    ``inv`` = full-res pixels per working pixel.
    """
    S = lambda v: int(round(v * inv))
    staves = []
    for si, s in enumerate(geo.staves):
        els = []
        for c in [c for c in clefs if c['stave'] == si]:
            ys, sp = geo.lines_at(si, c['x'])
            cy = ys[len(ys) - c['line']]
            els.append({'type': 'clef', 'shape': c['shape'], 'line': c['line'], 'x': c['x'],
                        'label': f"{c['shape']} clef, line {c['line']}",
                        'box': [S(c['x'] - 0.35 * sp), S(cy - 0.9 * sp), S(c['x'] + 0.35 * sp), S(cy + 0.9 * sp)],
                        'flag': c.get('flag', '')})
        for f in [f for f in flats if f['stave'] == si]:
            ys, sp = geo.lines_at(si, f['x'])
            yk = ys[-1] - f['k'] * sp / 2
            els.append({'type': 'accid', 'x': f['x'], 'label': 'flat (b)',
                        'box': [S(f['x'] - 0.25 * sp), S(yk - 0.9 * sp), S(f['x'] + 0.25 * sp), S(yk + 0.35 * sp)],
                        'flag': f.get('flag', '')})
        for n in [n for n in neumes if n['stave'] == si]:
            els.append({'type': 'neume', 'x': n['box'][0], 'n': n})
        els.sort(key=lambda e: e['x'])
        clef = None
        for e in els:
            if e['type'] == 'clef':
                clef = (e['shape'], e['line'])
            elif e['type'] == 'neume':
                clef = clef or ('C', len(s['lines']))
                n = e['n']
                e.update({'label': n['name'], 'box': [S(v) for v in n['box']], 'clef': f"{clef[0]}{clef[1]}",
                          'flag': '; '.join(n['flags']), 'notes': []})
                for i, h in enumerate(n['heads']):
                    pn, oc = pitch_of(h['k'], *clef)
                    tilt = 's' if n['name'] == 'virga' else ('se' if n['name'] == 'climacus' and i > 0 else None)
                    e['notes'].append({'pos': pos_label(h['k']), 'k': h['k'], 'pitch': f"{pn}{oc}", 'pname': pn, 'oct': oc,
                                       'box': [S(v) for v in h['box']], 'tilt': tilt,
                                       'flag': h.get('flag') or ''})
        lines = []
        XS = geo.XS
        m = (XS >= s['x0'] - 1) & (XS <= s['x1'] + 1)
        nl = len(s['lines'])
        for j, l in enumerate(s['lines']):
            lines.append({'line': nl - j, 'points': [[S(x), round(float(y) * inv, 1)] for x, y in zip(XS[m], np.asarray(l['y'])[m])],
                          'source': s['src'][j] if j < len(s['src']) else 'detected'})
        staves.append({'n': si + 1, 'lines': lines, 'elements': els, 'complete': s.get('complete', True)})
    return staves


def labels_json(staves, W, H, meta):
    out = {'image': {'width': W, 'height': H}, 'meta': meta, 'staves': [], 'notes_total': 0}
    for s in staves:
        els = []
        for e in s['elements']:
            d = {'type': e['type'], 'label': e['label'], 'box': e['box'], 'flag': e.get('flag', '')}
            if e['type'] == 'neume':
                d['clef'] = e['clef']
                d['notes'] = [{k: v for k, v in n.items() if k in ('pos', 'k', 'pitch', 'box', 'flag')} for n in e['notes']]
                out['notes_total'] += len(e['notes'])
            els.append(d)
        out['staves'].append({'n': s['n'], 'lines': s['lines'], 'elements': els})
    return out


def _tok(name):
    return re.sub(r'[^A-Za-z0-9_.-]+', '-', name).strip('-')


def mei(staves, geo, inv, W, H, title):
    pid = lambda p: f"{p}-{uuid.uuid4().hex[:12]}"
    zones = []

    def zone(box, rotate=None):
        zid = pid('zone')
        r = f' rotate="{rotate:.4f}"' if rotate is not None else ''
        zones.append(f'<zone xml:id="{zid}" ulx="{box[0]}" uly="{box[1]}" lrx="{box[2]}" lry="{box[3]}"{r}/>')
        return zid

    layer = []
    surface = pid('surface')
    for si, s in enumerate(staves):
        st = geo.staves[si]
        x0, x1 = st['x0'], st['x1']
        yt0, yt1 = geo.line_y(si, 0, x0), geo.line_y(si, 0, x1)
        yb0, yb1 = geo.line_y(si, -1, x0), geo.line_y(si, -1, x1)
        rot = math.degrees(math.atan2(((yt1 + yb1) - (yt0 + yb0)) / 2, x1 - x0))
        sbox = [int(round(v * inv)) for v in (x0, min(yt0, yt1), x1, max(yb0, yb1))]
        layer.append(f'<sb n="{si + 1}" xml:id="{pid("sb")}" facs="#{zone(sbox, rot)}"/>')
        for e in s['elements']:
            if e['type'] == 'clef':
                layer.append(f'<clef xml:id="{pid("clef")}" facs="#{zone(e["box"])}" shape="{e["shape"]}" line="{e["line"]}"/>')
            elif e['type'] == 'accid':
                layer.append(f'<accid xml:id="{pid("accid")}" facs="#{zone(e["box"])}" accid="f"/>')
            else:
                ncs = []
                for nc in e['notes']:
                    t = f' tilt="{nc["tilt"]}"' if nc['tilt'] else ''
                    ncs.append(f'<nc xml:id="{pid("nc")}" facs="#{zone(nc["box"])}" pname="{nc["pname"]}" oct="{nc["oct"]}"{t}/>')
                layer.append(f'<syllable xml:id="{pid("syllable")}">\n<neume xml:id="{pid("neume")}" facs="#{zone(e["box"])}" type="{_tok(e["label"])}">\n'
                             + '\n'.join(ncs) + '\n</neume>\n</syllable>')
    nl = len(geo.staves[0]['lines']) if geo.staves else 4
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<?xml-model href="https://music-encoding.org/schema/5.1/mei-all.rng" type="application/xml" schematypens="http://relaxng.org/ns/structure/1.0"?>
<mei xmlns="http://www.music-encoding.org/ns/mei" meiversion="5.1">
<meiHead xml:id="{pid('meihead')}">
<fileDesc xml:id="{pid('fd')}">
<titleStmt xml:id="{pid('ts')}"><title xml:id="{pid('t')}">{title}</title></titleStmt>
<pubStmt xml:id="{pid('ps')}"/>
</fileDesc>
</meiHead>
<music>
<facsimile xml:id="{pid('facs')}" type="transcription">
<surface xml:id="{surface}" ulx="0" uly="0" lrx="{W}" lry="{H}">
{chr(10).join(zones)}
</surface>
</facsimile>
<body>
<mdiv xml:id="{pid('mdiv')}">
<score xml:id="{pid('score')}">
<scoreDef xml:id="{pid('sd')}">
<staffGrp xml:id="{pid('sg')}">
<staffDef xml:id="{pid('sdef')}" n="1" notationtype="neume" lines="{nl}" clef.shape="C" clef.line="{nl}"/>
</staffGrp>
</scoreDef>
<section xml:id="{pid('sec')}">
<staff n="1" xml:id="{pid('staff')}">
<layer n="1" xml:id="{pid('layer')}">
<pb xml:id="{pid('pb')}" facs="#{surface}"/>
{chr(10).join(layer)}
</layer>
</staff>
</section>
</score>
</mdiv>
</body>
</music>
</mei>
'''


def markdown(lab, title, W, H):
    L = []
    A = L.append
    A(f'# {title}')
    A('')
    A('Automatic neume, staff-line and staff-position labels (chantlabel). Items marked ⚑ are low confidence or were set by hand.')
    A('')
    A('## Conventions')
    A('')
    A(f'- **Coordinates**: pixels in the full-resolution page image ({W} × {H}). Boxes are `[ulx, uly, lrx, lry]`.')
    A('- **Staff positions**: S0 = space below the bottom line, L1 = bottom line, S1, L2, … upward; extra lines continue the scheme (L0/S-1 below, L5/S5 above a four-line staff).')
    A('- **Pitches** come from the most recent clef to the left (C clef line = c4, F clef line = f3); positions do not depend on clefs.')
    A('- **Neume names**: punctum, virga, pes, clivis, torculus, porrectus, climacus, scandicus, distropha, tristropha, and `compound (…)` with the contour (u/d/s) for longer groups.')
    A('- Text is not transcribed; in the MEI each neume sits in its own `<syllable>` without `<syl>`.')
    A('')
    c = Counter(e['label'] for s in lab['staves'] for e in s['elements'] if e['type'] == 'neume')
    cl = Counter(e['label'] for s in lab['staves'] for e in s['elements'] if e['type'] != 'neume')
    A('## Summary')
    A('')
    A(f"- {len(lab['staves'])} staves, {sum(len(s['lines']) for s in lab['staves'])} staff lines.")
    A(f"- {lab['notes_total']} note heads in {sum(c.values())} neumes.")
    A('- Neume types: ' + ', '.join(f'{k} {v}' for k, v in c.most_common()))
    A('- Other glyphs: ' + ', '.join(f'{k} {v}' for k, v in cl.most_common()))
    for w in lab['meta'].get('warnings', []):
        A(f'- Warning: {w}')
    A('')
    A('## Flagged items (⚑)')
    A('')
    for s in lab['staves']:
        for e in s['elements']:
            if e.get('flag'):
                A(f"- Stave {s['n']}, {e['label']} at {e['box']}: {e['flag']}")
    A('')
    A('## Staff lines')
    A('')
    A('| Stave | Line | x range | y left | y mid | y right | source |')
    A('|---|---|---|---|---|---|---|')
    for s in lab['staves']:
        for l in s['lines']:
            p = l['points']; m = p[len(p) // 2]
            A(f"| {s['n']} | L{l['line']} | {p[0][0]}–{p[-1][0]} | {p[0][1]:.0f} | {m[1]:.0f} | {p[-1][1]:.0f} | {l['source']} |")
    A('')
    A('## Transcription by staff')
    A('')
    for s in lab['staves']:
        A(f"### Stave {s['n']}")
        A('')
        pos, pit = [], []
        for e in s['elements']:
            if e['type'] == 'clef':
                pos.append(f"[{e['label']}]"); pit.append(f"[{e['label'][0]}{e['label'][-1]}]")
            elif e['type'] == 'accid':
                pos.append('[b]'); pit.append('[b]')
            else:
                pos.append(' '.join(short(n['pos']) for n in e['notes'])); pit.append(' '.join(n['pitch'] for n in e['notes']))
        A('Positions, one group per neume: `' + ' | '.join(pos) + '`')
        A('')
        A('Pitches: `' + ' | '.join(pit) + '`')
        A('')
        A('| # | element | positions | pitches | box | note boxes | ⚑ |')
        A('|---|---|---|---|---|---|---|')
        for i, e in enumerate(s['elements'], 1):
            fl = '⚑ ' + e['flag'] if e.get('flag') else ''
            if e['type'] != 'neume':
                A(f"| {i} | {e['label']} | | | {e['box']} | | {fl} |"); continue
            A(f"| {i} | {e['label']} | {' '.join(short(n['pos']) for n in e['notes'])} | {' '.join(n['pitch'] for n in e['notes'])} | "
              f"{e['box']} | {' '.join(str(n['box']) for n in e['notes'])} | {fl} |")
        A('')
    return '\n'.join(L)
