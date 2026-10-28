from datetime import datetime
from decimal import Decimal
from typing import Any

from api.schemas import TrafficRecordCreate, TrafficRecordUpdate


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
    """Retrieve normalized MySQL rows and assemble traffic records."""

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
    """Retrieve one observation using its MySQL ID."""

    records = _fetch_records(
        connection=connection,
        where_clause="WHERE traffic.obs_id = %s",
        parameters=(observation_id,),
    )

    return records[0] if records else None


def get_latest_record(connection) -> dict | None:
    """Retrieve the observation with the latest timestamp."""

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


def _get_or_create_holiday(
    cursor,
    holiday_name: str | None,
) -> int | None:
    """Return an existing holiday ID or create the holiday."""

    if holiday_name is None:
        return None

    cursor.execute(
        """
        SELECT holiday_id
        FROM holidays
        WHERE holiday_name = %s
        """,
        (holiday_name,),
    )
    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        """
        INSERT INTO holidays (holiday_name)
        VALUES (%s)
        """,
        (holiday_name,),
    )

    return cursor.lastrowid


def _get_or_create_weather_condition(
    cursor,
    weather_main: str,
    weather_description: str,
) -> int:
    """Return an existing weather-condition ID or create it."""

    cursor.execute(
        """
        SELECT condition_id
        FROM weather_conditions
        WHERE weather_main = %s
          AND weather_description = %s
        """,
        (weather_main, weather_description),
    )
    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        """
        INSERT INTO weather_conditions (
            weather_main,
            weather_description
        )
        VALUES (%s, %s)
        """,
        (weather_main, weather_description),
    )

    return cursor.lastrowid


def _insert_weather_readings(
    cursor,
    observation_id: int,
    weather_readings,
) -> None:
    """Insert all weather readings belonging to an observation."""

    for weather in weather_readings:
        condition_id = _get_or_create_weather_condition(
            cursor,
            weather.main,
            weather.description,
        )

        cursor.execute(
            """
            INSERT INTO weather_readings (
                obs_id,
                condition_id,
                temp_k,
                rain_1h,
                snow_1h,
                clouds_all
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                observation_id,
                condition_id,
                weather.temp_k,
                weather.rain_1h,
                weather.snow_1h,
                weather.clouds_all,
            ),
        )


def create_record(
    connection,
    record: TrafficRecordCreate,
) -> dict:
    """Create an observation and its weather readings transactionally."""

    cursor = connection.cursor()

    try:
        connection.start_transaction()

        holiday_id = _get_or_create_holiday(
            cursor,
            record.holiday,
        )

        cursor.execute(
            """
            INSERT INTO traffic_observations (
                date_time,
                traffic_volume,
                holiday_id
            )
            VALUES (%s, %s, %s)
            """,
            (
                record.date_time,
                record.traffic_volume,
                holiday_id,
            ),
        )

        observation_id = cursor.lastrowid

        _insert_weather_readings(
            cursor,
            observation_id,
            record.weather,
        )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()

    return get_record_by_id(connection, observation_id)


def update_record(
    connection,
    observation_id: int,
    record: TrafficRecordUpdate,
) -> dict | None:
    """Replace an observation and its weather readings transactionally."""

    cursor = connection.cursor()

    try:
        connection.start_transaction()

        cursor.execute(
            """
            SELECT obs_id
            FROM traffic_observations
            WHERE obs_id = %s
            FOR UPDATE
            """,
            (observation_id,),
        )

        if cursor.fetchone() is None:
            connection.rollback()
            return None

        holiday_id = _get_or_create_holiday(
            cursor,
            record.holiday,
        )

        cursor.execute(
            """
            UPDATE traffic_observations
            SET
                date_time = %s,
                traffic_volume = %s,
                holiday_id = %s
            WHERE obs_id = %s
            """,
            (
                record.date_time,
                record.traffic_volume,
                holiday_id,
                observation_id,
            ),
        )

        cursor.execute(
            """
            DELETE FROM weather_readings
            WHERE obs_id = %s
            """,
            (observation_id,),
        )

        _insert_weather_readings(
            cursor,
            observation_id,
            record.weather,
        )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()

    return get_record_by_id(connection, observation_id)


def delete_record(
    connection,
    observation_id: int,
) -> bool:
    """Delete an observation and its weather readings transactionally."""

    cursor = connection.cursor()

    try:
        connection.start_transaction()

        cursor.execute(
            """
            SELECT obs_id
            FROM traffic_observations
            WHERE obs_id = %s
            FOR UPDATE
            """,
            (observation_id,),
        )

        if cursor.fetchone() is None:
            connection.rollback()
            return False

        cursor.execute(
            """
            DELETE FROM weather_readings
            WHERE obs_id = %s
            """,
            (observation_id,),
        )

        cursor.execute(
            """
            DELETE FROM traffic_observations
            WHERE obs_id = %s
            """,
            (observation_id,),
        )

        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()