import pytest
from pydantic import ValidationError

from api.schemas import TrafficRecordCreate


def valid_record():
    return {
        "date_time": "2018-10-01T00:00:00",
        "traffic_volume": 450,
        "holiday": None,
        "weather": [
            {
                "main": "Clear",
                "description": "Sky Is Clear",
                "temp_k": 285.5,
                "rain_1h": 0,
                "snow_1h": 0,
                "clouds_all": 20,
            }
        ],
    }


def test_valid_record_is_accepted():
    record = TrafficRecordCreate.model_validate(valid_record())

    assert record.traffic_volume == 450
    assert record.weather[0].main == "clear"
    assert record.weather[0].description == "sky is clear"


def test_negative_traffic_is_rejected():
    data = valid_record()
    data["traffic_volume"] = -1

    with pytest.raises(ValidationError):
        TrafficRecordCreate.model_validate(data)


def test_invalid_cloud_percentage_is_rejected():
    data = valid_record()
    data["weather"][0]["clouds_all"] = 150

    with pytest.raises(ValidationError):
        TrafficRecordCreate.model_validate(data)


def test_empty_weather_list_is_rejected():
    data = valid_record()
    data["weather"] = []

    with pytest.raises(ValidationError):
        TrafficRecordCreate.model_validate(data)


def test_negative_rain_is_rejected():
    data = valid_record()
    data["weather"][0]["rain_1h"] = -2

    with pytest.raises(ValidationError):
        TrafficRecordCreate.model_validate(data)