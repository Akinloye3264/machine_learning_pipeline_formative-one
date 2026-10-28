from datetime import datetime, timezone

from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError, PyMongoError

from api.dependencies import mongo_collection
from api.schemas import (
    DeleteResponse,
    TrafficRecordCreate,
    TrafficRecordResponse,
    TrafficRecordUpdate,
)
from api.services.mongodb_service import (
    create_record,
    delete_record,
    get_latest_record,
    get_record_by_id,
    get_records_by_range,
    update_record,
)

router = APIRouter(
    prefix="/api/mongodb/records",
    tags=["MongoDB Records"],
)


def _to_mongodb_datetime(value: datetime) -> datetime:
    """Convert timezone-aware values into naive UTC."""

    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    return value


@router.post(
    "",
    response_model=TrafficRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_mongodb_record(record: TrafficRecordCreate):
    try:
        return create_record(mongo_collection, record)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A record with this timestamp already exists",
        ) from error
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB operation failed",
        ) from error


@router.get(
    "/latest",
    response_model=TrafficRecordResponse,
)
def read_latest_record():
    try:
        record = get_latest_record(mongo_collection)
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB query failed",
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
):
    start = _to_mongodb_datetime(start)
    end = _to_mongodb_datetime(end)

    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start must be earlier than or equal to end",
        )

    try:
        return get_records_by_range(
            mongo_collection,
            start,
            end,
        )
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB query failed",
        ) from error


@router.get(
    "/{document_id}",
    response_model=TrafficRecordResponse,
)
def read_record_by_id(document_id: str):
    try:
        record = get_record_by_id(
            mongo_collection,
            document_id,
        )
    except InvalidId as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MongoDB document ID",
        ) from error
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB query failed",
        ) from error

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Traffic record not found",
        )

    return record


@router.put(
    "/{document_id}",
    response_model=TrafficRecordResponse,
)
def update_mongodb_record(
    document_id: str,
    record: TrafficRecordUpdate,
):
    try:
        updated_record = update_record(
            mongo_collection,
            document_id,
            record,
        )
    except InvalidId as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MongoDB document ID",
        ) from error
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A record with this timestamp already exists",
        ) from error
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB operation failed",
        ) from error

    if updated_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Traffic record not found",
        )

    return updated_record


@router.delete(
    "/{document_id}",
    response_model=DeleteResponse,
)
def delete_mongodb_record(document_id: str):
    try:
        deleted = delete_record(
            mongo_collection,
            document_id,
        )
    except InvalidId as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MongoDB document ID",
        ) from error
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB operation failed",
        ) from error

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Traffic record not found",
        )

    return {
        "message": "Traffic record deleted",
        "id": document_id,
    }