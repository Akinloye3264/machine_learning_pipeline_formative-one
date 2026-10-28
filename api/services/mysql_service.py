from datetime import datetime
from decimal import Decimal
from typing import Any


def _to_float(value: Decimal | float | None) -> float | None:
    """Convert MySQL decimal values into JSON-compatible floats."""
    if value is None:
        return None

    return float(value)


def _fetch_records(
    connection,
    where_clause: str = "",
    parameters: tuple[Any, ...] = (),
) -> list[dict]:
    """Retrieve and assemble normalized MySQL rows as traffic records."""

    query = f"""
        SELECT
            traffic.obs_id,
            traffic.date_time,
            traffic.traffic_volume,
            holiday.holiday_name,
            reading.reading_id,
            weather_condition.weather_main,
            weather_condition.weather_description,
            reading.temp_k,
            reading.rain_1h,
            reading.snow_1h,
            reading.clouds_all
        FROM traffic_observations AS traffic
        LEFT JOIN holidays AS holiday
            ON holiday.holiday_id = traffic.holiday_id
        INNER JOIN weather_readings AS reading
            ON reading.obs_id = traffic.obs_id
        INNER JOIN weather_conditions AS weather_condition
            ON weather_condition.condition_id = reading.condition_id
        {where_clause}
        ORDER BY
            traffic.date_time ASC,
            reading.reading_id ASC
    """

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(query, parameters)
        rows = cursor.fetchall()
    finally:
        cursor.close()

    records: dict[int, dict] = {}

    for row in rows:
        observation_id = row["obs_id"]

        if observation_id not in records:
            records[observation_id] = {
                "id": observation_id,
                "date_time": row["date_time"],
                "traffic_volume": row["traffic_volume"],
                "holiday": row["holiday_name"],
                "weather": [],
            }

        records[observation_id]["weather"].append(
            {
                "main": row["weather_main"],
                "description": row["weather_description"],
                "temp_k": _to_float(row["temp_k"]),
                "rain_1h": _to_float(row["rain_1h"]),
                "snow_1h": _to_float(row["snow_1h"]),
                "clouds_all": row["clouds_all"],
            }
        )

    return list(records.values())


def get_record_by_id(
    connection,
    observation_id: int,
) -> dict | None:
    """Retrieve one traffic observation using its MySQL ID."""

    records = _fetch_records(
        connection=connection,
        where_clause="WHERE traffic.obs_id = %s",
        parameters=(observation_id,),
    )

    return records[0] if records else None


def get_latest_record(connection) -> dict | None:
    """Retrieve the traffic observation with the latest timestamp."""

    records = _fetch_records(
        connection=connection,
        where_clause="""
            WHERE traffic.date_time = (
                SELECT MAX(date_time)
                FROM traffic_observations
            )
        """,
    )

    return records[0] if records else None


def get_records_by_range(
    connection,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Retrieve observations within an inclusive timestamp range."""

    return _fetch_records(
        connection=connection,
        where_clause="""
            WHERE traffic.date_time BETWEEN %s AND %s
        """,
        parameters=(start, end),
    )