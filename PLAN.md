# Rykker Godset Opp? – Plan

> Live-oppdatering av Strømsgodsets vei tilbake til Eliteserien.

---

## Visjon

En enkel, statisk nettside som besvarer spørsmålet alle Godset-supportere lurer på:
**«Rykker Godset Opp?»**

Nettsiden viser nøkkeltall, tabellplassering og analyserer om laget er på rett vei
mot opprykk fra OBOS-ligaen 2026.

---

## Arkitektur

```
scripts/fetch_data.py      →  data/raw/*.json  (inkl. match_stats.json)
scripts/generate_stats.py  →  data/stats.json
scripts/build_site.py      →  site/index.html + site/style.css
```

Alt er statisk. Ingen server, ingen database. Kun filer.

---

## Verktøy

| Verktøy | Bruk |
|---------|------|
| **uv** | Python-pakkehåndtering og virtual env |
| **mise** | Versjonshåndtering for Python, uv, osv. |
| **Python 3.12+** | Scriptspråk |
| **Jinja2** | HTML-template engine |
| **GitHub Actions** | CI/CD: fetch → stats → build → deploy |
| **GitHub Pages** | Hosting |

---

## Datakilde

**NIFS API** (`https://api.nifs.no/`) – gratis, åpent, JSON.

| Endepunkt | Data |
|-----------|------|
| `stages/700912/table/` | Komplett tabell |
| `stages/700912/matches/` | Alle kamper (resultater + kommende) |
| `stages/700912/teams/` | Lagliste |
| `matches/{id}/` | Kampstatistikk (skudd, sjanser, ballbesittelse) |

---

## Nøkkeltall (MVP)

- [x] Plassering i tabellen
- [x] Poeng, mål scoret/mottatt, målforskjell
- [x] Kamper spilt, seire / uavgjort / tap
- [x] Gauge: Nei / Tja / Ja!
- [x] Form siste 5 kamper
- [x] Poengsnitt (siste 5)
- [x] Seiersprosent
- [x] Avstand til 1. plass (direkte opprykk)
- [x] Avstand til 2. plass (direkte opprykk)
- [x] Avstand til 6. plass (kvalifiseringsgrense)
- [x] Siste 5 resultater (med hjemme–borte-format)
- [x] Neste 5 kamper (med hjemme–borte-format)
- [x] Mål vs skudd på mål (konverteringsrate)
- [x] Ligastatistikk – sammenligning med resten av ligaen (skudd, sjanser, ballbesittelse, målprosent, form)
- [x] Ligaranking per statistikk med indikator for over-/underprestasjon vs tabellplassering

## Nøkkeltall (fremtidig)

- [ ] Sammenligning med topp 2 siste 5 år
- [ ] Toppscorer / målscorere

---

## Design

- **Primærfarge:** `#002145` (Godset-blå)
- **Sekundærfarge:** `#FFFFFF` (hvit)
- **Accent:** `#D42027` (rød for varsler)
- **Font:** System-fonts
- **Mobilvennlig:** CSS Grid + Flexbox
- **Språk:** Norsk (bokmål)

---

## Mappestruktur

```
rykkergodsetopp/
├── .github/workflows/update-site.yml
├── .gitignore
├── .mise.toml
├── LICENSE
├── Makefile
├── PLAN.md
├── README.md
├── pyproject.toml
├── assets/
│   └── og-image.svg
├── scripts/
│   ├── fetch_data.py
│   ├── generate_stats.py
│   └── build_site.py
├── data/
│   ├── raw/
│   │   ├── table.json
│   │   ├── matches.json
│   │   ├── teams.json
│   │   ├── match_stats.json
│   │   └── metadata.json
│   └── stats.json
├── templates/
│   └── index.html.j2
└── site/
    ├── index.html
    ├── style.css
    ├── og-image.png
    └── favicon.svg
```

---

## CI/CD (GitHub Actions)

Trigger: `workflow_dispatch` (manuell) + `schedule` (daglig kl. 06:00 UTC).

Steg:
1. Checkout repo
2. Setup Python + uv
3. `uv sync`
4. Cache `data/raw/` fra forrige kjøring (gjenbruker match_stats)
5. `make ci`
6. Deploy `site/` til GitHub Pages

---

## Status

| Fase | Status |
|------|--------|
| MVP – backend scripts | ✅ Ferdig |
| MVP – frontend/design | ✅ Ferdig |
| SEO + metadata | ✅ Ferdig |
| CI/CD – GitHub Actions | ✅ Ferdig |
| Utvidet data (ligastatistikk, kampdata) | ✅ Ferdig |

---

## Opprykksregler OBOS-ligaen 2026

- **Direkte opprykk:** 1.–2. plass
- **Opprykkskvalifisering:** 3.–6. plass
- **Nedrykkskvalifisering:** 14. plass
- **Direkte nedrykk:** 15.–16. plass
