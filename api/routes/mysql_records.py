from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from mysql.connector import Error as MySQLError

from api.dependencies import get_mysql_connection
from api.schemas import TrafficRecordResponse
from api.services.mysql_service import (
    get_latest_record,
    get_record_by_id,
    get_records_by_range,
)

router = APIRouter(
    prefix="/api/mysql/records",
    tags=["MySQL Records"],
)


def _to_mysql_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


@router.get(
    "/latest",
    response_model=TrafficRecordResponse,
)
def read_latest_record(
    connection=Depends(get_mysql_connection),
):
    try:
        record = get_latest_record(connection)
    except MySQLError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL query failed",
        ) from error

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No traffic records found",
        )

    return record


@router.get(
    "/range",
    response_model=list[TrafficRecordResponse],
)
def read_records_by_range(
    start: datetime = Query(...),
    end: datetime = Query(...),
    connection=Depends(get_mysql_connection),
):
    start = _to_mysql_datetime(start)
    end = _to_mysql_datetime(end)

    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start must be earlier than or equal to end",
        )

    try:
        return get_records_by_range(connection, start, end)
    except MySQLError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL query failed",
        ) from error


@router.get(
    "/{observation_id}",
    response_model=TrafficRecordResponse,
)
def read_record_by_id(
    observation_id: int,
    connection=Depends(get_mysql_connection),
):
    try:
        record = get_record_by_id(connection, observation_id)
    except MySQLError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL query failed",
        ) from error

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Traffic record not found",
        )

    return record