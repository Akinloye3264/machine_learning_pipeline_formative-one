"""Reproduce the Task 4 recursive multi-horizon benchmark."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "task4_prediction"))

import predict_traffic as pt  # noqa: E402

DATA_PATH = ROOT / "database" / "traffic_db_mongodb.jsonl"
OUTPUT_DIR = ROOT / "task4_prediction" / "results"

SAMPLE_SIZE = 207
HORIZONS = (1, 3, 6, 12, 24)


def load_hourly_data() -> pd.DataFrame:
    records = []

    with DATA_PATH.open(encoding="utf-8") as file:
        for line in file:
            document = json.loads(line)
            document["date_time"] = document["date_time"]["$date"]
            records.append(document)

    frame = pt.records_to_frame(records)

    return (
        frame.groupby("date_time")
        .mean(numeric_only=True)
        .sort_index()
    )


def select_origins(hourly: pd.DataFrame) -> list[pd.Timestamp]:
    """Select 207 evenly spaced 2018 origins with 24 hours of actuals."""

    available = set(hourly.index)

    candidate_hours = pd.date_range(
        "2018-01-01 00:00:00",
        "2018-09-29 23:00:00",
        freq="h",
    )

    eligible = [
        origin
        for origin in candidate_hours
        if origin in available
        and all(
            origin + pd.Timedelta(hours=lead) in available
            for lead in range(1, 25)
        )
    ]

    if len(eligible) < SAMPLE_SIZE:
        raise RuntimeError(
            f"Only {len(eligible)} eligible origins were found; "
            f"{SAMPLE_SIZE} are required."
        )

    positions = np.linspace(
        0,
        len(eligible) - 1,
        SAMPLE_SIZE,
        dtype=int,
    )

    origins = [eligible[position] for position in positions]

    print(f"Eligible origins: {len(eligible)}")
    print(f"Selected origins: {len(origins)}")
    print(f"First origin:     {origins[0]}")
    print(f"Last origin:      {origins[-1]}")

    return origins


def run_benchmark(
    hourly: pd.DataFrame,
    origins: list[pd.Timestamp],
) -> pd.DataFrame:
    model, feature_names = pt.load_model(pt.DEFAULT_MODEL_PATH)
    rows = []

    for number, origin in enumerate(origins, start=1):
        history_start = origin - pd.Timedelta(
            hours=pt.DEFAULT_HISTORY_HOURS
        )

        history = hourly.loc[history_start:origin].reset_index()

        clean, imputed_hours = pt.preprocess_history(
            history,
            origin,
        )

        forecasts = pt.forecast(
            model,
            feature_names,
            clean,
            origin,
            horizon=max(HORIZONS),
        )

        for horizon in HORIZONS:
            target = origin + pd.Timedelta(hours=horizon)
            prediction = forecasts[horizon - 1][
                "predicted_traffic_volume"
            ]
            actual = float(hourly.loc[target, "traffic_volume"])

            rows.append(
                {
                    "origin": origin,
                    "target": target,
                    "horizon_hours": horizon,
                    "predicted_traffic_volume": prediction,
                    "actual_traffic_volume": actual,
                    "absolute_error": abs(prediction - actual),
                    "history_hours_imputed": imputed_hours,
                }
            )

        if number % 25 == 0 or number == len(origins):
            print(f"Completed {number}/{len(origins)} origins")

    return pd.DataFrame(rows)


def save_results(details: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summary = (
        details.groupby("horizon_hours", as_index=False)
        .agg(
            mae_vehicles=("absolute_error", "mean"),
            evaluated_origins=("origin", "count"),
        )
    )

    summary["mae_vehicles"] = summary["mae_vehicles"].round(2)

    details_path = OUTPUT_DIR / "forecast_benchmark_details.csv"
    summary_path = OUTPUT_DIR / "forecast_benchmark_summary.csv"
    figure_path = OUTPUT_DIR / "forecast_mae_by_horizon.png"

    details.to_csv(details_path, index=False)
    summary.to_csv(summary_path, index=False)

    figure, axis = plt.subplots(figsize=(8, 5))
    axis.plot(
        summary["horizon_hours"],
        summary["mae_vehicles"],
        marker="o",
        linewidth=2,
    )
    axis.set_title("Recursive forecast error by horizon")
    axis.set_xlabel("Forecast horizon (hours)")
    axis.set_ylabel("Mean absolute error (vehicles/hour)")
    axis.set_xticks(list(HORIZONS))
    axis.grid(alpha=0.3)
    figure.tight_layout()
    figure.savefig(figure_path, dpi=200)
    plt.close(figure)

    print("\nBenchmark summary:")
    print(summary.to_string(index=False))
    print(f"\nSaved: {details_path}")
    print(f"Saved: {summary_path}")
    print(f"Saved: {figure_path}")


def main() -> None:
    hourly = load_hourly_data()
    origins = select_origins(hourly)
    details = run_benchmark(hourly, origins)
    save_results(details)


if __name__ == "__main__":
    main()