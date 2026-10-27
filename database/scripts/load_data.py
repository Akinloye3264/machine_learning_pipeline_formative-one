import os
from pathlib import Path

import mysql.connector
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_CSV = ROOT / "data" / "raw" / "Metro_Interstate_Traffic_Volume.csv"


def clean(df):
    """Clean the raw CSV. Returns the cleaned dataframe."""
    # Fix inconsistent capitalization 
    df["weather_main"] = df["weather_main"].str.strip().str.lower()
    df["weather_description"] = df["weather_description"].str.strip().str.lower()
   
    # Remove exact duplicate rows
    df = df.drop_duplicates().copy()

    # Parse timestamps
    df["date_time"] = pd.to_datetime(df["date_time"])

    # Sensor errors become NULL instead of being kept or invented
    df.loc[df["temp"] == 0, "temp"] = None          # 0 Kelvin is impossible
    df.loc[df["rain_1h"] > 1000, "rain_1h"] = None  # 9831 mm in one hour is impossible

    # Holiday "None" is not a holiday -> real NULL
    df["holiday"] = df["holiday"].replace("None", None)

    return df


def main():
    load_dotenv(ROOT / ".env")
    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE", "traffic_db"),
    )
    cur = conn.cursor()

    df = pd.read_csv(RAW_CSV, keep_default_na=False)
    df = clean(df)
    df = df.astype(object).where(df.notna(), None)

    try:
        # holidays lookup
        holidays = sorted(h for h in df["holiday"].unique() if h is not None)
        cur.executemany("INSERT INTO holidays (holiday_name) VALUES (%s)",
                        [(h,) for h in holidays])

        # weather_conditions lookup 
        conds = df[["weather_main", "weather_description"]].drop_duplicates()
        cur.executemany(
            "INSERT INTO weather_conditions (weather_main, weather_description) VALUES (%s, %s)",
            list(conds.itertuples(index=False, name=None)))
        conn.commit()

        # Build id lookups
        cur.execute("SELECT holiday_name, holiday_id FROM holidays")
        holiday_ids = dict(cur.fetchall())
        cur.execute("SELECT weather_main, weather_description, condition_id FROM weather_conditions")
        cond_ids = {(m, d): i for m, d, i in cur.fetchall()}

        # traffic_observations: ONE row per unique timestamp (40,575) 
        obs = df.drop_duplicates("date_time")
        obs_rows = [
            (r.date_time.to_pydatetime(), int(r.traffic_volume),
             holiday_ids.get(r.holiday))
            for r in obs.itertuples()
        ]
        cur.executemany(
            "INSERT INTO traffic_observations (date_time, traffic_volume, holiday_id) VALUES (%s, %s, %s)",
            obs_rows)
        conn.commit()

        cur.execute("SELECT date_time, obs_id FROM traffic_observations")
        obs_ids = dict(cur.fetchall())

        # weather_readings: one row per remaining CSV row (48,187)
        read_rows = [
            (obs_ids[r.date_time.to_pydatetime()],
             cond_ids[(r.weather_main, r.weather_description)],
             r.temp, r.rain_1h, r.snow_1h, int(r.clouds_all))
            for r in df.itertuples()
        ]
        cur.executemany(
            """INSERT INTO weather_readings
               (obs_id, condition_id, temp_k, rain_1h, snow_1h, clouds_all)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            read_rows)
        conn.commit()

        for t in ["holidays", "weather_conditions", "traffic_observations", "weather_readings"]:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            print(t, cur.fetchone()[0])
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()