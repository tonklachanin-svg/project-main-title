import os
import mysql.connector

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "pea_db"),
    "charset": "utf8mb4"
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)