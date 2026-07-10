import json
from database import get_db


def ensure_table():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS document_cases (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                user_name VARCHAR(255),
                category VARCHAR(255),
                subject VARCHAR(500),
                budget_amount VARCHAR(100),
                status VARCHAR(20) NOT NULL DEFAULT 'open',
                history_entry_id INT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_user (user_id),
                CONSTRAINT fk_document_cases_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            ) DEFAULT CHARSET=utf8mb4
            """
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def list_cases(user_id, keyword=None, status=None):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM document_cases WHERE user_id = %s ORDER BY created_at ASC",
            (user_id,),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    for i, row in enumerate(rows, start=1):
        row['seq_display'] = f"{i:04d}"

    if keyword:
        kw = keyword.lower()
        rows = [
            r for r in rows
            if kw in (r.get('subject') or '').lower() or kw in (r.get('category') or '').lower()
        ]

    if status:
        rows = [r for r in rows if r['status'] == status]

    return rows


def get_case(case_id, user_id=None):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        if user_id is not None:
            cur.execute("SELECT * FROM document_cases WHERE id = %s AND user_id = %s", (case_id, user_id))
        else:
            cur.execute("SELECT * FROM document_cases WHERE id = %s", (case_id,))
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    return row


def create_case(user_id, user_name, category):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO document_cases (user_id, user_name, category, status) VALUES (%s, %s, %s, 'open')",
            (user_id, user_name, category),
        )
        conn.commit()
        new_id = cur.lastrowid
        cur.close()
    finally:
        conn.close()
    return new_id


def mark_in_progress(case_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE document_cases SET status = 'in_progress' WHERE id = %s AND status = 'open'",
            (case_id,),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def update_subject(case_id, subject):
    if not subject:
        return
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE document_cases SET subject = %s WHERE id = %s",
            (subject, case_id),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def close_case(case_id, subject, budget_amount, history_entry_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE document_cases
            SET status = 'closed', subject = %s, budget_amount = %s, history_entry_id = %s
            WHERE id = %s
            """,
            (subject, budget_amount, history_entry_id, case_id),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def delete_case(case_id, user_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM document_drafts WHERE case_id = %s AND user_id = %s",
            (case_id, user_id),
        )
        cur.execute(
            "DELETE FROM document_cases WHERE id = %s AND user_id = %s",
            (case_id, user_id),
        )
        deleted = cur.rowcount > 0
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return deleted


def backfill_legacy_drafts():
    """หา user_id ที่มีแถวใน document_drafts แต่ยังไม่มี case_id (ข้อมูลเก่าก่อนมีระบบ
    เก็บงานเป็นรายโครงการ) แล้วสร้าง 1 case ให้ต่อคนเพื่อผูกแถวเดิมเข้ากับ case นั้น"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT d.user_id FROM document_drafts d "
            "WHERE d.case_id IS NULL AND d.slot = 'main'"
        )
        user_ids = [row[0] for row in cur.fetchall()]

        for user_id in user_ids:
            cur.execute("SELECT name FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            user_name = row[0] if row else ''

            cur.execute(
                "INSERT INTO document_cases (user_id, user_name, category, status) "
                "VALUES (%s, %s, %s, 'in_progress')",
                (user_id, user_name, 'หมวดหมู่ที่1: จัดซื้อจัดจ้าง — ตัดหญ้าและฉีดยากำจัดวัชพืช'),
            )
            conn.commit()
            legacy_case_id = cur.lastrowid

            cur.execute(
                "UPDATE document_drafts SET case_id = %s "
                "WHERE user_id = %s AND case_id IS NULL AND slot = 'main'",
                (legacy_case_id, user_id),
            )
            conn.commit()

        # แถวเก่าที่เหลือ (slot อื่นที่ไม่ใช่ main เช่นของทดลองฟีเจอร์โคลนก่อนหน้านี้)
        # ไม่มีทางเข้าถึงได้จากโค้ดปัจจุบันแล้ว (ไม่ผูก case ให้ ปล่อยเป็นข้อมูลค้าง)
        cur.close()
    finally:
        conn.close()
