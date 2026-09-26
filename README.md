# ShadowCast

**See the storm's shadow before it falls.**

ShadowCast does impact-based cyclone forecasting for India's coastal districts. It turns an official forecast into a ranked, explained list of the substations, hospitals, shelters and roads that are about to be hit. It drafts advisories in NDMA's CAP 1.2 format, in the local language, for an officer to approve. After landfall it **proves itself** against satellite ground truth.

> Forecasts tell you what the weather will **be**. ShadowCast tells you what it will **do**, then shows you it was right.

**Live:** [shadowcast-two.vercel.app](https://shadowcast-two.vercel.app) · geo API [docs](https://shadowcast-geo-489356738785.asia-south1.run.app/docs)

Built for **Build with AI: Code for Communities, Second Edition**, Track 5 *(Track-Based Cyclone Impact & Infrastructure Vulnerability Forecaster)*.

## The loop: Predict → Prioritise → Prepare → Prove

| Step | What happens |
|---|---|
| **Predict** | The as-issued forecast track becomes a wind/rain/surge hazard at every asset (parametric wind field, WeatherNext 2 ensemble, GPM rainfall, coastal elevation) |
| **Prioritise** | Assets are ranked by calibrated outage probability × criticality (population served breaks ties), and every rank comes with its reasons |
| **Prepare** | Gemini drafts actions and a multilingual CAP 1.2 advisory with audio. **Nothing is dispatched without an officer's approval**, and every decision is audited |
| **Prove** | Night-light (VIIRS) blackouts and Sentinel-1 flooding are measured per asset after landfall; historical backtests are published with their skill metrics |

**Evidence.** The outage model is fitted once, on Cyclone Fani (2019), and then scored without refitting. Truth is NASA VIIRS night-light loss around each lit substation.

| Storm | Test | ROC AUC | Brier | What it shows |
|---|---|---|---|---|
| Fani 2019, Odisha | In sample | 0.97 | 0.049 | Above 100 kt, substations lost a median 77 % of their lights; at or below 80 kt, about 0 % |
| Fani 2019 | Spatial holdout (each fifth of the coast hidden in turn) | 0.97 | 0.050 | Within held-out stretches: 0.85–0.94. The model does not overfit the coast |
| Hudhud 2014, Andhra Pradesh | Untouched test storm, another state and grid | **0.79** | 0.19 | Transfers to a direct strong hit on Visakhapatnam (Spearman 0.56) |
| Amphan 2020, West Bengal | Held out | 0.44 | 0.28 | **Fails.** The wind model saturates over land and rural West Bengal lost power regardless of local wind |
| Dana 2024, Odisha | Held out, weak storm | 0.32 | 0.02 | No false alarms. Only 5 of 252 substations went dark, too few for the AUC to mean anything |

We tried adding inland decay (Kaplan & DeMaria 1995) and terrain roughness (ESA WorldCover). It made the Fani spatial holdout worse (0.87), so it was reverted; see the commit history. Amphan is published as it is: the Prove step exists to catch exactly this kind of miss before anyone relies on the model in a new grid.

## Repository

| Path | What |
|---|---|
| [`apps/web`](apps/web) | Operations console: Google Maps + deck.gl, timeline replay, ensemble spaghetti, ranked assets with reasons, the Gemini duty analyst, backtest; Next.js 16 on Vercel |
| [`services/geo`](services/geo) | Hazard per asset, calibrated outage probability, ranking with reasons, satellite backtests; FastAPI on Cloud Run |
| [`services/archiver`](services/archiver) | Cloud Run Job that snapshots GDACS, NDMA SACHET, IBTrACS and WeatherNext 2 every 6 h for as-issued replays |
| [`infra`](infra) | Idempotent `gcloud` deployment scripts (geo API, archiver, agent resources, Vercel federation) |

**As-issued forecast replay:** ShadowCast replays ECMWF's 52-member ensemble as it was issued, 68 to 20 hours before landfall. Every member drives the same wind model, so each asset gets the probability of gales and hurricane-force wind, and when gales arrive. For Cyclone Dana (2024) at 44 h lead, 94-96 % of members put gales on Paradip's hospitals and Mahakalapada's shelters about 15 h before landfall.

**The Gemini duty analyst:** an agent on Gemini 3.8 Flash (Vertex AI) answers questions such as *"why is this hospital ranked #3?"* by calling the geo API, so every number it quotes comes from ShadowCast's deterministic model, never from Gemini itself. It drafts advisories: officer actions per asset plus a public CAP 1.2 message in English, Hindi and Odia, validated against a schema. The officer approves or rejects each draft (approvals are HMAC-signed so they cannot be forged), and every decision is written once to an append-only Firestore audit log. Approved advisories can be downloaded as CAP XML and heard in each language through Gemini-TTS; classic Cloud Text-to-Speech has no Odia voice.

**Deployment:** the console runs on Vercel and reaches Vertex AI and Firestore through Workload Identity Federation: Vercel's OIDC token is exchanged for short-lived credentials of a service account that may only call Gemini and use Firestore. There is no service-account key anywhere. The Python services run on Cloud Run.

Coming next: the Amphan (2020) out-of-sample backtest.

## Stack

Google Earth Engine · Gemini on Vertex AI · Gemini-TTS · WeatherNext 2 · Cloud Run · Cloud Storage · Firestore · Google Maps Platform · Next.js on Vercel.

## Data sources

IBTrACS (NOAA NCEI) · GDACS (EC JRC / UN OCHA) · NDMA SACHET CAP feeds · ECMWF open data (CC BY 4.0) · WeatherNext 2 via Open-Meteo · NASA VIIRS VNP46A2 · Copernicus Sentinel-1/2 · NASA GPM IMERG · OpenStreetMap contributors (ODbL) · OSDMA cyclone shelter registry · WorldPop.

ShadowCast produces **draft** advisories for authorised officials. IMD and NDMA remain the authoritative sources for warnings.

## License

[Apache-2.0](LICENSE)
