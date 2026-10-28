from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WeatherReading(BaseModel):
    main: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1, max_length=255)
    temp_k: float | None = None
    rain_1h: float | None = Field(default=None, ge=0)
    snow_1h: float | None = Field(default=None, ge=0)
    clouds_all: int = Field(ge=0, le=100)

    @field_validator("main", "description")
    @classmethod
    def normalize_weather_text(cls, value: str) -> str:
        return value.strip().lower()


class TrafficRecordCreate(BaseModel):
    date_time: datetime
    traffic_volume: int = Field(ge=0)
    holiday: str | None = Field(default=None, max_length=50)
    weather: list[WeatherReading] = Field(min_length=1)

    @field_validator("date_time")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        # MySQL stores naive datetimes. Convert timezone-aware inputs to UTC.
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    @field_validator("holiday")
    @classmethod
    def normalize_holiday(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None


class TrafficRecordUpdate(TrafficRecordCreate):
    """PUT replaces the complete traffic record."""


class TrafficRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | str
    date_time: datetime
    traffic_volume: int
    holiday: str | None = None
    weather: list[WeatherReading]


class DeleteResponse(BaseModel):
    message: str
    id: int | str