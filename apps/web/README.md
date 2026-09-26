# ShadowCast console

The operations console for district and state disaster teams. Pick a storm, then scrub from days before landfall to the week after:

- **Map (Google Maps with a deck.gl overlay):** every shelter, hospital, substation and school in the region, coloured and sized by grid-outage risk, by the chance of gales across ECMWF ensemble members, or by the modelled wind at the scrubber time. The storm track, or the 52 as-issued ensemble member tracks, sits on top, along with the storm's eye and radius of maximum wind.
- **Prioritise:** the ranked asset list with kind filters. Each asset opens to its outage probability, gale arrival, population served, elevation, its wind timeline and the plain-language reasons for its rank.
- **Replay modes:** the best track (hindsight, used for backtesting) or each ECMWF ensemble forecast _as issued_, 68 to 20 hours before landfall.
- **Prove:** backtest skill (ROC AUC, Brier score, Spearman), median night-light loss by modelled wind band, and predicted vs observed loss for every substation.

## Architecture

Next.js 16 (App Router) with React 19 and Tailwind 4. The page server-renders the scenario list. Everything else is fetched client-side with SWR through the same-origin `/api/geo/*` rewrite to the [geo API](../../services/geo), so the API location is server configuration only. The map is loaded client-side only.

## Develop

```bash
cp .env.example .env.local          # set NEXT_PUBLIC_GOOGLE_MAPS_API_KEY; GEO_API_URL defaults to the Cloud Run API
pnpm install
pnpm dev                            # http://localhost:3000
pnpm format:check && pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

To use a local geo API instead, run `uv run uvicorn shadowcast_geo.api:create_app --factory --port 8000` in `services/geo` and set `GEO_API_URL=http://localhost:8000`.

The Maps key must be a browser key restricted to the Maps JavaScript API and to your origins (`localhost:3000`, `*.vercel.app`).
