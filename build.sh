#!/bin/sh
# Kokoaa src/app.html -> index.html (täysi HTML-dokumentti GitHub Pagesia varten)
cd "$(dirname "$0")"
{
  printf '<!doctype html>\n<html lang="fi">\n<head>\n<meta charset="utf-8">\n'
  printf '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
  printf '<meta name="description" content="Kulkuvalojen harjoitusohjelma: tunnista alus sen valoista pimeässä.">\n'
  printf '<meta name="theme-color" content="#060a11">\n'
  sed -n '1,/<\/style>/p' src/app.html
  printf '</head>\n<body>\n'
  sed -n '/<\/style>/,$p' src/app.html | tail -n +2
  printf '</body>\n</html>\n'
} > index.html
# julkaisuaika versiotietoon
BUILD=$(date '+%-d.%-m.%Y %H:%M')
sed -i '' "s/__BUILD__/$BUILD/" index.html
echo "index.html päivitetty ($BUILD)"
