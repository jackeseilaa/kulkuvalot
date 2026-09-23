#!/usr/bin/env python3
"""Hakee Koirakarin sektoriloiston ympäristön aineiston ja kirjoittaa sen src/app.html-tiedostoon.

Lähteet:
  - Väylävirasto, avoin rajapinta (CC BY 4.0): turvalaitteet, loistot, valosektorit, navigointilinjat
  - OpenStreetMap (ODbL): rantaviivat

Aja: python3 tools/koirakari.py   (ja sen jälkeen ./build.sh)
"""
import json, math, re, sys, time, urllib.request, urllib.parse
from pathlib import Path

LIGHT_NO = '11430'                    # Koirakari
BBOX = (24.85, 60.085, 24.97, 60.15)  # lon0, lat0, lon1, lat1
COAST_BBOX = (60.095, 24.86, 60.155, 24.96)
FAIRWAYS = {'4675', '4610', '4710'}
API = 'https://avoinapi.vaylapilvi.fi/vaylatiedot/ogc/features/v1/collections/vesivaylatiedot:{}/items?f=json&limit=5000&bbox={}'
UA = {'User-Agent': 'kulkuvalot-harjoitus/1.0'}


def get(url, data=None):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def feats(name):
    return get(API.format(name, ','.join(map(str, BBOX))))['features']


def parse_seq(t):
    """'6*(0,15+0,45) + 2,00 + 4,40=10,00 s' -> [[0.15,1],[0.45,0],...]"""
    if not t or t.startswith('-'):
        return None
    left = t.split('=')[0].replace(',', '.').replace(' ', '')
    parts, depth, cur = [], 0, ''
    for ch in left:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == '+' and depth == 0:
            parts.append(cur); cur = ''
        else:
            cur += ch
    parts.append(cur)
    seq, trailing, grouped = [], [], False
    for p in parts:
        m = re.match(r'(\d+)\*\((.+)\)', p)
        if m:
            a, b = (float(x) for x in m.group(2).split('+'))
            seq += [[a, 1], [b, 0]] * int(m.group(1)); grouped = True
        else:
            trailing.append(float(p))
    if grouped and len(trailing) == 1:
        seq.append([trailing[0], 0])
    else:
        for i, d in enumerate(trailing):
            seq.append([d, 1 if i % 2 == 0 else 0])
    return [[round(d, 2), s] for d, s in seq]


def main():
    tl = feats('turvalaitteet_uusi')
    lo = feats('loistot_uusi')
    vs = feats('valosektorit_uusi')
    nl = feats('navigointilinjat_uusi')

    main_f = next(f for f in tl if f['properties']['turvalaitenumero'] == LIGHT_NO)
    lon0, lat0 = main_f['geometry']['coordinates'][0]
    kx = 111320 * math.cos(math.radians(lat0)); ky = 110540
    P = lambda lon, lat: [round((lon - lon0) * kx), round((lat - lat0) * ky)]

    lights = {}
    for f in lo:
        p = f['properties']
        if p.get('laji') == 'Päivävalo':
            continue
        lights.setdefault(str(p['turvalaitenumero']), p)
    sectors = {}
    for f in vs:
        p = f['properties']
        s = sectors.setdefault(str(p['tlnumero']), [])
        item = [p['alkukulma'], p['loppukulma'], p['vari']]
        if item not in s:
            s.append(item)

    out_lights = []
    for f in tl:
        p = f['properties']
        n = p['turvalaitenumero']
        if p['valaistu'] != 'K' or n not in lights:
            continue
        L = lights[n]
        seq = parse_seq(L.get('tarkkavalotunnus'))
        if not seq:
            continue
        out_lights.append({
            'no': n, 'name': p['nimifi'].strip(), 'type': p['turvalaitetyyppifi'], 'nav': p['navigointilajikoodi'],
            'ch': L.get('viralvalotunnuse'), 'h': L.get('korkeusvedesta') or 4.2,
            'p': P(*f['geometry']['coordinates'][0]), 'seq': seq,
            'sec': sorted(sectors.get(n, []), key=lambda s: s[0]),
        })
    out_lights.sort(key=lambda l: l['no'] != LIGHT_NO)

    lines = []
    for f in nl:
        p = f['properties']
        if not (set(str(p['jnro']).split('\\n')) & FAIRWAYS):
            continue
        name = re.sub(r'\[\d+: ([^\]]+)\].*', r'\1', p['vaylan_nimi'].split('\\n')[0])
        lines.append({'j': str(p['jnro']).split('\\n')[0], 'name': name, 'c': [P(*c) for c in f['geometry']['coordinates']]})

    coast = fetch_coast()
    land, shore = [], []
    for w in coast:
        pts = simplify([P(g['lon'], g['lat']) for g in w['geometry']], 4)
        if len(pts) < 2:
            continue
        closed = w['geometry'][0] == w['geometry'][-1]
        (land if closed and len(pts) > 3 else shore).append(pts)

    data = {'src': 'Väylävirasto (CC BY 4.0), © OpenStreetMap-tekijät (ODbL)', 'origin': [lon0, lat0],
            'lights': out_lights, 'lines': lines, 'land': land, 'shore': shore}
    js = 'const KOIRA = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';'
    app = Path(__file__).resolve().parent.parent / 'src' / 'app.html'
    s = app.read_text()
    s = re.sub(r'/\* KOIRA-DATA \*/.*?/\* /KOIRA-DATA \*/', lambda m: '/* KOIRA-DATA */' + js + '/* /KOIRA-DATA */', s, flags=re.S)
    app.write_text(s)
    print(f'valoja {len(out_lights)}, väylälinjoja {len(lines)}, saaria {len(land)}, rantaviivoja {len(shore)}, {len(js)//1024} kt')


def fetch_coast():
    """Rantaviivat Overpassista; vaihtoehtoisesti aiemmin tallennettu tiedosto: --coast tiedosto.json"""
    if '--coast' in sys.argv:
        return json.load(open(sys.argv[sys.argv.index('--coast') + 1]))['elements']
    q = '[out:json][timeout:90];way["natural"="coastline"]({},{},{},{});out geom;'.format(*COAST_BBOX)
    for attempt in range(3):
        try:
            return get('https://overpass-api.de/api/interpreter', urllib.parse.urlencode({'data': q}).encode())['elements']
        except Exception as e:
            print('Overpass-virhe, yritetään uudelleen:', e)
            time.sleep(10)
    raise SystemExit('Rantaviivoja ei saatu. Kokeile myöhemmin tai käytä --coast tiedosto.json')


def simplify(pts, tol):
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1e-9
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        p = pts[i]
        d = abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / L if L > 1e-6 else math.hypot(p[0] - a[0], p[1] - a[1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > tol:
        return simplify(pts[:idx + 1], tol)[:-1] + simplify(pts[idx:], tol)
    return [a, b]


if __name__ == '__main__':
    main()
