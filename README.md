# ShadowCast

**See the storm's shadow before it falls.**

ShadowCast does impact-based cyclone forecasting for India's coastal districts. It turns an official forecast into a ranked, explained list of the substations, hospitals, shelters and roads that are about to be hit. It drafts advisories in NDMA's CAP 1.2 format, in the local language, for an officer to approve. After landfall it **proves itself** against satellite ground truth.

> Forecasts tell you what the weather will **be**. ShadowCast tells you what it will **do**, then shows you it was right.

Built for **Build with AI: Code for Communities, Second Edition**, Track 5 *(Track-Based Cyclone Impact & Infrastructure Vulnerability Forecaster)*.

## The loop: Predict → Prioritise → Prepare → Prove

| Step | What happens |
|---|---|
| **Predict** | The as-issued forecast track becomes a wind/rain/surge hazard at every asset (parametric wind field, WeatherNext 2 ensemble, GPM rainfall, coastal elevation) |
| **Prioritise** | Assets are ranked by calibrated outage probability × criticality × population served, and every rank comes with its reasons |
| **Prepare** | Gemini drafts actions and a multilingual CAP 1.2 advisory with audio. **Nothing is dispatched without an officer's approval**, and every decision is audited |
| **Prove** | Night-light (VIIRS) blackouts and Sentinel-1 flooding are measured per asset after landfall; historical backtests are published with error bars |

**Evidence so far (Cyclone Fani, 2019):** across 263 substations from Ganjam to Balasore, modelled peak wind predicts observed night-light loss (Spearman 0.61). Substations above 100 kt lost a median **82 %** of their lights; those at or below 80 kt lost about **0 %**.

## Repository

| Path | What |
|---|---|
| [`services/archiver`](services/archiver) | Cloud Run Job that snapshots GDACS, NDMA SACHET, IBTrACS and WeatherNext 2 every 6 h for as-issued replays |
| [`infra`](infra) | Idempotent `gcloud` deployment scripts |

Coming next: `services/geo` (hazard, ranking, backtest and verification API on Cloud Run) and `apps/web` (Next.js operations console with the Gemini agent, on Vercel).

## Stack

Google Earth Engine · Gemini on Vertex AI · Gemini-TTS · WeatherNext 2 · Cloud Run · Cloud Storage · Firestore · Google Maps Platform · Next.js on Vercel.

## Data sources

IBTrACS (NOAA NCEI) · GDACS (EC JRC / UN OCHA) · NDMA SACHET CAP feeds · ECMWF open data (CC BY 4.0) · WeatherNext 2 via Open-Meteo · NASA VIIRS VNP46A2 · Copernicus Sentinel-1/2 · NASA GPM IMERG · OpenStreetMap contributors (ODbL) · OSDMA cyclone shelter registry · WorldPop.

ShadowCast produces **draft** advisories for authorised officials. IMD and NDMA remain the authoritative sources for warnings.

## License

[Apache-2.0](LICENSE)
