"""
common_data.py
---------------------------------------------------------
จุดเก็บ "ข้อมูลกลาง" ที่ใช้ร่วมกันในหลายหน้าเอกสาร (สเปคหญ้า/ฉีดยา)
เก็บใน MySQL ตาราง common_data (แถวเดียว id=1) แทนการพิมพ์ซ้ำ
ในแต่ละหน้าเหมือนที่ผ่านมา

วิธีใช้:
    from common_data import get_common_data, save_common_data
    common = get_common_data()          # อ่านค่าปัจจุบัน
    save_common_data({...})             # บันทึกค่าใหม่ทั้งหมด

ก่อนใช้งานครั้งแรก ต้องรัน sql/add_common_data_table.sql กับฐานข้อมูล pea_db ก่อน
---------------------------------------------------------
"""

import json
from database import get_db

# ใช้เป็นค่าตั้งต้น เผื่อกรณีตารางยังไม่มีข้อมูล (กันไม่ให้หน้าเว็บพังถ้ายังไม่ได้รัน SQL)
DEFAULT_COMMON_DATA = {
    "signature_from": "(นายภานุพงค์  เจนสุริยะกุล)",
    "position_from": "หผ.จฟ.1 กปบ.(ก3)",
    "org_from": "ผจฟ.1",
    "org_to": "กปบ.(ก3)",
    "dept_name": "แผนกจัดการงานสถานีไฟฟ้า 1",
    "dept_tel": "10520-21",
    "committee": [
        {"name": "นายสุรชาติ  อมรวงศ์ไพบูลย์", "job_pos": "พชง.7 ผจฟ.1 กปบ.(ก3)", "role": "ประธานกรรมการ"},
        {"name": "นายนามชัย  นุชประเสริฐ", "job_pos": "พชง.6 ผจฟ.1 กปบ.(ก3)", "role": "กรรมการ"},
        {"name": "นายนฤเทพ  จันทร์วงค์", "job_pos": "พชง.5 ผจฟ.1 กปบ.(ก3)", "role": "กรรมการ"},
    ],
}


def get_common_data():
    """อ่านข้อมูลกลางปัจจุบันจาก MySQL คืนค่าเป็น dict เสมอ"""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT signature_from, position_from, org_from, org_to,
                   dept_name, dept_tel, committee_json
            FROM common_data
            WHERE id = 1
            """
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    if not row:
        # ยังไม่เคยรัน SQL migration หรือแถวถูกลบไป ใช้ค่าตั้งต้นแทนไปก่อน
        return dict(DEFAULT_COMMON_DATA)

    try:
        committee = json.loads(row["committee_json"]) if row["committee_json"] else []
    except (TypeError, ValueError):
        committee = []

    return {
        "signature_from": row["signature_from"] or "",
        "position_from": row["position_from"] or "",
        "org_from": row["org_from"] or "",
        "org_to": row["org_to"] or "",
        "dept_name": row["dept_name"] or "",
        "dept_tel": row["dept_tel"] or "",
        "committee": committee or DEFAULT_COMMON_DATA["committee"],
    }


def save_common_data(data):
    """บันทึกข้อมูลกลางใหม่ทั้งชุดลง MySQL (แถว id=1 แถวเดียว)

    data ต้องมี key: signature_from, position_from, org_from, org_to,
    dept_name, dept_tel, committee (list ของ {name, job_pos, role})
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO common_data
                (id, signature_from, position_from, org_from, org_to,
                 dept_name, dept_tel, committee_json)
            VALUES (1, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                signature_from = VALUES(signature_from),
                position_from  = VALUES(position_from),
                org_from       = VALUES(org_from),
                org_to         = VALUES(org_to),
                dept_name      = VALUES(dept_name),
                dept_tel       = VALUES(dept_tel),
                committee_json = VALUES(committee_json)
            """,
            (
                data.get("signature_from", ""),
                data.get("position_from", ""),
                data.get("org_from", ""),
                data.get("org_to", ""),
                data.get("dept_name", ""),
                data.get("dept_tel", ""),
                json.dumps(data.get("committee", []), ensure_ascii=False),
            ),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def apply_common_data(page_key, data):
   
    common = get_common_data()

    # หน้าที่ใช้ ลายเซ็นผู้เสนอ + จาก/ถึง
    if page_key in ("main", "spec_page1", "spec_page2", "spec_page3"):
        data["signature_from"] = common["signature_from"]
        data["from"] = common["org_from"]
        data["to"] = common["org_to"]

    # ตำแหน่งผู้เสนอ: จากเอกสารจริงพบว่าหน้า 3 ใช้คำที่สั้นกว่าหน้า 1/2
    # (หน้า 1/2 = "หผ.จฟ.1 กปบ.(ก3)", หน้า 3 = "หผ.จฟ.1" เฉยๆ)
    # จึงไม่รวม position_from ของหน้า 3 เข้าไปในข้อมูลกลางชุดนี้ ปล่อยให้เป็นค่าเฉพาะของหน้า 3 เอง
    if page_key in ("main", "spec_page1", "spec_page2"):
        data["position_from"] = common["position_from"]

    # หน้าที่ใช้ ชื่อแผนก + เบอร์โทร (ชื่อ field ต่างกันไปตามแต่ละ template เดิม)
    if page_key in ("main", "spec_page1", "spec_page2"):
        data["dept_name"] = common["dept_name"]
        data["dept_tel"] = common["dept_tel"]
    if page_key == "spec_page3":
        data["dept_name"] = common["dept_name"]
        data["dept_phone"] = common["dept_tel"]
    if page_key in ("spec_page5", "spec_page6"):
        data["dept"] = common["dept_name"]
        data["tel"] = common["dept_tel"]

    # หน้าที่ใช้ คณะกรรมการตรวจรับ 3 คน (รูปแบบ field ต่างกันไปตาม template เดิม)
    if page_key == "spec_page3":
        data["committee"] = [
            {"name": m["name"], "pos": m["job_pos"], "role": m["role"]}
            for m in common["committee"]
        ]
    if page_key == "spec_page5":
        data["committee"] = [
            {
                "name": m["name"],
                "position": m["role"] if m["role"].endswith("ฯ") else m["role"] + "ฯ",
            }
            for m in common["committee"]
        ]

    return data