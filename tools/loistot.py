#!/usr/bin/env python3
"""Päivittää Sektoriloisto-osion loistohakemiston (kaikki Suomen monivärisektoriset loistot) src/app.html-tiedostoon.

Lähde: Väylävirasto, avoin rajapinta (CC BY 4.0). Aja: python3 tools/loistot.py && ./build.sh
"""
import json, re, urllib.request
from pathlib import Path

API = 'https://avoinapi.vaylapilvi.fi/vaylatiedot/ogc/features/v1/collections/vesivaylatiedot:{}/items?f=json&limit=10000{}'


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'kulkuvalot-harjoitus/1.0'})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)['features']


def main():
    cols = {}
    for f in get(API.format('valosektorit_uusi', '')):
        p = f['properties']
        cols.setdefault(str(p['tlnumero']), set()).add(p['vari'])
    multi = {k for k, v in cols.items() if len(v) > 1}
    rows = []
    for f in get(API.format('turvalaitteet_uusi', '&filter=valaistu%3D%27K%27')):
        p = f['properties']
        n = str(p['turvalaitenumero'])
        if n in multi and p.get('nimifi'):
            lon, lat = f['geometry']['coordinates'][0][:2]
            rows.append([n, p['nimifi'].strip(), p['turvalaitetyyppifi'], round(lat, 5), round(lon, 5)])
    rows.sort(key=lambda r: r[1].lower())
    js = 'const LIDX = ' + json.dumps(rows, ensure_ascii=False, separators=(',', ':')) + ';'
    app = Path(__file__).resolve().parent.parent / 'src' / 'app.html'
    s = app.read_text()
    s = re.sub(r'/\* LOISTO-INDEX \*/.*?/\* /LOISTO-INDEX \*/', lambda m: '/* LOISTO-INDEX */' + js + '/* /LOISTO-INDEX */', s, flags=re.S)
    app.write_text(s)
    print(f'loistoja {len(rows)}')


if __name__ == '__main__':
    main()
