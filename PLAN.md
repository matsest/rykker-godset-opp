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
scripts/fetch_data.py      →  data/raw/*.json
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
| **GitHub Pages / Cloudflare Pages** | Hosting |

---

## Datakilde

**NIFS API** (`https://api.nifs.no/`) – gratis, åpent, JSON.

| Endepunkt | Data |
|-----------|------|
| `stages/700912/table/` | Komplett tabell |
| `stages/700912/matches/` | Alle kamper (resultater + kommende) |
| `stages/700912/teams/` | Lagliste |

---

## Nøkkeltall (MVP)

- [x] Plassering i tabellen
- [x] Poeng, mål scoret/mottatt, målforskjell
- [x] Kamper spilt, seire / uavgjort / tap
- [x] Form siste 5 kamper
- [x] Poengsnitt siste 5 kamper
- [x] Poengsnitt hjemme / borte siste 5 kamper
- [x] Avstand til 1. plass (direkte opprykk)
- [x] Avstand til 3. plass (kvalifiseringsgrense)
- [x] Avstand til 15. plass (nedrykk)
- [x] Status: **JA** / **KVALIFISERING** / **NEI**
- [x] Siste 5 resultater
- [x] Neste 3 kamper

## Nøkkeltall (fremtidig)

- [ ] Mål vs skudd på mål (konverteringsrate)
- [ ] xG og xGA
- [ ] Sammenligning med lag på 1. og 2. plass
- [ ] Sammenligning med fjorårets topp 2
- [ ] Toppscorer

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
├── .mise.toml
├── PLAN.md
├── README.md
├── pyproject.toml
├── scripts/
│   ├── fetch_data.py
│   ├── generate_stats.py
│   └── build_site.py
├── data/
│   ├── raw/
│   │   ├── table.json
│   │   ├── matches.json
│   │   └── teams.json
│   └── stats.json
├── templates/
│   └── index.html.j2
└── site/
    ├── index.html
    └── style.css
```

---

## CI/CD (GitHub Actions)

Trigger: `workflow_dispatch` (manuell) + `schedule` (timevis).

Steg:
1. Checkout repo
2. Setup Python + uv
3. `uv sync`
4. `python scripts/fetch_data.py`
5. `python scripts/generate_stats.py`
6. `python scripts/build_site.py`
7. Deploy `site/` til GitHub Pages

---

## Status

| Fase | Status |
|------|--------|
| MVP – backend scripts | 🚧 Under arbeid |
| MVP – frontend/design | 🚧 Under arbeid |
| CI/CD – GitHub Actions | ⏳ Planlagt |
| Utvidet data (xG, sammenligning) | ⏳ Fremtidig |

---

## Opprykksregler OBOS-ligaen 2026

- **Direkte opprykk:** 1.–2. plass
- **Opprykkskvalifisering:** 3.–6. plass
- **Nedrykkskvalifisering:** 14. plass
- **Direkte nedrykk:** 15.–16. plass

---

## Oppdateringer

- **2026-05-05:** Prosjekt opprettet. NIFS API identifisert som datakilde.
  Stage ID 700912 = OBOS-ligaen 2026.
