# ShadowCast geo service

It turns a cyclone track into a **ranked, explained list of the assets that are about to lose power**, and it proves the model against satellite ground truth.

- **Offline build** (`python -m shadowcast_geo.build`): track → hazard per asset → Earth Engine enrichment → night-light truth → calibrated outage model → ranking → JSON artifacts in Cloud Storage.
- **API** (FastAPI on Cloud Run): serves the built scenarios and computes hazard on demand, e.g. wind at every asset at any moment, for the console's timeline scrubber.

## Method

| Step | How |
|---|---|
| Track | IBTrACS best track: JTWC intensity, radius of maximum wind and quadrant wind radii. As-issued ECMWF ensemble tracks come next |
| Hazard | Holland (1980) parametric wind profile per asset. The track is densified to 15-minute steps, because 3-hourly fixes let the eyewall pass *between* fixes at near-track assets |
| Exposure | 3,325 assets on the Odisha coast: 765 official OSDMA cyclone shelters plus 2,560 from OSM (264 substations, 38 power plants, 671 hospitals, 796 health centres, 358 clinics, 247 schools, 105 water works, 65 police and 16 fire stations). Each has WorldPop population within 2 km and Copernicus DEM elevation |
| Truth | VIIRS VNP46A2 raw radiance, masked to high-quality retrievals, before vs after landfall within 1.5 km of each substation. The gap-filled band is avoided because it carries pre-storm values into cloudy post-storm nights |
| Model | `P(outage) = logistic(a + b · peak wind)`, fitted on Fani. An asset "lost power" when its light fell by at least 50 % |
| Priority | `score = P(outage) × criticality / 5`, where criticality is hospitals and shelters 5, substations 4, …, schools 2. Every rank carries plain-language reasons |

## Results

**Cyclone Fani (2019), in-sample:**
- 200 lit substations, ROC AUC **0.97**, Brier **0.049**, Spearman(peak wind, light loss) **0.65**.
- The model crosses 50 % outage probability at **~107 kt**.
- Assets modelled above 100 kt lost a median **77 %** of their lights; at or below 80 kt, about **0 %**.

**Cyclone Dana (2024), held out:**
- The strongest modelled wind at any substation was 61 kt, and the model raised **no high-probability outage flags** (mean P 0.2 %).
- 2 % of substations crossed the 50 % loss threshold, which is consistent with night-to-night noise (this storm's low-wind band shows a median 21 % light variation).
- Dana tests false-alarm behaviour, not detection. **A strong held-out storm, Amphan (2020), is the next validation.**

## Assumptions and limitations

- Holland B = 1.5 and no over-land decay or asymmetry from forward motion. Peak winds over land are therefore upper bounds.
- The outage model has one feature (wind). Grid topology, pole age and pre-emptive shutdowns are not modelled. It was calibrated on one storm and one state.
- Night-light loss is a proxy for grid outage. Clouds, the moon and festivals add noise, which is handled by medians, the quality mask and the 50 % threshold.
- Best-track replays are hindsight, so lead times are short. As-issued ensemble replays (ECMWF open data on Google Cloud) remove this.
- Storm surge is not yet in the score. Elevation is reported per asset as evidence.

## API

| Endpoint | Returns |
|---|---|
| `GET /health` | Liveness and loaded scenarios |
| `GET /scenarios` | Built scenarios |
| `GET /scenarios/{id}` | Metadata, outage model, backtest skill, loss by wind band |
| `GET /scenarios/{id}/track` | GeoJSON track (path and fixes) |
| `GET /scenarios/{id}/assets?kind=&min_score=&limit=&offset=` | Ranked assets with hazard, probability and reasons |
| `GET /scenarios/{id}/assets/{asset_id}` | One asset with its 15-minute wind timeline |
| `GET /scenarios/{id}/hazard?at=` | Wind at every asset, plus the storm position, at one moment |
| `GET /scenarios/{id}/backtest` | Predicted vs observed per substation, with skill |

Interactive docs are at `/docs`.

## Develop

```bash
uv sync --all-extras
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
uv run python -m shadowcast_geo.build                  # writes ./artifacts (needs gcloud ADC with Earth Engine)
GEO_ARTIFACT_DIR=artifacts uv run uvicorn shadowcast_geo.api:create_app --factory --reload
```

Deploy with [`infra/geo.sh --publish`](../../infra/geo.sh).
