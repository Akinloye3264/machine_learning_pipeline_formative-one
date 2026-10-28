from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from mysql.connector import Error as MySQLError
from mysql.connector import IntegrityError

from api.dependencies import get_mysql_connection
from api.schemas import (
    DeleteResponse,
    TrafficRecordCreate,
    TrafficRecordResponse,
    TrafficRecordUpdate,
)
from api.services.mysql_service import (
    create_record,
    delete_record,
    get_latest_record,
    get_record_by_id,
    get_records_by_range,
    update_record,
)

router = APIRouter(
    prefix="/api/mysql/records",
    tags=["MySQL Records"],
)


def _to_mysql_datetime(value: datetime) -> datetime:
    """Convert timezone-aware values into naive UTC for MySQL."""

    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    return value


@router.post(
    "",
    response_model=TrafficRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_mysql_record(
    record: TrafficRecordCreate,
    connection=Depends(get_mysql_connection),
):
    try:
        return create_record(connection, record)
    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A record with this timestamp already exists",
        ) from error
    except MySQLError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL operation failed",
        ) from error


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
        return get_records_by_range(
            connection,
            start,
            end,
        )
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
        record = get_record_by_id(
            connection,
            observation_id,
        )
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


@router.put(
    "/{observation_id}",
    response_model=TrafficRecordResponse,
)
def update_mysql_record(
    observation_id: int,
    record: TrafficRecordUpdate,
    connection=Depends(get_mysql_connection),
):
    try:
        updated_record = update_record(
            connection,
            observation_id,
            record,
        )
    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A record with this timestamp already exists",
        ) from error
    except MySQLError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL operation failed",
        ) from error

    if updated_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Traffic record not found",
        )

    return updated_record


@router.delete(
    "/{observation_id}",
    response_model=DeleteResponse,
)
def delete_mysql_record(
    observation_id: int,
    connection=Depends(get_mysql_connection),
):
    try:
        deleted = delete_record(
            connection,
            observation_id,
        )
    except MySQLError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL operation failed",
        ) from error

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Traffic record not found",
        )

    return {
        "message": "Traffic record deleted",
        "id": observation_id,
    }