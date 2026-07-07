"""
document_drafts.py
---------------------------------------------------------
เก็บ "ฉบับร่าง" ของเนื้อหาเอกสารแต่ละหน้า (subject, section, ตาราง ฯลฯ)
แยกตามผู้ใช้แต่ละคนอย่างถาวรใน MySQL ตาราง document_drafts
(เดิมเก็บไว้ใน session ของเบราว์เซอร์เท่านั้น พอ logout/ปิดเบราว์เซอร์
หรือ session หมดอายุ ข้อมูลที่แก้ไว้จะหายไป)

แต่ละคนมีฉบับร่างของตัวเอง 1 ชุดต่อหน้า (user_id, page_key) แต่คนอื่น
เปิดดู (read-only) ฉบับร่างของเพื่อนร่วมงานได้ผ่าน get_draft(user_id, page_key)
โดยไม่ต้องเป็นเจ้าของ — การบันทึกทับ (save_draft) ต้องระบุ user_id ของ
เจ้าของเท่านั้น (ฝั่ง route เป็นคนบังคับว่าต้องเป็นผู้ใช้ที่ login อยู่)
---------------------------------------------------------
"""

import json
from database import get_db


def get_draft(user_id, page_key):
    """อ่านฉบับร่างของผู้ใช้คนหนึ่งสำหรับหน้าที่ระบุ คืนค่า None ถ้ายังไม่เคยบันทึก"""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT data_json FROM document_drafts WHERE user_id = %s AND page_key = %s",
            (user_id, page_key),
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


def save_draft(user_id, page_key, data):
    """บันทึก (เพิ่ม/อัปเดต) ฉบับร่างของผู้ใช้คนหนึ่งสำหรับหน้าที่ระบุ"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO document_drafts (user_id, page_key, data_json)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE data_json = VALUES(data_json)
            """,
            (user_id, page_key, json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
