#!/usr/bin/env python3
"""Syvyysruudukko yöajon kaikuluotaimelle.

Hakee Traficomin avoimesta WFS-palvelusta syvyysalueet (DepthArea_A) ja
luodatut syvyydet (Sounding_P) yöajon alueelta, laskee niistä 20 m:n
syvyysruudukon ja kirjoittaa sen src/app.html:ään merkkien
/* SYV-DATA */ ... /* /SYV-DATA */ väliin (zlib + base64).

Syvyys ruudussa: syvyysalueen rajojen (DRVAL1..DRVAL2) välillä interpoloidaan
etäisyyden mukaan matalampaan ja syvempään alueeseen; lähellä luotauspisteitä
arvoa vedetään luodattuun syvyyteen. Tavu = syvyys * 5 (0,2 m tarkkuus),
255 = maa tai ei tietoa.

Aineisto: © Traficom, CC BY 4.0. Ei navigointikäyttöön.
Käyttö:  python3 tools/syvyys.py [--cache hakemisto]   ja sitten ./build.sh
"""
import base64, json, math, os, re, sys, urllib.request, zlib
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

LAT0, LON0 = 60.1238645, 24.91023761          # Koirakari (sama kuin KOIRA.origin)
KX = 111320 * math.cos(math.radians(LAT0))
S, W, N, E = 60.086, 24.826, 60.194, 25.058   # ruudukon rajat
CELL = 20.0
WFS = 'https://julkinen.traficom.fi/inspirepalvelu/rajoitettu/wfs'
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, '..', 'src', 'app.html')

def xy(lon, lat):
    return (lon - LON0) * KX, (lat - LAT0) * 110540

X0, Y0 = xy(W, S)
X1, Y1 = xy(E, N)
NX, NY = int(math.ceil((X1 - X0) / CELL)), int(math.ceil((Y1 - Y0) / CELL))

def fetch(layer, cache):
    fn = cache and os.path.join(cache, layer + '.json')
    if fn and os.path.exists(fn):
        return json.load(open(fn))
    feats, start = [], 0
    while True:
        u = (f'{WFS}?service=WFS&version=2.0.0&request=GetFeature&typeNames=rajoitettu:{layer}'
             f'&outputFormat=application/json&srsName=EPSG:4326&bbox={W},{S},{E},{N},EPSG:4326'
             f'&count=1000&startIndex={start}&sortBy=IDENTIFIER')
        d = json.load(urllib.request.urlopen(u, timeout=180))
        feats += d['features']
        print(f'  {layer}: {len(feats)}/{d.get("numberMatched")}', file=sys.stderr)
        if len(d['features']) < 1000:
            break
        start += 1000
    if fn:
        os.makedirs(cache, exist_ok=True)
        json.dump(feats, open(fn, 'w'))
    return feats

def px(lon, lat):
    x, y = xy(lon, lat)
    return (x - X0) / CELL, (Y1 - y) / CELL      # kuvan rivi 0 = pohjoisreuna

def rings(geom):
    if geom['type'] == 'Polygon':
        return [geom['coordinates']]
    if geom['type'] == 'MultiPolygon':
        return geom['coordinates']
    return []

def area(ring):
    a = 0
    for (x1, y1, *_), (x2, y2, *_) in zip(ring, ring[1:]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2

def main():
    cache = sys.argv[sys.argv.index('--cache') + 1] if '--cache' in sys.argv else None
    areas = fetch('DepthArea_A', cache)
    snd = fetch('Sounding_P', cache)
    # syvyysalueet ruudukkoon reikineen; reiät, joita mikään alue ei täytä, ovat maata
    polys = []
    for f in areas:
        p = f['properties']
        try:
            d1, d2 = float(p['DRVAL1']), float(p['DRVAL2'] if p['DRVAL2'] is not None else float(p['DRVAL1']) + 20)
        except (TypeError, ValueError):
            continue
        for poly in rings(f['geometry']):
            polys.append((area(poly[0]), max(0, d1), max(0.5, d2), poly))
    polys.sort(key=lambda t: -t[0])             # isot ensin, pienet päälle
    ci = np.zeros((NY, NX), dtype=np.int32)
    levels = [(None, None)]
    for _, d1, d2, poly in polys:
        levels.append((d1, d2))
        im = Image.new('1', (NX, NY), 0)
        dr = ImageDraw.Draw(im)
        dr.polygon([px(c[0], c[1]) for c in poly[0]], fill=1)
        for hole in poly[1:]:                          # saaret ja muut alueet
            dr.polygon([px(c[0], c[1]) for c in hole], fill=0)
        ci[np.array(im, dtype=bool)] = len(levels) - 1
    lv = np.array([(-1, 0)] + levels[1:], dtype=float)
    d1 = lv[ci, 0]; d2 = lv[ci, 1]
    land = ci == 0
    depth = np.full(ci.shape, np.nan)
    for v in sorted(set(d1[~land])):
        m = (d1 == v) & ~land
        shallow = land | (d2 <= v + 1e-6)             # matalampi alue tai maa
        deep = ~land & (d1 >= d2[m].max() - 1e-6) if m.any() else None
        ds = ndimage.distance_transform_edt(~shallow) * CELL
        hi = d2[m]
        if deep is not None and deep.any():
            dd = ndimage.distance_transform_edt(~deep) * CELL
            t = ds[m] / np.maximum(ds[m] + dd[m], 1)
        else:
            t = np.minimum(ds[m] / 400, 1) * .6
        depth[m] = v + (hi - v) * np.clip(t, 0, 1)
    # luotaukset: vedetään lähiruutuja kohti luodattua arvoa (IDW 60 m säteellä)
    acc = np.zeros(ci.shape); wsum = np.zeros(ci.shape)
    R = 3
    for f in snd:
        g = f['geometry']['coordinates']
        dep = f['properties'].get('DEPTH')
        if dep is None:
            continue
        c, r = px(g[0], g[1])
        ic, ir = int(c), int(r)
        for rr in range(ir - R, ir + R + 1):
            for cc in range(ic - R, ic + R + 1):
                if 0 <= rr < NY and 0 <= cc < NX and not land[rr, cc]:
                    dist = math.hypot(cc + .5 - c, rr + .5 - r)
                    if dist <= R:
                        w = 1 / (0.3 + dist) ** 2
                        acc[rr, cc] += w * float(dep); wsum[rr, cc] += w
    has = wsum > 0
    blend = np.clip(wsum / 4, 0, 1)
    sv = np.where(has, acc / np.maximum(wsum, 1e-9), 0)
    sv = np.clip(sv, d1 - 0.3, d2 + 0.3)
    depth = np.where(has, depth * (1 - blend) + sv * blend, depth)
    out = np.where(land | np.isnan(depth), 255, np.clip(np.round(depth * 5), 0, 254)).astype(np.uint8)
    raw = zlib.compress(out.tobytes(), 9)
    b64 = base64.b64encode(raw).decode()
    js = (f'const SYV = {{ x0:{X0:.1f}, y1:{Y1:.1f}, cell:{CELL:g}, nx:{NX}, ny:{NY}, '
          f'src:\'Traficom, syvyysalueet ja luotaukset (CC BY 4.0)\', z:\'{b64}\' }};')
    s = open(APP, encoding='utf-8').read()
    s2, n = re.subn(r'/\* SYV-DATA \*/.*?/\* /SYV-DATA \*/', lambda _: '/* SYV-DATA */' + js + '/* /SYV-DATA */', s, flags=re.S)
    if n != 1:
        sys.exit('merkkejä /* SYV-DATA */ ei löytynyt src/app.html:stä')
    open(APP, 'w', encoding='utf-8').write(s2)
    wet = (~land).sum()
    print(f'ruudukko {NX}×{NY} ({CELL:g} m), vettä {wet} ruutua, {len(polys)} aluetta, {len(snd)} luotausta, '
          f'{len(b64) / 1024:.0f} kt, syvin {np.nanmax(depth):.1f} m')

if __name__ == '__main__':
    main()
