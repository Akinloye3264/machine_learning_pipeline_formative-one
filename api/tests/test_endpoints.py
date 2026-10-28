from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_mysql_connection, mongo_collection
from api.main import app

client = TestClient(app)

MYSQL_TEST_DATE = datetime(2035, 1, 15, 8)
MONGODB_TEST_DATE = datetime(2035, 1, 16, 8)


def build_payload(date_time: datetime, traffic_volume: int = 3875):
    return {
        "date_time": date_time.isoformat(),
        "traffic_volume": traffic_volume,
        "holiday": None,
        "weather": [
            {
                "main": "rain",
                "description": "light rain",
                "temp_k": 279.45,
                "rain_1h": 1.7,
                "snow_1h": 0,
                "clouds_all": 85,
            },
            {
                "main": "mist",
                "description": "mist",
                "temp_k": 279.45,
                "rain_1h": 0,
                "snow_1h": 0,
                "clouds_all": 85,
            },
        ],
    }


def clean_mysql_test_record():
    connection_generator = get_mysql_connection()
    connection = next(connection_generator)
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT obs_id
            FROM traffic_observations
            WHERE date_time = %s
            """,
            (MYSQL_TEST_DATE,),
        )
        row = cursor.fetchone()

        if row:
            observation_id = row[0]

            cursor.execute(
                "DELETE FROM weather_readings WHERE obs_id = %s",
                (observation_id,),
            )
            cursor.execute(
                "DELETE FROM traffic_observations WHERE obs_id = %s",
                (observation_id,),
            )

        connection.commit()
    finally:
        cursor.close()
        connection_generator.close()


def clean_mongodb_test_record():
    mongo_collection.delete_many(
        {
            "date_time": {
                "$in": [
                    MYSQL_TEST_DATE,
                    MONGODB_TEST_DATE,
                ]
            }
        }
    )


@pytest.fixture(autouse=True)
def clean_test_records():
    clean_mysql_test_record()
    clean_mongodb_test_record()

    yield

    clean_mysql_test_record()
    clean_mongodb_test_record()


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["databases"]["mysql"]["status"] == "connected"
    assert response.json()["databases"]["mongodb"]["status"] == "connected"


def test_mysql_crud_and_time_series_endpoints():
    payload = build_payload(MYSQL_TEST_DATE)

    create_response = client.post(
        "/api/mysql/records",
        json=payload,
    )
    assert create_response.status_code == 201

    created = create_response.json()
    observation_id = created["id"]

    assert isinstance(observation_id, int)
    assert created["traffic_volume"] == 3875
    assert len(created["weather"]) == 2

    duplicate_response = client.post(
        "/api/mysql/records",
        json=payload,
    )
    assert duplicate_response.status_code == 409

    get_response = client.get(
        f"/api/mysql/records/{observation_id}"
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == observation_id

    latest_response = client.get(
        "/api/mysql/records/latest"
    )
    assert latest_response.status_code == 200
    assert latest_response.json()["id"] == observation_id

    range_response = client.get(
        "/api/mysql/records/range",
        params={
            "start": (
                MYSQL_TEST_DATE - timedelta(hours=1)
            ).isoformat(),
            "end": (
                MYSQL_TEST_DATE + timedelta(hours=1)
            ).isoformat(),
        },
    )
    assert range_response.status_code == 200
    assert len(range_response.json()) == 1

    updated_payload = build_payload(
        MYSQL_TEST_DATE,
        traffic_volume=4100,
    )
    update_response = client.put(
        f"/api/mysql/records/{observation_id}",
        json=updated_payload,
    )
    assert update_response.status_code == 200
    assert update_response.json()["traffic_volume"] == 4100

    delete_response = client.delete(
        f"/api/mysql/records/{observation_id}"
    )
    assert delete_response.status_code == 200

    missing_response = client.get(
        f"/api/mysql/records/{observation_id}"
    )
    assert missing_response.status_code == 404


def test_mongodb_crud_and_time_series_endpoints():
    payload = build_payload(MONGODB_TEST_DATE)

    create_response = client.post(
        "/api/mongodb/records",
        json=payload,
    )
    assert create_response.status_code == 201

    created = create_response.json()
    document_id = created["id"]

    assert isinstance(document_id, str)
    assert len(document_id) == 24
    assert created["traffic_volume"] == 3875
    assert len(created["weather"]) == 2

    duplicate_response = client.post(
        "/api/mongodb/records",
        json=payload,
    )
    assert duplicate_response.status_code == 409

    get_response = client.get(
        f"/api/mongodb/records/{document_id}"
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == document_id

    latest_response = client.get(
        "/api/mongodb/records/latest"
    )
    assert latest_response.status_code == 200
    assert latest_response.json()["id"] == document_id

    range_response = client.get(
        "/api/mongodb/records/range",
        params={
            "start": (
                MONGODB_TEST_DATE - timedelta(hours=1)
            ).isoformat(),
            "end": (
                MONGODB_TEST_DATE + timedelta(hours=1)
            ).isoformat(),
        },
    )
    assert range_response.status_code == 200
    assert len(range_response.json()) == 1

    updated_payload = build_payload(
        MONGODB_TEST_DATE,
        traffic_volume=4100,
    )
    update_response = client.put(
        f"/api/mongodb/records/{document_id}",
        json=updated_payload,
    )
    assert update_response.status_code == 200
    assert update_response.json()["traffic_volume"] == 4100

    delete_response = client.delete(
        f"/api/mongodb/records/{document_id}"
    )
    assert delete_response.status_code == 200

    missing_response = client.get(
        f"/api/mongodb/records/{document_id}"
    )
    assert missing_response.status_code == 404


@pytest.mark.parametrize("database", ["mysql", "mongodb"])
def test_invalid_date_range(database):
    response = client.get(
        f"/api/{database}/records/range",
        params={
            "start": "2035-01-20T10:00:00",
            "end": "2035-01-20T09:00:00",
        },
    )

    assert response.status_code == 400