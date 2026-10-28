# Corrections and Handoff Notes for Task 4

## Purpose

Task 4 must fetch time-series data through the Task 3 API, reproduce the preprocessing used for model training, load the saved model, and generate a traffic-volume prediction or forecast.

Member 4 should use the API rather than connecting directly to MySQL or MongoDB.

## Critical corrections before integration

### 1. Remove target leakage from the rolling average

The Task 1 notebook currently calculates the 24-hour rolling mean with:

```python
df_clean["rolling_mean_24"] = (
    df_clean["traffic_volume"].rolling(24).mean()
)
```

This includes the current `traffic_volume` target in the feature used to predict that same target. A real forecast cannot use the value it is trying to predict.

Change it to:

```python
df_clean["rolling_mean_24"] = (
    df_clean["traffic_volume"]
    .shift(1)
    .rolling(24)
    .mean()
)
```

After this change, retrain the Random Forest and replace the existing `.pkl` model. The experiment metrics in the notebook and report must also be updated.

### 2. Clean sensor outliers before hourly aggregation

The Task 1 notebook currently creates `df_hourly` before modifying outliers in `df`. Consequently, those corrections do not propagate into `df_clean`.

Move this code:

```python
df.loc[df["temp"] < 100, "temp"] = np.nan
df.loc[df["rain_1h"] > 500, "rain_1h"] = np.nan
```

so that it runs before:

```python
df_hourly = df.groupby("date_time").mean(numeric_only=True)
```

Then repeat the cleaning, feature engineering, training, evaluation, and model export.

## API endpoint to use

Use either database implementation through its date-range endpoint:

```text
GET /api/mysql/records/range
GET /api/mongodb/records/range
```

Example request:

```text
http://127.0.0.1:8000/api/mysql/records/range?start=2018-09-16T23:00:00&end=2018-09-30T23:00:00
```

Fetching only the latest record is insufficient because the model requires 1-hour, 24-hour, and 168-hour lag values. Fetch approximately 14 days so missing hourly intervals can be reconstructed safely.

Start the API before running the prediction script:

```powershell
uvicorn api.main:app --reload
```

## Convert the API response into model data

### 1. Flatten the weather array

The API returns one traffic observation with an embedded list of weather readings:

```json
{
  "date_time": "2012-10-02T10:00:00",
  "traffic_volume": 4516,
  "holiday": null,
  "weather": [
    {
      "main": "clouds",
      "description": "broken clouds",
      "temp_k": 289.36,
      "rain_1h": 0,
      "snow_1h": 0,
      "clouds_all": 75
    }
  ]
}
```

The model requires one row per hour. When an observation contains multiple weather readings, calculate the mean of these numerical fields:

- `temp_k`
- `rain_1h`
- `snow_1h`
- `clouds_all`

This matches the numerical hourly aggregation used in Task 1.

### 2. Rename the temperature field

The API and databases use `temp_k`, while the trained model expects `temp`:

```python
df = df.rename(columns={"temp_k": "temp"})
```

### 3. Parse, sort, and index timestamps

```python
df["date_time"] = pd.to_datetime(df["date_time"])
df = df.sort_values("date_time").set_index("date_time")
```

### 4. Reconstruct missing hourly intervals

Task 2 stores raw unique timestamps, and the source data contains missing hours. Reindex the API result to a complete hourly timeline:

```python
full_timeline = pd.date_range(
    start=df.index.min(),
    end=df.index.max(),
    freq="h",
)

df = df.reindex(full_timeline)
df.index.name = "date_time"
```

### 5. Apply the training-time imputation rules

```python
df["temp"] = df["temp"].interpolate(method="time")
df["clouds_all"] = df["clouds_all"].interpolate(method="time")

df["rain_1h"] = df["rain_1h"].fillna(0.0)
df["snow_1h"] = df["snow_1h"].fillna(0.0)

df["traffic_volume"] = df["traffic_volume"].ffill().bfill()
```

For a genuine future forecast, do not fill the unknown future target. Calculate its lag and rolling features only from earlier observations.

## Required feature engineering

```python
df["hour"] = df.index.hour
df["dayofweek"] = df.index.dayofweek
df["is_weekend"] = df["dayofweek"].isin([5, 6]).astype(int)

df["lag_1"] = df["traffic_volume"].shift(1)
df["lag_24"] = df["traffic_volume"].shift(24)
df["lag_168"] = df["traffic_volume"].shift(168)

df["rolling_mean_24"] = (
    df["traffic_volume"]
    .shift(1)
    .rolling(24)
    .mean()
)
```

`rolling_mean_168` was created during EDA but is not an input to the saved final model.

## Exact feature order

The prediction DataFrame must use the same feature names and order used during training:

```python
FEATURES = [
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
```

Before prediction:

```python
prediction_features = prediction_row[FEATURES]
prediction = model.predict(prediction_features)
```

The Random Forest does not require feature scaling.

## Model compatibility checks

Load and inspect the model:

```python
import joblib

model = joblib.load(
    "task1_eda_ml/traffic_forecasting_model.pkl"
)

print(model.n_features_in_)
print(model.feature_names_in_)
```

Expected feature count:

```text
10
```

If the model produces a scikit-learn version warning or cannot be loaded, retrain and save it from the current project environment. Pin that scikit-learn version in `requirements.txt` so every group member uses a compatible version.

## Dependencies to add

The current API requirements do not include the machine-learning packages. Add:

```text
pandas
numpy
scikit-learn
joblib
```

Use the existing `httpx` package to call the API, or add `requests` if the prediction script is written with `requests`.

## Recommended Task 4 files

```text
task4_prediction/
├── __init__.py
├── preprocessing.py
├── predict.py
└── test_prediction.py
```

- `preprocessing.py`: flatten API records, reindex time, impute data, and create features.
- `predict.py`: call the API, load the model, select the latest complete feature row, and produce a forecast.
- `test_prediction.py`: verify the end-to-end prediction workflow and feature order.

## Recommended prediction flow

```text
Start the FastAPI application
        ↓
Fetch approximately 14 days from a date-range endpoint
        ↓
Flatten embedded weather arrays
        ↓
Rename temp_k to temp
        ↓
Reconstruct missing hourly intervals
        ↓
Apply the Task 1 imputation rules
        ↓
Create calendar, lag, and leakage-safe rolling features
        ↓
Load the retrained model
        ↓
Select the ten features in the exact training order
        ↓
Generate and display the traffic-volume forecast
```

## Error handling requirements

The prediction script should provide clear errors when:

- The API is unavailable.
- An API request returns a non-success status.
- Fewer than 169 reconstructed hourly observations are available.
- Weather values cannot be imputed.
- Required feature columns are missing.
- The model cannot be loaded.
- The model feature count or feature names do not match.

## Git workflow

1. Merge the Task 3 `API` branch into `main`.
2. Pull the updated `main` branch.
3. Create a separate Task 4 branch.
4. Retrain and replace the model after applying the corrections above.
5. Add the prediction and preprocessing scripts.
6. Add automated tests and update the README.
7. Make at least four clear, meaningful commits for the Task 4 contribution.

