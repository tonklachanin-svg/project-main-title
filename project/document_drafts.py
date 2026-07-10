import json
import mysql.connector
from database import get_db


def ensure_case_column():
    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE document_drafts ADD COLUMN case_id INT NULL")
            conn.commit()
        except mysql.connector.Error as e:
            if e.errno != 1060:  # 1060 = Duplicate column name
                raise

        cur.execute(
            """
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'document_drafts'
              AND INDEX_NAME = 'uniq_case_page'
            """
        )
        (has_new_key,) = cur.fetchone()
        if not has_new_key:
            cur.execute(
                "ALTER TABLE document_drafts ADD UNIQUE KEY uniq_case_page (user_id, case_id, page_key)"
            )
            conn.commit()

        cur.execute(
            """
            SELECT DISTINCT INDEX_NAME
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'document_drafts'
              AND NON_UNIQUE = 0
              AND INDEX_NAME NOT IN ('PRIMARY', 'uniq_case_page')
            """
        )
        old_keys = [row[0] for row in cur.fetchall()]
        for key_name in old_keys:
            cur.execute(f"ALTER TABLE document_drafts DROP INDEX `{key_name}`")
            conn.commit()

        cur.close()
    finally:
        conn.close()


def get_draft(case_id, page_key):
    if case_id is None:
        return None
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT data_json FROM document_drafts WHERE case_id = %s AND page_key = %s",
            (case_id, page_key),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    if not row:
        return None

    try:
        return json.loads(row["data_json"])
    except (TypeError, ValueError):
        return None


def save_draft(user_id, case_id, page_key, data):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO document_drafts (user_id, case_id, page_key, data_json)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE data_json = VALUES(data_json)
            """,
            (user_id, case_id, page_key, json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
