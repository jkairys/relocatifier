# relocatifier — frontend

Static MapLibre frontend for Discovery mode (ADR-0002): a full-screen choropleth
of Suburbs (ABS SAL), colourable by the seven v1 Metrics, with a click-anywhere
stat sheet. No backend — it consumes artifacts the ETL writes to `public/data/`:

- `suburbs.pmtiles` — vector tiles, layer `suburbs`, feature id promoted from
  `sal_code` (properties: `sal_code`, `name`, `state`)
- `metrics.json` — per-suburb metric values plus search-zone stats
  (see `docs/PRD.md` §Artifact contract)

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
  feature-state colouring, hover/click
- `src/color.ts` — stats (p10/median/p90) → green–yellow–red ramp
- `src/metrics.ts` — the canonical seven-metric registry + value formatting
- `src/layers.ts` — toggleable-layer registry (future layers slot in here)
- `src/useArtifacts.ts` — artifact loading/probing and the missing-data state
- `src/components/` — header, metric switcher, legend, layer toggle,
  stat sheet, empty state
