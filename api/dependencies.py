import mysql.connector
from pymongo import MongoClient

from api.config import settings


def get_mysql_connection():
    connection = mysql.connector.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
    )

    try:
        yield connection
    finally:
        connection.close()


mongo_client = MongoClient(
    settings.mongodb_uri,
    serverSelectionTimeoutMS=5000,
)

mongo_database = mongo_client[settings.mongodb_database]
mongo_collection = mongo_database["traffic_observations"]