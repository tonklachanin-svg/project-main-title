import mysql.connector

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "pea_db",
    "charset": "utf8mb4"
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)