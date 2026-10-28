from fastapi import Depends, FastAPI
from api.routes.mysql_records import router as mysql_records_router

from api.dependencies import (
    get_mysql_connection,
    mongo_client,
    mongo_collection,
)

app = FastAPI(
    title="Traffic Time-Series API",
    description="CRUD and time-series endpoints for MySQL and MongoDB",
    version="1.0.0",
)
app.include_router(mysql_records_router)

@app.get("/")
def root():
    return {
        "message": "Traffic Time-Series API",
        "documentation": "/docs",
    }


@app.get("/health")
def health(mysql_connection=Depends(get_mysql_connection)):
    cursor = mysql_connection.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM traffic_observations")
        mysql_records = cursor.fetchone()[0]
    finally:
        cursor.close()

    mongo_client.admin.command("ping")
    mongodb_records = mongo_collection.count_documents({})

    return {
        "status": "healthy",
        "databases": {
            "mysql": {
                "status": "connected",
                "records": mysql_records,
            },
            "mongodb": {
                "status": "connected",
                "records": mongodb_records,
            },
        },
    }