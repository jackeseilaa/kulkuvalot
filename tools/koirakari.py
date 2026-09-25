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
BBOX = (24.82, 60.085, 25.065, 60.195)  # lon0, lat0, lon1, lat1
COAST_BBOX = (60.07, 24.80, 60.20, 25.08)
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
    va = feats('vaylaalueet_uusi')

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
        fw = re.search(r'\[\d+: ([^\]]+)\]', p.get('vaylan_nimi') or '')   # linjamerkin väylä kartan nimeä varten
        if p['turvalaitetyyppifi'] == 'Linjamerkki' and fw:
            out_lights[-1]['fw'] = fw.group(1).strip()
    out_lights.sort(key=lambda l: l['no'] != LIGHT_NO)

    # valaisemattomat viitat ja poijut (näkyvät yöllä vain varjoina)
    marks = []
    for f in tl:
        p = f['properties']
        if p['valaistu'] == 'K' or p['turvalaitetyyppifi'] not in ('Viitta', 'Poiju'):
            continue
        marks.append({'no': p['turvalaitenumero'], 'name': (p['nimifi'] or '').strip(), 'type': p['turvalaitetyyppifi'],
                      'nav': p['navigointilajikoodi'], 'h': 2.5 if p['turvalaitetyyppifi'] == 'Viitta' else 2.0,
                      'p': P(*f['geometry']['coordinates'][0])})

    lines = []
    for f in nl:
        p = f['properties']
        name = re.sub(r'\[\d+: ([^\]]+)\].*', r'\1', p['vaylan_nimi'].split('\\n')[0])
        lines.append({'j': str(p['jnro']).split('\\n')[0], 'name': name, 'c': [P(*c) for c in f['geometry']['coordinates']]})

    areas = []
    for f in va:
        p = f['properties']; g = f['geometry']
        polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
        for poly in polys:
            areas.append({'j': str(p['jnro']).split('\\n')[0], 'd': p.get('mitoitussyvays'),
                          'r': [P(*c[:2]) for c in poly[0]]})

    coast = fetch_coast()
    rocks, reefs = fetch_rocks(P)
    land, shore = [], []
    for w in coast:
        pts = simplify([P(g["lon"], g["lat"]) for g in w["geometry"]], 5)
        if len(pts) < 2:
            continue
        closed = w['geometry'][0] == w['geometry'][-1]
        (land if closed and len(pts) > 3 else shore).append(pts)

    data = {'src': 'Väylävirasto (CC BY 4.0), © OpenStreetMap-tekijät (ODbL)', 'origin': [lon0, lat0],
            'lights': out_lights, 'marks': marks, 'lines': lines, 'areas': areas, 'rocks': rocks, 'reefs': reefs, 'land': land, 'shore': shore}
    js = 'const KOIRA = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';'
    app = Path(__file__).resolve().parent.parent / 'src' / 'app.html'
    s = app.read_text()
    s = re.sub(r'/\* KOIRA-DATA \*/.*?/\* /KOIRA-DATA \*/', lambda m: '/* KOIRA-DATA */' + js + '/* /KOIRA-DATA */', s, flags=re.S)
    app.write_text(s)
    print(f'valoja {len(out_lights)}, valaisemattomia merkkejä {len(marks)}, väylälinjoja {len(lines)}, väyläalueita {len(areas)}, saaria {len(land)}, rantaviivoja {len(shore)}, kiviä {len(rocks)}, karikoita {len(reefs)}, {len(js)//1024} kt')


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


def overpass(q, cache_flag):
    if cache_flag in sys.argv:
        return json.load(open(sys.argv[sys.argv.index(cache_flag) + 1]))['elements']
    for attempt in range(3):
        try:
            return get('https://overpass-api.de/api/interpreter', urllib.parse.urlencode({'data': q}).encode())['elements']
        except Exception as e:
            print('Overpass-virhe, yritetään uudelleen:', e)
            time.sleep(15)
    raise SystemExit('Overpass ei vastaa. Kokeile myöhemmin.')


def fetch_rocks(P):
    """Kivet, karikot ja matalikot OpenStreetMapista (merikarttamerkinnät seamark:*)"""
    b = '60.08,24.82,60.20,25.07'
    q = ('[out:json][timeout:150];(node["seamark:type"~"rock|obstruction|wreck"](%s);node["natural"~"rock|stone|reef|shoal"](%s);'
         'way["seamark:type"~"rock|obstruction"](%s);way["natural"~"reef|shoal"](%s););out geom;') % (b, b, b, b)
    rocks, reefs = [], []
    for e in overpass(q, '--rocks'):
        t = e.get('tags', {})
        kind = t.get('seamark:type') or t.get('natural')
        wl = t.get('seamark:rock:water_level') or t.get('seamark:obstruction:water_level') or ''
        k = 'dry' if wl in ('always_dry', 'dry') else 'awash' if wl in ('awash', 'covers', 'floating') else 'sub' if wl in ('submerged', 'below_mlw') else ('reef' if kind in ('reef', 'shoal') else 'rock')
        if e['type'] == 'node':
            rocks.append({'p': P(e['lon'], e['lat']), 'k': k})
        elif e.get('geometry'):
            pts = simplify([P(g['lon'], g['lat']) for g in e['geometry']], 3)
            if len(pts) >= 3:
                reefs.append({'r': pts, 'k': k})
    return rocks, reefs


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
