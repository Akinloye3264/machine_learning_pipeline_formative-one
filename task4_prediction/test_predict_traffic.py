"""Offline tests for the Task 4 script (no API or database needed)."""

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import predict_traffic as pt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def all_records():
    records = []
    with open(ROOT / "database" / "traffic_db_mongodb.jsonl", encoding="utf-8") as file:
        for line in file:
            doc = json.loads(line)
            doc["date_time"] = doc["date_time"]["$date"].replace("Z", "")
            records.append(doc)
    return records


def window(records, start, end):
    return [r for r in records if start <= r["date_time"] <= end]


@pytest.fixture(scope="module")
def model():
    return pt.load_model(pt.DEFAULT_MODEL_PATH)


def test_features_match_task1_processed_csv(all_records):
    """The script must rebuild the same inputs Task 1 gave the model."""
    origin = pd.Timestamp("2018-03-15 11:00")
    target = origin + pd.Timedelta(hours=1)

    records = window(all_records, "2018-03-07T11:00:00", "2018-03-15T11:00:00")
    clean, _ = pt.preprocess_history(pt.records_to_frame(records), origin)
    weather = clean.iloc[-1][pt.WEATHER_COLUMNS].astype(float).to_dict()
    ours = pt.build_feature_row(clean["traffic_volume"], weather, target)

    reference = pd.read_csv(
        ROOT / "data" / "processed" / "metro_traffic_clean.csv", parse_dates=["date_time"]
    ).set_index("date_time")
    row = reference.loc[target]
    for name in ("hour", "dayofweek", "is_weekend", "lag_1", "lag_24", "lag_168"):
        assert ours[name] == pytest.approx(row[name]), name

    # Moving average: Task 1 included the target hour, we use the 24 hours before it.
    expected = reference["traffic_volume"].loc[target - pd.Timedelta(hours=24): origin].mean()
    assert ours["rolling_mean_24"] == pytest.approx(expected)


def test_missing_hours_are_filled_and_flagged(all_records):
    origin = pd.Timestamp("2018-03-15 11:00")
    records = window(all_records, "2018-03-07T11:00:00", "2018-03-15T11:00:00")
    _, baseline = pt.preprocess_history(pt.records_to_frame(records), origin)

    # Remove two more hours that exist in the data.
    removed = ("2018-03-12T03:00:00", "2018-03-12T04:00:00")
    assert sum(r["date_time"] in removed for r in records) == 2
    records = [r for r in records if r["date_time"] not in removed]

    clean, imputed = pt.preprocess_history(pt.records_to_frame(records), origin)

    assert imputed == baseline + 2
    assert not clean.isna().any().any()
    assert clean.index.to_series().diff().dropna().eq(pd.Timedelta(hours=1)).all()


def test_sensor_faults_are_removed():
    records = [
        {"date_time": f"2018-01-01T{h:02d}:00:00", "traffic_volume": 1000,
         "weather": [{"temp_k": t, "rain_1h": r, "snow_1h": 0.0, "clouds_all": 10}]}
        for h, (t, r) in enumerate([(270.0, 0.0), (0.0, 9831.3), (272.0, 0.0)])
    ]
    clean, _ = pt.preprocess_history(pt.records_to_frame(records), pd.Timestamp("2018-01-01 02:00"))

    assert clean["temp"].iloc[1] == pytest.approx(271.0)  # interpolated, not 0 K
    assert clean["rain_1h"].iloc[1] == 0.0                # spike dropped


def test_several_weather_readings_are_averaged():
    records = [{"date_time": "2018-01-01T00:00:00", "traffic_volume": 500,
                "weather": [{"temp_k": 270.0, "rain_1h": 0.0, "snow_1h": 0.0, "clouds_all": 20},
                            {"temp_k": 272.0, "rain_1h": 2.0, "snow_1h": 0.0, "clouds_all": 40}]}]
    frame = pt.records_to_frame(records)
    assert frame.loc[0, "temp"] == 271.0
    assert frame.loc[0, "clouds_all"] == 30.0


def test_not_enough_history_gives_clear_error(all_records):
    origin = pd.Timestamp("2018-03-15 11:00")
    records = window(all_records, "2018-03-14T11:00:00", "2018-03-15T11:00:00")  # only 24h
    clean, _ = pt.preprocess_history(pt.records_to_frame(records), origin)
    with pytest.raises(pt.PredictionError, match="Not enough history"):
        pt.build_feature_row(clean["traffic_volume"],
                             clean.iloc[-1][pt.WEATHER_COLUMNS].to_dict(),
                             origin + pd.Timedelta(hours=1))


def test_multi_step_forecast_is_recursive_and_sane(all_records, model):
    loaded, names = model
    origin = pd.Timestamp("2018-03-15 11:00")
    records = window(all_records, "2018-03-07T11:00:00", "2018-03-15T11:00:00")
    clean, _ = pt.preprocess_history(pt.records_to_frame(records), origin)

    results = pt.forecast(loaded, names, clean, origin, horizon=6)

    assert [r["date_time"] for r in results] == list(
        pd.date_range(origin + pd.Timedelta(hours=1), periods=6, freq="h"))
    assert all(0 <= r["predicted_traffic_volume"] < 8000 for r in results)
    # Step 2 must use step 1's prediction as its lag_1.
    assert results[1]["features"]["lag_1"] == pytest.approx(results[0]["predicted_traffic_volume"], abs=1)


def test_weather_override_changes_inputs(all_records, model):
    loaded, names = model
    origin = pd.Timestamp("2018-03-15 11:00")
    records = window(all_records, "2018-03-07T11:00:00", "2018-03-15T11:00:00")
    clean, _ = pt.preprocess_history(pt.records_to_frame(records), origin)

    result = pt.forecast(loaded, names, clean, origin, 1, {"rain_1h": 5.0, "temp": 260.0})[0]
    assert result["features"]["rain_1h"] == 5.0
    assert result["features"]["temp"] == 260.0


def test_api_down_returns_friendly_error(capsys):
    code = pt.main(["--api-url", "http://127.0.0.1:9"])
    assert code == 1
    assert "Cannot reach the API" in capsys.readouterr().err


@pytest.mark.parametrize("bad", [["--horizon", "0"], ["--horizon", "49"],
                                 ["--history-hours", "100"], ["--clouds-all", "150"]])
def test_bad_arguments_are_rejected(bad):
    with pytest.raises(SystemExit):
        pt.parse_args(bad)
