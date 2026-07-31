---
title: CityChange — City Time Machine
emoji: 🏙️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
license: mit
---

# CityChange — City Time Machine

**Urban evolution intelligence from open Earth-observation data.**
Pick a place; CityChange reconstructs how it changed year by year
(2017–2023) from open satellite-derived land-cover observations: what
changed, when, along which trajectory, how unusual, and how strong the
evidence is — with Sentinel-2 before/after imagery.

Six pre-analysed demo regions (India, USA ×2, Brazil, France, Germany) are
built in. You can also pan anywhere in the world and press **Analyze this
view** (~30–90 s; the analysis streams a few MB of public satellite data).

Notes for this hosted demo:

- Analyses you run yourself live until the Space restarts (ephemeral
  storage); the six demo regions are baked in and always available.
- All statements are observations from automated land-cover products with
  explicit caveats — CityChange reports *what* changed, never *why*.

Source, docs, evaluation & academic material: see the project repository.
Data: Impact Observatory / Microsoft / Esri 10 m Annual LULC (CC BY 4.0,
from ESA Sentinel-2); ESA WorldCover (CC BY 4.0); Copernicus Sentinel-2
imagery (ESA); search & basemap © OpenStreetMap contributors.
