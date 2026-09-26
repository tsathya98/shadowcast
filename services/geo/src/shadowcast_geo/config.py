"""Scenarios, regions, datasets and runtime settings for the ShadowCast geo service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

USER_AGENT = "shadowcast-geo/0.1 (+https://github.com/tsathya98/shadowcast)"

IBTRACS_NI_CSV = (
    "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs"
    "/v04r01/access/csv/ibtracs.NI.list.v04r01.csv"
)
OVERPASS_URLS = ("https://overpass.kumi.systems/api/interpreter", "https://overpass-api.de/api/interpreter")
OSDMA_SHELTERS_URL = "https://www.osdma.org/preparedness/multi-purpose-cyclone-flood-shelters/"
# ECMWF open data mirrored on Google Cloud Storage; keeps full history from 2024 onwards.
ECMWF_OPEN_DATA = "https://storage.googleapis.com/ecmwf-open-data"
ECMWF_TRACK_STEPS = (360, 240)  # tropical-cyclone track files are named -360h- since 2026 and -240h- before

# Earth Engine datasets.
NIGHT_LIGHTS = "NASA/VIIRS/002/VNP46A2"
NIGHT_LIGHTS_BAND = "DNB_BRDF_Corrected_NTL"  # raw radiance; the gap-filled band hides post-storm blackouts
NIGHT_LIGHTS_QUALITY_BAND = "Mandatory_Quality_Flag"  # 0/1 = high-quality retrieval
POPULATION = "WorldPop/GP/100m/pop"
POPULATION_YEAR = 2020
ELEVATION = "COPERNICUS/DEM/GLO30_2024_1"

# Physical and modelling constants.
EARTH_RADIUS_KM = 6371.0
NM_TO_KM = 1.852
KT_PER_MS = 1.943844
HOLLAND_B = 1.5  # Holland (1980) profile shape parameter; 1.5 is the conventional mid-range value
DENSIFY_STEP_MINUTES = 15  # hazard time step; 3-hourly best tracks miss the eyewall at near-track assets
WIND_BANDS_KT = (34, 50, 64)
GALE_KT = 34.0
ENSEMBLE_MATCH_KM = 150.0  # a member "hits" the target when its track passes within this distance
POPULATION_RADIUS_M = 2000
NIGHT_LIGHTS_RADIUS_M = 1500
LIT_RADIANCE = 1.0  # nW/cm2/sr; below this, percentage loss is dominated by noise
OUTAGE_LOSS_PCT = 50.0  # an asset "lost power" when its night-light radiance fell by at least this much
HOLDOUT_FOLDS = 5  # spatial cross-validation blocks along the reference coast
LOW_LYING_M = 5.0
LOSS_BANDS_KT = (0, 60, 80, 100, 130)

# Relative consequence of losing an asset (1-5), used to turn outage probability into a priority score.
CRITICALITY: dict[str, int] = {
    "hospital": 5,
    "cyclone_shelter": 5,
    "health_centre": 4,
    "substation": 4,
    "power_plant": 4,
    "clinic": 3,
    "water_works": 3,
    "fire_station": 3,
    "police": 2,
    "school": 2,
}

# OSM (key, value) -> asset kind.
OSM_KINDS: dict[tuple[str, str], str] = {
    ("power", "substation"): "substation",
    ("power", "plant"): "power_plant",
    ("amenity", "hospital"): "hospital",
    ("amenity", "clinic"): "clinic",
    ("healthcare", "centre"): "health_centre",
    ("amenity", "school"): "school",
    ("amenity", "fire_station"): "fire_station",
    ("amenity", "police"): "police",
    ("man_made", "water_works"): "water_works",
    ("man_made", "water_tower"): "water_works",
}


@dataclass(frozen=True)
class Region:
    """A study area.

    Attributes:
        id: Stable identifier.
        name: Human-readable name.
        bbox: ``(south, west, north, east)`` in degrees.
        osdma_districts: OSDMA districts whose cyclone shelters fall inside the region (empty outside Odisha).
    """

    id: str
    name: str
    bbox: tuple[float, float, float, float]
    osdma_districts: tuple[str, ...] = ()


@dataclass(frozen=True)
class Scenario:
    """A historical cyclone replayed over a region.

    Attributes:
        id: Stable identifier used in URLs and artifact paths.
        storm: IBTrACS storm name.
        season: IBTrACS season (year).
        region: Study area.
        landfall: Official landfall time (UTC), used for lead-time reporting.
        truth_pre: Inclusive start / exclusive end dates of the pre-storm night-light window.
        truth_post: Inclusive start / exclusive end dates of the post-landfall night-light window.
        reference: Whether the outage model is fitted on this scenario (exactly one scenario should be).
        forecasts: ECMWF ensemble issue times (UTC) to replay as-issued; ECMWF open data exists from 2024 onwards.
    """

    id: str
    storm: str
    season: int
    region: Region
    landfall: datetime
    truth_pre: tuple[date, date]
    truth_post: tuple[date, date]
    reference: bool = False
    forecasts: tuple[datetime, ...] = ()


ODISHA_COAST = Region(
    id="odisha-coast",
    name="Odisha coast (Ganjam to Balasore)",
    bbox=(19.0, 84.4, 21.7, 87.6),
    osdma_districts=(
        "BALASORE",
        "BHADRAK",
        "CUTTACK",
        "GANJAM",
        "JAGATSINGHPUR",
        "JAJPUR",
        "KENDRAPARA",
        "KHURDA",
        "MAYURBHANJ",
        "NAYAGARH",
        "PURI",
    ),
)

WEST_BENGAL_COAST = Region(
    id="west-bengal-coast",
    name="West Bengal coast (Digha to Kolkata and the Sundarbans)",
    bbox=(21.5, 87.4, 23.0, 89.0),
)

# Night-light windows follow one rule for every storm: about two weeks ending just before the storm's approach, and
# the seven nights after landfall.
SCENARIOS: dict[str, Scenario] = {
    scenario.id: scenario
    for scenario in (
        Scenario(
            id="fani-2019",
            storm="FANI",
            season=2019,
            region=ODISHA_COAST,
            landfall=datetime(2019, 5, 3, 3, 30, tzinfo=UTC),  # IMD: crossed near Puri 08:00-10:00 IST
            truth_pre=(date(2019, 4, 20), date(2019, 5, 2)),
            truth_post=(date(2019, 5, 4), date(2019, 5, 11)),
            reference=True,
        ),
        Scenario(
            id="dana-2024",
            storm="DANA",
            season=2024,
            region=ODISHA_COAST,
            landfall=datetime(2024, 10, 24, 20, 0, tzinfo=UTC),  # IMD: crossed near Bhitarkanika-Dhamra overnight
            truth_pre=(date(2024, 10, 10), date(2024, 10, 22)),
            truth_post=(date(2024, 10, 25), date(2024, 11, 1)),
            forecasts=tuple(
                datetime(2024, 10, day, hour, tzinfo=UTC)
                for day, hour in ((22, 0), (22, 12), (23, 0), (23, 12), (24, 0))
            ),
        ),
        # Held-out strong storm in a different state and grid; it predates ECMWF open data, so there is no as-issued
        # forecast replay. Both night-light windows fall inside India's COVID-19 lockdown.
        Scenario(
            id="amphan-2020",
            storm="AMPHAN",
            season=2020,
            region=WEST_BENGAL_COAST,
            landfall=datetime(2020, 5, 20, 11, 0, tzinfo=UTC),  # IMD: crossed near the Sundarbans 15:30-17:30 IST
            truth_pre=(date(2020, 5, 5), date(2020, 5, 19)),
            truth_post=(date(2020, 5, 21), date(2020, 5, 28)),
        ),
    )
}


@dataclass(frozen=True)
class Settings:
    """Geo service settings resolved from the environment.

    Attributes:
        bucket: GCS bucket holding built scenario artifacts; when unset, ``artifact_dir`` is used.
        artifact_dir: Local artifact root for development.
        cache_dir: Local cache for downloaded build inputs (IBTrACS, Overpass, OSDMA).
        ee_project: Google Cloud project used to initialise Earth Engine during builds.
        http_timeout_s: Per-request timeout for build-time downloads.
        max_attempts: Attempts per download before giving up.
        retry_backoff_s: Base delay for exponential backoff between attempts.
        allowed_origins: CORS origins allowed to call the API.
    """

    bucket: str | None = None
    artifact_dir: Path = Path("artifacts")
    cache_dir: Path = Path(".cache")
    ee_project: str = "argmax-cyclone-2026"
    http_timeout_s: float = 300.0
    max_attempts: int = 3
    retry_backoff_s: float = 5.0
    allowed_origins: tuple[str, ...] = ("*",)

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from ``GEO_*`` environment variables, falling back to defaults.

        Returns:
            Settings: The resolved configuration.

        Raises:
            ValueError: If a numeric variable cannot be parsed.
        """
        env = os.environ
        origins = env.get("GEO_ALLOWED_ORIGINS")
        return cls(
            bucket=env.get("GEO_BUCKET") or None,
            artifact_dir=Path(env.get("GEO_ARTIFACT_DIR", cls.artifact_dir)),
            cache_dir=Path(env.get("GEO_CACHE_DIR", cls.cache_dir)),
            ee_project=env.get("GEO_EE_PROJECT", cls.ee_project),
            http_timeout_s=float(env.get("GEO_HTTP_TIMEOUT_S", cls.http_timeout_s)),
            max_attempts=int(env.get("GEO_MAX_ATTEMPTS", cls.max_attempts)),
            retry_backoff_s=float(env.get("GEO_RETRY_BACKOFF_S", cls.retry_backoff_s)),
            allowed_origins=tuple(o.strip() for o in origins.split(",")) if origins else cls.allowed_origins,
        )
