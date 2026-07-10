import json
from database import get_db


def ensure_table():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS document_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                user_name VARCHAR(255),
                category VARCHAR(255),
                page_key VARCHAR(50),
                page_title VARCHAR(255),
                subject VARCHAR(500),
                data_json LONGTEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_category (category),
                INDEX idx_page_key (page_key),
                INDEX idx_user (user_id),
                INDEX idx_created (created_at)
            ) DEFAULT CHARSET=utf8mb4
            """
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def log_submission(user_id, user_name, category, page_key, page_title, subject, data):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO document_history
                (user_id, user_name, category, page_key, page_title, subject, data_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, user_name, category, page_key, page_title, subject,
             json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()
        new_id = cur.lastrowid
        cur.close()
    finally:
        conn.close()
    return new_id


def seconds_since_last_submission(user_id, page_key):
    """คืนจำนวนวินาทีนับจากการ log ครั้งล่าสุดของ user_id + page_key นี้ (None ถ้าไม่เคย log
    เลย) ใช้กันการ log ซ้ำซ้อนตอนกด "ส่งข้อมูล" ถี่ ๆ ในเวลาไล่เลี่ยกัน (เช่น เน็ตช้าแล้ว
    fetch สองครั้งซ้อนก่อนปุ่มจะ disable ทัน หรือเปิดสองแท็บกดพร้อมกัน)"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TIMESTAMPDIFF(SECOND, created_at, NOW())
            FROM document_history
            WHERE user_id = %s AND page_key = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id, page_key),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    return row[0] if row else None


def search_history(category=None, keyword=None, date_from=None, date_to=None, limit=200):
    conditions = []
    params = []

    if category:
        conditions.append("category = %s")
        params.append(category)

    if keyword:
        conditions.append("(subject LIKE %s OR user_name LIKE %s)")
        like = f"%{keyword}%"
        params.extend([like, like])

    if date_from:
        conditions.append("created_at >= %s")
        params.append(f"{date_from} 00:00:00")

    if date_to:
        conditions.append("created_at <= %s")
        params.append(f"{date_to} 23:59:59")

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            f"""
            SELECT id, user_id, user_name, category, page_key, page_title, subject, created_at
            FROM document_history
            {where_sql}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (*params, limit),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    return rows


def get_history_entry(entry_id):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM document_history WHERE id = %s", (entry_id,))
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    if not row:
        return None

    try:
        row["data"] = json.loads(row["data_json"])
    except (TypeError, ValueError):
        row["data"] = None
    return row


def delete_entry(entry_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM document_history WHERE id = %s", (entry_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        cur.close()
    finally:
        conn.close()
    return deleted
