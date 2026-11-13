"""Static zoomable review viewer: index.html + labels.json + image tiles."""
import json
import os
from importlib import resources

import cv2


def build_viewer(outdir, title, lab, layers, tile=2048, quality=80):
    """``layers``: dict name -> full-res BGR image; names among orig, photo, redraw."""
    os.makedirs(os.path.join(outdir, 't'), exist_ok=True)
    for name, im in layers.items():
        H, W = im.shape[:2]
        pv = cv2.resize(im, (2000, int(H * 2000 / W)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(os.path.join(outdir, 't', f'{name}_preview.jpg'), pv, [cv2.IMWRITE_JPEG_QUALITY, 82])
        q = 72 if name == 'photo' else quality
        for ty in range(0, H, tile):
            for tx in range(0, W, tile):
                cv2.imwrite(os.path.join(outdir, 't', f'{name}_{tx // tile}_{ty // tile}.jpg'),
                            im[ty:ty + tile, tx:tx + tile], [cv2.IMWRITE_JPEG_QUALITY, q])
    lab = dict(lab); lab['meta'] = dict(lab.get('meta', {}), layers=list(layers))
    with open(os.path.join(outdir, 'labels.json'), 'w') as f:
        json.dump(lab, f)
    tpl = resources.files('chantlabel').joinpath('viewer_template/index.html').read_text()
    safe = title.replace('<', '&lt;').replace('>', '&gt;')
    with open(os.path.join(outdir, 'index.html'), 'w') as f:
        f.write(tpl.replace('__TITLE__', safe).replace('__TILE__', str(tile)))
