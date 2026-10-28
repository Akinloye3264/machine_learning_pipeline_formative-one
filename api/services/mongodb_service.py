from datetime import datetime

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, ReturnDocument

from api.schemas import TrafficRecordCreate, TrafficRecordUpdate


def _serialize_document(document: dict | None) -> dict | None:
    """Convert a MongoDB document into the common API response format."""

    if document is None:
        return None

    return {
        "id": str(document["_id"]),
        "date_time": document["date_time"],
        "traffic_volume": document["traffic_volume"],
        "holiday": document.get("holiday"),
        "weather": document["weather"],
    }


def _record_to_document(
    record: TrafficRecordCreate | TrafficRecordUpdate,
) -> dict:
    """Convert a validated request model into a MongoDB document."""

    document = record.model_dump()

    # Existing MongoDB documents omit holiday when it is not applicable.
    if document["holiday"] is None:
        document.pop("holiday")

    return document


def create_record(
    collection,
    record: TrafficRecordCreate,
) -> dict:
    """Insert and return a new MongoDB traffic record."""

    document = _record_to_document(record)
    result = collection.insert_one(document)

    created_document = collection.find_one(
        {"_id": result.inserted_id}
    )

    return _serialize_document(created_document)


def get_record_by_id(
    collection,
    document_id: str,
) -> dict | None:
    """Retrieve a MongoDB traffic record by ObjectId."""

    document = collection.find_one(
        {"_id": ObjectId(document_id)}
    )

    return _serialize_document(document)


def get_latest_record(collection) -> dict | None:
    """Retrieve the record with the latest timestamp."""

    document = collection.find_one(
        {},
        sort=[("date_time", DESCENDING)],
    )

    return _serialize_document(document)


def get_records_by_range(
    collection,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Retrieve records within an inclusive timestamp range."""

    documents = collection.find(
        {
            "date_time": {
                "$gte": start,
                "$lte": end,
            }
        }
    ).sort(
        [
            ("date_time", ASCENDING),
            ("_id", ASCENDING),
        ]
    )

    return [
        _serialize_document(document)
        for document in documents
    ]


def update_record(
    collection,
    document_id: str,
    record: TrafficRecordUpdate,
) -> dict | None:
    """Replace and return an existing MongoDB traffic record."""

    replacement = _record_to_document(record)

    updated_document = collection.find_one_and_replace(
        {"_id": ObjectId(document_id)},
        replacement,
        return_document=ReturnDocument.AFTER,
    )

    return _serialize_document(updated_document)


def delete_record(
    collection,
    document_id: str,
) -> bool:
    """Delete a MongoDB traffic record."""

    result = collection.delete_one(
        {"_id": ObjectId(document_id)}
    )

    return result.deleted_count == 1