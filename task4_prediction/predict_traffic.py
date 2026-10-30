"""
Task 4 - Prediction / forecast script
=====================================

Pipeline (one run = one forecast):

    1. FETCH       recent hourly records from the REST API (Task 3)
    2. PREPROCESS  rebuild the Task 1 cleaning steps on those records
    3. LOAD        the trained Random Forest (Task 1, joblib file)
    4. PREDICT     traffic_volume for the next hour (or the next N hours)

Usage (run from the repository root, with the API running):

    python task4_prediction/predict_traffic.py
    python task4_prediction/predict_traffic.py --source mongodb --horizon 6
    python task4_prediction/predict_traffic.py --as-of 2018-09-20T08:00:00

The model was trained on 10 features (see FEATURE_NAMES). They all come from
the same preprocessing logic used in task1_eda_ml/task1_eda_and_lags.ipynb.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import httpx
import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = ROOT / "task1_eda_ml" / "traffic_forecasting_model.pkl"
DEFAULT_API_URL = "http://127.0.0.1:8000"

# Feature order used by the model in Task 1 (Experiment 2: tuned autoregressive).
FEATURE_NAMES = [
    "hour",
    "dayofweek",
    "is_weekend",
    "temp",
    "clouds_all",
    "rain_1h",
    "lag_1",
    "lag_24",
    "lag_168",
    "rolling_mean_24",
]

INTEGER_FEATURES = {"hour", "dayofweek", "is_weekend"}
WEATHER_COLUMNS = ["temp", "rain_1h", "snow_1h", "clouds_all"]

# Sensor-fault thresholds from Task 1 (Issue 4 - Sensor malfunctions).
MIN_VALID_TEMP_K = 100      # 0 K is physically impossible
MAX_VALID_RAIN_MM = 500     # 9,000+ mm/h spikes are sensor errors

MAX_LAG_HOURS = 168         # longest lag the model needs
ROLLING_WINDOW = 24
DEFAULT_HISTORY_HOURS = 192  # 168h of lag + a small safety margin for gaps
REQUEST_TIMEOUT_SECONDS = 30


class PredictionError(RuntimeError):
    """A problem the user can fix (API down, not enough history, ...)."""


# --------------------------------------------------------------------------- #
# Step 1 - Fetch from the API
# --------------------------------------------------------------------------- #
def _get_json(client: httpx.Client, path: str, params: dict | None = None):
    try:
        response = client.get(path, params=params)
    except httpx.ConnectError as error:
        raise PredictionError(
            f"Cannot reach the API at {client.base_url}. "
            "Start it first with: uvicorn api.main:app --reload"
        ) from error
    except httpx.TimeoutException as error:
        raise PredictionError(f"The API did not answer within {REQUEST_TIMEOUT_SECONDS}s.") from error

    if response.status_code == 404:
        raise PredictionError(f"The API returned 404 for {path}: {_detail(response)}")
    if response.status_code >= 400:
        raise PredictionError(
            f"The API returned {response.status_code} for {path}: {_detail(response)}"
        )
    return response.json()


def _detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text


def fetch_latest_record(client: httpx.Client, source: str) -> dict:
    """GET /api/<source>/records/latest"""
    return _get_json(client, f"/api/{source}/records/latest")


def fetch_records_between(
    client: httpx.Client, source: str, start: pd.Timestamp, end: pd.Timestamp
) -> list[dict]:
    """GET /api/<source>/records/range?start=...&end=..."""
    return _get_json(
        client,
        f"/api/{source}/records/range",
        params={"start": start.isoformat(), "end": end.isoformat()},
    )


def fetch_history(
    client: httpx.Client,
    source: str,
    history_hours: int,
    as_of: pd.Timestamp | None = None,
) -> tuple[list[dict], pd.Timestamp]:
    """Return (records, origin). `origin` is the last hour we know about."""
    if as_of is None:
        latest = fetch_latest_record(client, source)
        origin = to_naive_utc(latest["date_time"]).floor("h")
    else:
        origin = as_of.floor("h")

    start = origin - pd.Timedelta(hours=history_hours)
    records = fetch_records_between(client, source, start, origin)
    if not records:
        raise PredictionError(
            f"The API returned no records between {start} and {origin}. "
            "Check the --as-of value or that the databases are loaded."
        )
    return records, origin


def to_naive_utc(value) -> pd.Timestamp:
    """Parse an API timestamp into a timezone-naive UTC pandas Timestamp."""
    return pd.to_datetime(value, utc=True).tz_localize(None)


# --------------------------------------------------------------------------- #
# Step 2 - Preprocess (mirrors Task 1)
# --------------------------------------------------------------------------- #
def records_to_frame(records: list[dict]) -> pd.DataFrame:
    """Flatten API records (one row per hour, weather embedded as a list).

    Task 1 averaged the numeric columns when one hour had several weather
    readings, so we average the embedded readings the same way.
    """

    def mean_of(readings: list[dict], key: str) -> float:
        values = [r[key] for r in readings if r.get(key) is not None]
        return float(np.mean(values)) if values else np.nan

    rows = []
    for record in records:
        readings = record.get("weather") or []
        rows.append(
            {
                "date_time": to_naive_utc(record["date_time"]),
                "temp": mean_of(readings, "temp_k"),
                "rain_1h": mean_of(readings, "rain_1h"),
                "snow_1h": mean_of(readings, "snow_1h"),
                "clouds_all": mean_of(readings, "clouds_all"),
                "traffic_volume": float(record["traffic_volume"]),
            }
        )
    return pd.DataFrame(rows)


def preprocess_history(frame: pd.DataFrame, origin: pd.Timestamp) -> tuple[pd.DataFrame, int]:
    """Apply the Task 1 cleaning steps. Returns (clean hourly frame, #hours imputed)."""
    frame = frame.copy()

    # 1. Sensor faults -> missing (then handled by imputation below).
    frame.loc[frame["temp"] < MIN_VALID_TEMP_K, "temp"] = np.nan
    frame.loc[frame["rain_1h"] > MAX_VALID_RAIN_MM, "rain_1h"] = np.nan

    # 2. Duplicate timestamps -> mean per hour.
    hourly = frame.groupby("date_time").mean(numeric_only=True)

    # 3. Complete, uninterrupted hourly index ending at the forecast origin.
    full_index = pd.date_range(hourly.index.min(), origin, freq="h", name="date_time")
    clean = hourly.reindex(full_index)
    imputed_hours = int(clean["traffic_volume"].isna().sum())

    # 4. Imputation, same rules as Task 1.
    for column in ("temp", "clouds_all"):
        clean[column] = clean[column].interpolate(method="time", limit_direction="both")
    for column in ("rain_1h", "snow_1h"):
        clean[column] = clean[column].fillna(0.0)
    clean["traffic_volume"] = clean["traffic_volume"].ffill().bfill()

    return clean, imputed_hours


def build_feature_row(
    traffic: pd.Series, weather: dict[str, float], timestamp: pd.Timestamp
) -> dict[str, float]:
    """Compute the model inputs for ONE target hour from earlier hours only.

    Lags and the moving average only use hours strictly before `timestamp`,
    because the target hour's own traffic is unknown at forecast time.
    """
    needed_start = timestamp - pd.Timedelta(hours=MAX_LAG_HOURS)
    if needed_start < traffic.index.min():
        raise PredictionError(
            f"Not enough history: need data back to {needed_start}, "
            f"but the earliest hour available is {traffic.index.min()}. "
            "Increase --history-hours."
        )

    previous_24 = traffic.loc[
        timestamp - pd.Timedelta(hours=ROLLING_WINDOW) : timestamp - pd.Timedelta(hours=1)
    ]
    return {
        "hour": timestamp.hour,
        "dayofweek": timestamp.dayofweek,
        "is_weekend": int(timestamp.dayofweek >= 5),
        "temp": weather["temp"],
        "clouds_all": weather["clouds_all"],
        "rain_1h": weather["rain_1h"],
        "lag_1": traffic.loc[timestamp - pd.Timedelta(hours=1)],
        "lag_24": traffic.loc[timestamp - pd.Timedelta(hours=24)],
        "lag_168": traffic.loc[timestamp - pd.Timedelta(hours=168)],
        "rolling_mean_24": float(previous_24.mean()),
    }


# --------------------------------------------------------------------------- #
# Step 3 - Load the model
# --------------------------------------------------------------------------- #
def load_model(path: Path):
    if not path.exists():
        raise PredictionError(f"Model file not found: {path}")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model = joblib.load(path)

    for warning in caught:
        if "version" in str(warning.message).lower():
            print(
                "Note: the model was saved with a different scikit-learn version "
                "than the one installed. Predictions still work; for an exact match "
                "use the version pinned in requirements.txt.",
                file=sys.stderr,
            )
            break

    feature_names = list(getattr(model, "feature_names_in_", FEATURE_NAMES))
    unknown = set(feature_names) - set(FEATURE_NAMES)
    if unknown:
        raise PredictionError(
            f"The model expects features this script cannot build: {sorted(unknown)}"
        )
    return model, feature_names


# --------------------------------------------------------------------------- #
# Step 4 - Predict / forecast
# --------------------------------------------------------------------------- #
def forecast(
    model,
    feature_names: list[str],
    clean: pd.DataFrame,
    origin: pd.Timestamp,
    horizon: int,
    weather_overrides: dict[str, float] | None = None,
) -> list[dict]:
    """Forecast `horizon` hours after `origin`.

    For horizons > 1 the forecast is recursive: each predicted hour becomes
    the lag_1 / moving-average input of the next one.

    The model also uses the weather of the target hour. That is not known in
    advance, so we carry the last observed weather forward (persistence)
    unless the caller overrides it.
    """
    traffic = clean["traffic_volume"].copy()
    weather = clean.iloc[-1][WEATHER_COLUMNS].astype(float).to_dict()
    weather.update({k: v for k, v in (weather_overrides or {}).items() if v is not None})

    results = []
    for step in range(1, horizon + 1):
        timestamp = origin + pd.Timedelta(hours=step)
        features = build_feature_row(traffic, weather, timestamp)
        row = pd.DataFrame([features])[feature_names]
        prediction = max(0.0, float(model.predict(row)[0]))

        traffic.loc[timestamp] = prediction  # feeds the next step's lags
        results.append(
            {
                "date_time": timestamp,
                "predicted_traffic_volume": round(prediction),
                "features": {
                    k: int(v) if k in INTEGER_FEATURES else round(float(v), 2)
                    for k, v in features.items()
                },
            }
        )
    return results


def attach_actuals(
    client: httpx.Client, source: str, results: list[dict]
) -> None:
    """If the real values exist in the database, add them for comparison."""
    first, last = results[0]["date_time"], results[-1]["date_time"]
    records = fetch_records_between(client, source, first, last)
    actual = {to_naive_utc(r["date_time"]): r["traffic_volume"] for r in records}
    for item in results:
        item["actual_traffic_volume"] = actual.get(item["date_time"])


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch recent traffic records from the API and forecast traffic volume."
    )
    parser.add_argument("--source", choices=["mysql", "mongodb"], default="mysql",
                        help="Which database endpoint to read from (default: mysql)")
    parser.add_argument("--api-url", default=DEFAULT_API_URL,
                        help=f"Base URL of the API (default: {DEFAULT_API_URL})")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH,
                        help="Path to the trained model (.pkl)")
    parser.add_argument("--horizon", type=int, default=1,
                        help="Hours to forecast after the last record (1-48, default 1)")
    parser.add_argument("--as-of", default=None,
                        help="Forecast as if this was the latest hour, e.g. 2018-09-20T08:00:00. "
                             "Real values are shown next to the forecast when they exist.")
    parser.add_argument("--history-hours", type=int, default=DEFAULT_HISTORY_HOURS,
                        help=f"Hours of history to request (default {DEFAULT_HISTORY_HOURS}, minimum 168)")
    parser.add_argument("--temp-k", type=float, help="Expected temperature in Kelvin")
    parser.add_argument("--rain-1h", type=float, help="Expected rain in mm/hour")
    parser.add_argument("--clouds-all", type=float, help="Expected cloud cover, 0-100")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")

    args = parser.parse_args(argv)
    if not 1 <= args.horizon <= 48:
        parser.error("--horizon must be between 1 and 48")
    if args.history_hours < MAX_LAG_HOURS:
        parser.error(f"--history-hours must be at least {MAX_LAG_HOURS}")
    if args.clouds_all is not None and not 0 <= args.clouds_all <= 100:
        parser.error("--clouds-all must be between 0 and 100")
    if args.rain_1h is not None and args.rain_1h < 0:
        parser.error("--rain-1h must be 0 or more")
    return args


def run(args: argparse.Namespace) -> dict:
    # 3. Load the model first: fail fast before any network call.
    model, feature_names = load_model(args.model)

    with httpx.Client(base_url=args.api_url, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        # 1. Fetch
        as_of = to_naive_utc(args.as_of) if args.as_of else None
        records, origin = fetch_history(client, args.source, args.history_hours, as_of)

        # 2. Preprocess
        clean, imputed_hours = preprocess_history(records_to_frame(records), origin)

        # 4. Predict
        overrides = {"temp": args.temp_k, "rain_1h": args.rain_1h, "clouds_all": args.clouds_all}
        results = forecast(model, feature_names, clean, origin, args.horizon, overrides)

        if args.as_of:
            attach_actuals(client, args.source, results)

    return {
        "source": args.source,
        "model": str(args.model.name),
        "last_observed_hour": origin,
        "last_observed_traffic": int(round(clean["traffic_volume"].iloc[-1])),
        "history": {
            "records_fetched": len(records),
            "window_start": clean.index.min(),
            "window_end": clean.index.max(),
            "hours_imputed": imputed_hours,
        },
        "weather_assumed": {k: round(float(v), 2) for k, v in
                            {**clean.iloc[-1][WEATHER_COLUMNS].astype(float).to_dict(),
                             **{k: v for k, v in {"temp": args.temp_k, "rain_1h": args.rain_1h,
                                                  "clouds_all": args.clouds_all}.items()
                                if v is not None}}.items()},
        "forecasts": results,
    }


def print_report(report: dict) -> None:
    history = report["history"]
    print(f"Traffic forecast  |  source: {report['source']}  |  model: {report['model']}")
    print("-" * 64)
    print(f"Last observed hour : {report['last_observed_hour']:%Y-%m-%d %H:%M} "
          f"({report['last_observed_traffic']} vehicles)")
    print(f"History used       : {history['records_fetched']} records, "
          f"{history['window_start']:%Y-%m-%d %H:%M} -> {history['window_end']:%Y-%m-%d %H:%M}, "
          f"{history['hours_imputed']} missing hour(s) filled")
    weather = report["weather_assumed"]
    print(f"Weather assumed    : temp {weather['temp']} K, rain {weather['rain_1h']} mm, "
          f"clouds {weather['clouds_all']}%")
    print()

    has_actuals = any("actual_traffic_volume" in f for f in report["forecasts"])
    header = f"{'Hour':<18}{'Predicted':>10}"
    if has_actuals:
        header += f"{'Actual':>10}{'Error':>9}"
    print(header)
    for item in report["forecasts"]:
        line = f"{item['date_time']:%Y-%m-%d %H:%M}  {item['predicted_traffic_volume']:>10}"
        if has_actuals:
            actual = item.get("actual_traffic_volume")
            if actual is None:
                line += f"{'n/a':>10}{'':>9}"
            else:
                line += f"{actual:>10}{item['predicted_traffic_volume'] - actual:>+9}"
        print(line)
    print("\n(vehicles per hour on I-94 westbound)")


def _json_default(value):
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    raise TypeError(f"Cannot serialise {type(value)}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run(args)
    except PredictionError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, default=_json_default))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
