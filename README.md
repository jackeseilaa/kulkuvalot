# Kulkuvalot

Selaimessa toimiva harjoitusohjelma, jolla opetellaan tunnistamaan alukset niiden kulkuvaloista pimeässä.

- **Harjoittelu**: sovelluksessa on 29 alustyyppiä. Alusta voi katsoa mistä kulmasta tahansa (kulmaa käännetään painikkeilla, liukusäätimellä tai vetämällä kuvaa). Toiminto "Näytä alus" paljastaa aluksen rungon ja valojen selitykset.
- **Tehtävät**: tehtävätyypit ovat "Mikä alus?" ja "Mistä suunnasta?". Mukaan saa halutessaan myös vinot kulmat. Pisteet tallentuvat selaimeen.
- Alukset piirretään koodilla 3D-mallina. Valojen näkyvyys lasketaan sääntöjen sektoreista: mastovalo 225°, sivuvalot 112,5° ja perä- ja hinausvalo 135°.

Ohjelma on yksi HTML-tiedosto (`index.html`). Siinä ei ole kirjastoja eikä kuvatiedostoja, eikä se tarvitse palvelinta. Tiedoston voi avata sellaisenaan selaimessa.

## Julkaisu GitHub Pagesissa

1. Luo GitHubiin uusi julkinen repositorio, esimerkiksi nimellä `kulkuvalot`.
2. Lataa `index.html` repositorioon: **Add file → Upload files**.
3. Valitse **Settings → Pages → Source: Deploy from a branch**. Valitse haaraksi `main` ja kansioksi `/ (root)`, ja tallenna.
4. Minuutin kuluttua sivu toimii osoitteessa `https://<käyttäjätunnus>.github.io/kulkuvalot/`.

Osioon voi linkittää suoraan: `…/kulkuvalot/#tehtavat` tai `…/#ohje`.

## Muokkaaminen

Lähdekoodi on tiedostossa `src/app.html`. Muokkauksen jälkeen aja:

```sh
./build.sh
```

Skripti kokoaa tiedoston `index.html`.

Alustyypit ovat taulukossa `V`. Jokaisella tyypillä on nimi, valojen kuvaus, vinkki ja `build()`-funktio, joka palauttaa rungon osat (`parts`) ja valot (`lights`). Koordinaatit ovat aluksen omat: x osoittaa keulaan, y oikealle kyljelle ja z ylös. Valon tyyppi (`s`) on jokin seuraavista: `mast`, `stb`, `port`, `stern`, `all` tai `tri`.

## Lähde ja vastuu

Sisältö perustuu Pekka Jylhän (merenkulun asiantuntija) ja Tapio Säypön (toteutus) Kulkuvalot-harjoitussivustoon (2001–2004). Kansalliset erityisvalot (jäänmurtaja, viranomaisalus ja lossi) noudattavat alkuperäistä aineistoa. Tarkista ajantasaiset määräykset (COLREG ja Traficom). Ohjelma on harjoitteluväline, eikä sitä ole tarkoitettu navigointiin.
