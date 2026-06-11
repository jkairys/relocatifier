# relocatifier — frontend

Static MapLibre frontend for Discovery mode (ADR-0002): a full-screen choropleth
of Suburbs (ABS SAL), colourable by the seven v1 Metrics, with a click-anywhere
stat sheet, suburb search, and a persisted shortlist. No backend — it consumes
artifacts the ETL writes to `public/data/`:

- `suburbs.pmtiles` — vector tiles, layer `suburbs`, feature id promoted from
  `sal_code` (properties: `sal_code`, `name`, `state`)
- `metrics.json` — per-suburb metric values (incl. a `centre` [lng, lat] per
  suburb) plus search-zone stats (see `docs/PRD.md` §Artifact contract)

Beyond the choropleth + stat sheet:

- **Search** (header): type-ahead over all suburb names, prefix matches first,
  arrows/enter/esc; results show the state (and SAL code when a name+state
  pair is ambiguous). Selecting flies to the suburb and opens its stat sheet.
- **Shortlist**: the star on a stat sheet pins a suburb (SAL codes persisted
  in localStorage). The Shortlist panel (left rail) lists pins, flies on
  click, and with ≥2 pins opens a compare table — suburbs as columns, the
  seven metrics as rows, cells tinted with the map's relative-to-stats ramp.
  Pinned suburbs keep a magenta outline on the map.
- **Default view**: first load fits the whole Search Zone (Cairns → Batemans
  Bay); the URL hash (`#zoom/lat/lng`, maintained by MapLibre) acts as a
  permalink and wins over the default when present.
- **Hover tooltip**: suburb name + active-metric value at the cursor,
  updated outside React via rAF-throttled mousemove.

If either artifact is missing the app shows an empty-state notice instead of
crashing — run `task etl:fetch` then `task etl:build` from the repo root.

## Develop

```sh
npm install
task dev      # or: npm run dev
task build    # or: npm run build  (tsc strict + vite build)
```

In dev only, if `suburbs.pmtiles` is absent the app will fall back to
`public/data/suburbs.mock.geojson` (same feature properties) so the UI can be
exercised without tippecanoe output. `public/data/` is gitignored.

## Structure

- `src/MapView.tsx` — map lifecycle, pmtiles protocol, suburb layers,
  feature-state colouring (hover/selected/pinned), cursor tooltip, flyTo API
- `src/color.ts` — stats (p10/median/p90) → green–yellow–red ramp
- `src/metrics.ts` — the canonical seven-metric registry + value formatting
- `src/layers.ts` — toggleable-layer registry (future layers slot in here)
- `src/search.ts` — suburb-name search index (prefix-first, SAL-code
  disambiguation for duplicate name+state pairs)
- `src/useArtifacts.ts` — artifact loading/probing and the missing-data state
- `src/useShortlist.ts` — pinned SAL codes, persisted to localStorage
- `src/components/` — header, search box, metric switcher, legend, layer
  toggle, shortlist panel, compare panel, stat sheet, empty state
