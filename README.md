# Metro Interstate Traffic Time-Series Pipeline

A complete time-series data pipeline using the Metro Interstate Traffic Volume dataset. The project includes exploratory analysis, feature engineering, forecasting, MySQL and MongoDB implementations, REST API endpoints, and prediction integration.

## Project objective

The project predicts hourly traffic volume using historical traffic, weather, calendar, lag, and moving-average features.

The prediction target is:

```text
traffic_volume
```

The timestamp column is:

```text
date_time
```

## Project structure

```text
api/
├── main.py
├── config.py
├── dependencies.py
├── schemas.py
├── routes/
├── services/
└── tests/

data/
├── raw/
└── processed/

database/
├── diagram/
├── scripts/
├── sql/
├── traffic_db_mysql.sql
└── traffic_db_mongodb.jsonl

task1_eda_ml/
├── task1_eda_and_lags.ipynb
└── traffic_forecasting_model.pkl

task4_prediction/
├── predict_traffic.py
└── test_predict_traffic.py
```

## Completed tasks

### Task 1: EDA and machine learning

- Time-series cleaning and preprocessing
- Missing interval and outlier handling
- Lag features: 1, 24 and 168 hours
- Moving averages: 24 and 168 hours
- Random Forest forecasting experiments
- Saved forecasting model

### Task 2: Database design

MySQL uses four normalized tables:

- `traffic_observations`
- `weather_readings`
- `weather_conditions`
- `holidays`

MongoDB uses the `traffic_observations` collection with embedded weather readings.

### Task 3: REST API

The FastAPI application provides CRUD and time-series queries for both MySQL and MongoDB.

### Task 4: Prediction integration

`task4_prediction/predict_traffic.py` runs the full forecasting pipeline:

1. **Fetch** the latest record and the previous 8 days of hourly records from the API (`/latest` and `/range`)
2. **Preprocess** them with the Task 1 rules: sensor faults removed, duplicate hours averaged, a complete hourly index, interpolation of temperature and clouds, rain and snow filled with 0, forward-fill of traffic
3. **Load** `task1_eda_ml/traffic_forecasting_model.pkl`
4. **Predict** the next hour (or the next N hours) of `traffic_volume`

Start the API first, then run from the repository root:

```powershell
python task4_prediction/predict_traffic.py                                  # next hour, MySQL
python task4_prediction/predict_traffic.py --source mongodb --horizon 6     # next 6 hours, MongoDB
python task4_prediction/predict_traffic.py --as-of 2018-09-20T06:00:00 --horizon 6   # backtest vs real values
python task4_prediction/predict_traffic.py --json                           # machine-readable output
```

Notes:

- The model uses the weather of the hour it predicts. Future weather is unknown, so the last observed weather is carried forward. Override it with `--temp-k`, `--rain-1h` and `--clouds-all`.
- With `--horizon` above 1 the forecast is recursive: each predicted hour feeds the lags of the next one, so error grows with the horizon.
- The moving average uses the 24 hours **before** the target hour. In Task 1 it also included the target hour itself; on the 2018 test set this changes MAE from 155.0 to 157.1.
- The dataset ends on 2018-09-30 23:00, so the default run forecasts 2018-10-01 00:00. Use `--as-of` to compare forecasts with real values.
- The model was saved with scikit-learn 1.6.1, which is pinned in `requirements.txt`.

Run the offline tests (no database needed):

```powershell
pytest task4_prediction -v
```

## Requirements

- Python 3.11 or later
- MySQL Server 8
- MongoDB
- MongoDB Database Tools
- Git

## Installation

Clone the repository and create a virtual environment:

```powershell
git clone https://github.com/Akinloye3264/machine_learning_pipeline_formative-one.git
cd machine_learning_pipeline_formative-one

py -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
```

## Environment configuration

Copy `.env.example` to `.env` and provide the local credentials:

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=traffic_db

MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=traffic_db
```

Never commit `.env`.

## Restore MySQL

From the repository root:

```powershell
mysql -u root -p --execute="source database/traffic_db_mysql.sql"
```

Verify:

```sql
USE traffic_db;
SELECT COUNT(*) FROM traffic_observations;
SELECT COUNT(*) FROM weather_readings;
```

Expected approximate counts:

```text
traffic_observations: 40575
weather_readings: 48187
```

## Restore MongoDB

```powershell
mongoimport --uri "mongodb://localhost:27017" --db "traffic_db" --collection "traffic_observations" --file "database\traffic_db_mongodb.jsonl"
```

Create the timestamp index:

```powershell
mongosh --quiet --eval "db.getSiblingDB('traffic_db').traffic_observations.createIndex({date_time:1},{unique:true})"
```

Verify:

```powershell
mongosh --quiet --eval "db.getSiblingDB('traffic_db').traffic_observations.countDocuments({})"
```

Expected:

```text
40575
```

## Run the API

```powershell
uvicorn api.main:app --reload
```

Open:

- API home: `http://127.0.0.1:8000/`
- Health check: `http://127.0.0.1:8000/health`
- Swagger documentation: `http://127.0.0.1:8000/docs`
- ReDoc documentation: `http://127.0.0.1:8000/redoc`

## API endpoints

| Method | MySQL endpoint | MongoDB endpoint | Purpose |
|---|---|---|---|
| POST | `/api/mysql/records` | `/api/mongodb/records` | Create a record |
| GET | `/api/mysql/records/{id}` | `/api/mongodb/records/{id}` | Retrieve a record |
| PUT | `/api/mysql/records/{id}` | `/api/mongodb/records/{id}` | Replace a record |
| DELETE | `/api/mysql/records/{id}` | `/api/mongodb/records/{id}` | Delete a record |
| GET | `/api/mysql/records/latest` | `/api/mongodb/records/latest` | Retrieve the latest record |
| GET | `/api/mysql/records/range` | `/api/mongodb/records/range` | Retrieve a date range |

Date-range parameters:

```text
?start=2012-10-02T09:00:00&end=2012-10-02T12:00:00
```

## Example request

```json
{
  "date_time": "2030-01-15T08:00:00",
  "traffic_volume": 3875,
  "holiday": null,
  "weather": [
    {
      "main": "rain",
      "description": "light rain",
      "temp_k": 279.45,
      "rain_1h": 1.7,
      "snow_1h": 0,
      "clouds_all": 85
    }
  ]
}
```

## Validation and error responses

The API validates:

- Non-negative traffic volume
- Valid timestamps
- At least one weather reading
- Cloud percentage between 0 and 100
- Non-negative rain and snow measurements
- Unique timestamps
- Valid MongoDB ObjectIds
- Correct date-range ordering

Common responses include:

- `201`: record created
- `400`: invalid ID or date range
- `404`: record not found
- `409`: duplicate timestamp
- `422`: invalid request body
- `503`: database unavailable

## Testing

The tests use local development databases and automatically remove their test records.

Run:

```powershell
pytest -v
```

The current suite contains:

- Schema validation tests
- MySQL CRUD tests
- MongoDB CRUD tests
- Latest-record tests
- Date-range tests
- Duplicate timestamp tests
- Invalid date-range tests
- Health endpoint tests

## Team contributions

| Member | Main contribution |
|---|---|
| Ptuyizere | Task 1: EDA, preprocessing, feature engineering and model training |
| Jonathan Mugisha | Task 2: MySQL, MongoDB, queries and ERD |
| Akinloye | Task 3: FastAPI, CRUD, time-series endpoints and API tests |
| Add fourth member’s name | Task 4: prediction and forecasting integration |

Replace the displayed names with the formal names required in the final report.

## Security

- Database credentials are stored in `.env`.
- `.env` is excluded from Git.
- SQL queries use parameterized values.
- MySQL writes use transactions and rollback on failure.
- API responses do not expose database credentials or internal exceptions.