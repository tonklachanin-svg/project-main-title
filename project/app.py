from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import os
import re
import uuid
import urllib.parse
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from flask_session import Session
from database import get_db
from auth import auth
from common_data import get_common_data, save_common_data, apply_common_data
from document_drafts import get_draft, save_draft, ensure_case_column
from document_history import ensure_table as ensure_history_table, log_submission, search_history, get_history_entry, delete_entry as delete_history_entry, seconds_since_last_submission
import document_cases


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pea2569-xK9mQ')

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf'}

FIELD_ALLOWED_EXT = {
    'mow_images': {'jpg', 'jpeg', 'png', 'gif', 'webp'},
    'spray_images': {'pdf', 'doc', 'docx', 'xls', 'xlsx'},
}
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024

_UUID_PREFIX_RE = re.compile(r'^[0-9a-f]{32}_')


def sanitize_original_filename(name):
    name = os.path.basename(name)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)
    return name[-150:] or 'file'


def display_filename(url):
    name = urllib.parse.unquote(url.rsplit('/', 1)[-1])
    return _UUID_PREFIX_RE.sub('', name, count=1)


app.jinja_env.filters['display_filename'] = display_filename


def first_name(full_name):
    if not full_name:
        return full_name
    parts = full_name.split()
    return parts[0] if parts else full_name


app.jinja_env.filters['first_name'] = first_name

FIELD_LABELS = {
    'from': 'จาก',
    'to': 'ถึง',
    'number': 'เลขที่',
    'date': 'วันที่',
    'subject': 'เรื่อง',
    'receiver': 'เรียน',
    'section1': 'ข้อมูล (ข้อ 1)',
    'section2': 'ข้อพิจารณา (ข้อ 2)',
    'closing': 'ข้อความปิดท้าย',
    'signature_from': 'ลายเซ็นผู้เสนอ',
    'position_from': 'ตำแหน่งผู้เสนอ',
    'approve': 'ข้อความอนุมัติ',
    'approve_text': 'ข้อความอนุมัติ',
    'signature_approve': 'ลายเซ็นผู้อนุมัติ',
    'position_approve': 'ตำแหน่งผู้อนุมัติ',
    'intro': 'คำนำ',
    'reason': 'เหตุผลและความจำเป็น',
    'detail_intro': 'รายละเอียดพัสดุ',
    'mow_table': 'ตารางพื้นที่ตัดหญ้า',
    'mow_total': 'ยอดรวมตัดหญ้า',
    'spray_table': 'ตารางพื้นที่ฉีดยา',
    'spray_total': 'ยอดรวมฉีดยา',
    'last_hired': 'จ้างครั้งล่าสุด',
    'price_basis': 'ที่มาราคากลาง',
    'budget_detail': 'รายละเอียดงบประมาณ',
    'deadline': 'กำหนดส่งมอบ',
    'method': 'วิธีจัดซื้อจัดจ้าง',
    'officer_name': 'ชื่อเจ้าหน้าที่',
    'officer_pos': 'ตำแหน่งเจ้าหน้าที่',
    'committee': 'คณะกรรมการ',
    'committee_order': 'คำสั่งแต่งตั้งคณะกรรมการ',
    'dept_phone': 'เบอร์โทรแผนก',
    'qualification_intro': 'คุณสมบัติผู้เสนอราคา',
    'condition_offer': 'เงื่อนไขการเสนอราคา',
    'delivery_days': 'จำนวนวันส่งมอบ',
    'delivery_place': 'สถานที่ส่งมอบ',
    'delivery_doc_count': 'จำนวนฉบับเอกสารส่งมอบ',
    'delivery_due_date': 'วันครบกำหนดส่งมอบ',
    'warranty_period': 'ระยะเวลารับประกัน',
    'penalty_clause': 'เงื่อนไขค่าปรับ',
    'rejection_clause': 'เงื่อนไขการไม่รับมอบ',
    'penalty_rate_daily': 'อัตราค่าปรับรายวัน (%)',
    'penalty_lump_sum': 'ค่าปรับเหมาจ่ายต่อวัน',
    'penalty_rate_lump': 'อัตราค่าปรับเหมาจ่าย (%)',
    'penalty_min_daily': 'ค่าปรับขั้นต่ำต่อวัน',
    'report_from': 'จาก',
    'report_to': 'ถึง',
    'report_number': 'เลขที่',
    'report_date': 'วันที่',
    'report_subject': 'เรื่อง',
    'report_receiver': 'เรียน',
    'report_intro': 'คำนำรายงาน',
    'order_table': 'ตารางสรุปผลการพิจารณา',
    'order_total': 'ยอดรวม',
    'report_consideration': 'ผลการพิจารณา',
    'report_budget_source': 'แหล่งงบประมาณ',
    'report_closing': 'ข้อความปิดท้าย',
    'vendor_name': 'ชื่อผู้ขาย/ผู้รับจ้าง',
    'vendor_address': 'ที่อยู่ผู้ขาย/ผู้รับจ้าง',
    'vendor_phone': 'เบอร์โทรผู้ขาย/ผู้รับจ้าง',
    'bank_account_no': 'เลขบัญชีธนาคาร',
    'bank_account_name': 'ชื่อบัญชีธนาคาร',
    'bank_name': 'ชื่อธนาคาร',
    'po_intro': 'คำนำใบสั่งจ้าง',
    'po_table': 'ตารางใบสั่งจ้าง',
    'po_total': 'ยอดรวมใบสั่งจ้าง',
    'po_note': 'หมายเหตุใบสั่งจ้าง',
    'approver_name': 'ชื่อผู้อนุมัติ',
    'approver_pos': 'ตำแหน่งผู้อนุมัติ',
    'station_areas': 'พื้นที่แต่ละสถานี',
    'mow_images': 'รูปพื้นที่ตัดหญ้า',
    'spray_images': 'เอกสาร/รูปพื้นที่ฉีดยา',
    'name': 'ชื่อ',
    'month': 'เดือน',
    'year': 'ปี',
    'period': 'งวดที่',
    'amount': 'จำนวนเงิน',
    'amount_text': 'จำนวนเงิน (ตัวอักษร)',
    'vat_note': 'หมายเหตุภาษี',
    'dept': 'แผนก',
    'tel': 'เบอร์โทร',
    'receipt_ref': 'เลขที่ กฟฟ.',
    'date_day': 'วันที่ (วัน)',
    'date_month': 'วันที่ (เดือน)',
    'date_year': 'วันที่ (ปี)',
    'payee': 'ผู้เบิก',
    'payee_address': 'ที่อยู่ผู้เบิก',
    'branch': 'กฟฟ.',
    'budget_type': 'ประเภทงบ',
    'job_number': 'หมายเลขงาน',
    'account_code': 'รหัสบัญชี',
    'cashbook_page': 'สมุดเงินสดหน้า',
    'debit_account': 'เดบิทบัญชี',
    'posted_date': 'ลงบัญชีเมื่อ',
    'voucher_items': 'รายการเบิกจ่าย',
    'description': 'รายละเอียด',
    'satang': 'สตางค์',
    'subtotal': 'ยอดรวมย่อย',
    'subtotal_satang': 'สตางค์ยอดรวมย่อย',
    'vat': 'ภาษีมูลค่าเพิ่ม',
    'vat_satang': 'สตางค์ภาษี',
    'total_text': 'ยอดรวม (ตัวอักษร)',
    'total_amount': 'ยอดรวมทั้งสิ้น',
    'receipt_no': 'ใบเสร็จเลขที่',
    'receipt_date': 'วันที่ใบเสร็จ',
    'check_no': 'เช็คเลขที่',
    'check_date': 'วันที่เช็ค',
    'total': 'พื้นที่รวม',
    'area': 'พื้นที่ดำเนินการ',
    'price': 'ราคา',
    'item': 'รายการ',
    'offer_price': 'ราคาที่เสนอ',
    'agreed_price': 'ราคาที่ตกลง',
    'qty': 'จำนวน',
    'unit': 'หน่วย',
    'unit_price': 'ราคาต่อหน่วย',
    'pos': 'ตำแหน่ง',
    'role': 'บทบาท',
    'position': 'ตำแหน่ง',
    'text': 'ตัวอักษร',
    'grand_total': 'ยอดรวมสุทธิ',
    'dept_name': 'ชื่อแผนก',
    'dept_tel': 'เบอร์โทรแผนก',
    'org_from': 'จาก',
    'org_to': 'ถึง',
}
app.jinja_env.globals['field_labels'] = FIELD_LABELS

app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(__file__), 'flask_session')
app.config['SESSION_PERMANENT'] = False
Session(app)

app.register_blueprint(auth)


def ensure_admin_support():
    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE users ADD COLUMN is_admin TINYINT(1) NOT NULL DEFAULT 0")
            conn.commit()
        except mysql.connector.Error as e:
            if e.errno != 1060:
                raise

        cur.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        (admin_count,) = cur.fetchone()
        if admin_count == 0:
            cur.execute(
                "UPDATE users SET is_admin = 1 "
                "WHERE id = (SELECT id FROM (SELECT MIN(id) AS id FROM users) AS t)"
            )
            conn.commit()
        cur.close()
    finally:
        conn.close()


ensure_history_table()
ensure_admin_support()
ensure_case_column()
document_cases.ensure_table()
document_cases.backfill_legacy_drafts()

from datetime import datetime

THAI_MONTHS = [
    '', 'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
    'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'
]
 
@app.context_processor
def inject_today_th():
    now = datetime.now()
    thai_year = now.year + 543
    today_th = f"{now.day} {THAI_MONTHS[now.month]} {thai_year}"
    return {'today_th': today_th}


def thai_date(dt):
    if not dt:
        return '-'
    return f"{dt.day} {THAI_MONTHS[dt.month]} {dt.year + 543}"


def thai_datetime(dt):
    if not dt:
        return '-'
    return f"{dt.day} {THAI_MONTHS[dt.month]} {dt.year + 543} {dt.strftime('%H:%M')} น."


app.jinja_env.filters['thai_date'] = thai_date
app.jinja_env.filters['thai_datetime'] = thai_datetime


DEFAULT_DATA = {
    'from': 'ผจฟ.1',
    'to': 'กปบ.(ก3)',
    'number': 'ก.3 กปบ.(จฟ.1) /2569',
    'date': '',
    'subject': 'ขอความเห็นชอบดำเนินการจัดจ้างตัดหญ้าและฉีดยากำจัดวัชพืชสถานีไฟฟ้าในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1',
    'receiver': 'อก.ปบ.(ก3) ผ่าน ชก.ปบ.(ก3)',
    'section1': 'หน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 (สถานีไฟฟ้าท่าทราย 1) สังกัด ผจฟ.1 กปบ.(ก3) ตรวจสอบพบว่าบริเวณพื้นที่ภายในบริเวณสถานีไฟฟ้า มีต้นหญ้าและวัชพืชขึ้นเป็นจำนวนมาก',
    'section2': 'ผจฟ.1 กปบ.(ก3) ได้พิจารณาแล้วเพื่อป้องกันการเกิดกระแสไฟฟ้าขัดข้อง จากสัตว์เลื้อยคลาน ต่างๆ จึงเห็นควรดำเนินการจัดจ้างตัดหญ้าและฉีดยากำจัดวัชพืช โดยใช้ราคากลางอ้างอิงตามพระราชบัญญัติการจัดซื้อจัดจ้าง และบริหารพัสดุภาครัฐ พ.ศ. 2560 จึงขออนุมัติความเห็นชอบดำเนินการจัดซื้อ/จ้างดังกล่าว โดยให้เบิกจ่ายจากงบทำการ ประจำปี 2569 ค่าจ้างบำรุงรักษาสวน รหัสบัญชี 53034030 ศูนย์ต้นทุน I301031040',
    'closing': 'จึงเรียนมาเพื่อโปรดพิจารณาหากเห็นชอบโปรดลงนามให้ต่อไป',
    'signature_from': '(นายภานุพงค์  เจนสุริยะกุล)',
    'position_from': 'หผ.จฟ.1 กปบ.(ก3)',
    'approve': 'เห็นชอบดำเนินการต่อไป',
    'signature_approve': '(นายเลอพงศ์ แก่นจันทร์)',
    'position_approve': 'อก.ปบ.(ก3)'
}

DEFAULT_DATA_PAGE2 = {
    'from': 'ผจฟ.1',
    'to': 'กปบ.(ก3)',
    'number': 'ก.3 กปบ.(จฟ.1)',
    'date': '',
    'subject': 'มอบหมายผู้จัดทำรายละเอียดคุณลักษณะเฉพาะของพัสดุ และกำหนดราคากลาง สำหรับงานขอจัดจ้างตัดหญ้าและฉีดยากำจัดวัชพืชสถานีไฟฟ้าในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 ด้วยวิธีเฉพาะเจาะจง',
    'receiver': 'อก.ปบ.(ก3) ผ่าน ชก.ปบ.(ก3)',
    'section1': 'ด้วย ผจฟ.1 กปบ.(ก3) มีความประสงค์จะจัดจ้างตัดหญ้าและฉีดยากำจัดวัชพืชสถานีไฟฟ้าในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 เพื่อให้เป็นไปตามพระราชบัญญัติการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ.2560 และระเบียบกระทรวงการคลังว่าด้วยการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ. 2560',
    'section2': 'ผจฟ.1 กปบ.(ก3) ขอมอบหมายให้ นายพีรวิชญ์  ศรีนันทวงศ์ ตำแหน่ง ชผ.จฟ.1 กปบ.(ก3) เป็นผู้จัดทำรายละเอียดคุณลักษณะเฉพาะของพัสดุและกำหนดราคากลาง โดยมีอำนาจและหน้าที่จัดทำรายละเอียดคุณลักษณะเฉพาะของพัสดุที่จะซื้อ/จ้าง กำหนดหลักเกณฑ์การพิจารณาคัดเลือกข้อเสนอ และ กำหนดราคากลางของพัสดุที่จะซื้อ/จ้าง โดยให้ผู้ได้รับมอบหมายดำเนินการให้แล้วเสร็จภายใน 10 วันทำการ นับถัดจากวันที่ได้รับมอบหมาย',
    'closing': 'จึงเรียนมาเพื่อโปรดพิจารณา',
    'signature_from': '(นายภานุพงค์  เจนสุริยะกุล)',
    'position_from': 'หผ.จฟ.1 กปบ.(ก3)',
    'approve': 'เห็นชอบดำเนินการต่อไป',
    'signature_approve': '(นายเลอพงศ์ แก่นจันทร์)',
    'position_approve': 'อก.ปบ.(ก3)'
}

DEFAULT_DATA_PAGE3 = {
    'from': 'ผจฟ.1',
    'to': 'กปบ.(ก3)',
    'number': 'ก.3 กปบ.(จฟ.1)',
    'date': '',
    'subject': 'รายงานขอจัดจ้างตัดหญ้าและฉีดยากำจัดวัชพืชสถานีไฟฟ้าในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1',
    'receiver': 'อก.ปบ.(ก3) ผ่าน ชก.ปบ.(ก3)',

    'intro': 'ด้วย หน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 (สถานีไฟฟ้าท่าทราย 1) ผจฟ.1 กปบ.(ก3) มีความประสงค์จะจัดจ้างตัดหญ้าและฉีดยากำจัดวัชพืชสถานีไฟฟ้าในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 โดยวิธีเฉพาะเจาะจงตามพระราชบัญญัติการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ.2560 ตามมาตรา 56 (2)(ข) และตามระเบียบกระทรวงการคลังว่าด้วยการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ.2560 ซึ่งมีรายละเอียดดังต่อไปนี้',

    'reason': 'เนื่องจากหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 (สถานีไฟฟ้าท่าทราย 1) มีสถานีไฟฟ้าที่อยู่ในความรับผิดชอบทั้งสิ้นจำนวน 5 สถานีฯ ได้แก่ สถานีไฟฟ้าท่าทราย 1, สถานีไฟฟ้าสมุทรสาคร 2, สถานีไฟฟ้าบางปลา, สถานีไฟฟ้าท่าทราย 2 (ชั่วคราว) และสถานีไฟฟ้าสมุทรสาคร 16 (ชั่วคราว) ปัจจุบันพื้นที่ภายในบริเวณสถานีไฟฟ้ามีต้นหญ้าและวัชพืชขึ้นเป็นจำนวนมาก ซึ่งอาจส่งผลกระทบต่อความมั่นคงในการจ่ายกระแสไฟฟ้า เพื่อป้องกันการเกิดกระแสไฟฟ้าขัดข้องจากสัตว์เลื้อยคลานต่างๆ จึงมีความจำเป็นที่ต้องจัดจ้างตัดหญ้าและฉีดยากำจัดวัชพืชให้มีความเป็นระเบียบเรียบร้อยของสถานีไฟฟ้า',

    'detail_intro': 'จัดจ้างตัดหญ้าและฉีดยากำจัดวัชพืชสถานีไฟฟ้าในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 (สถานีไฟฟ้าท่าทราย 1) จำนวน 4 สถานีฯ (เอกสารแนบ 1) ตามรายละเอียดดังนี้',

    'mow_table': [
        {'name': 'ท่าทราย 1',     'total': '6 ไร่ 290 ตร.ว.', 'area': '1 ไร่',           'price': '600'},
        {'name': 'สมุทรสาคร 2',   'total': '3 ไร่ 363 ตร.ว.', 'area': '2 ไร่ 215 ตร.ว.', 'price': '1,522.50'},
        {'name': 'บางปลา',        'total': '2 ไร่ 40 ตร.ว.',  'area': '1 ไร่',           'price': '600'},
        {'name': 'ท่าทราย 2 (ช)', 'total': '1 ไร่ 112 ตร.ว.', 'area': '50 ตร.ว.',        'price': '75'},
    ],
    'mow_total': {'total': '14 ไร่ 5 ตร.ว.', 'area': '4 ไร่ 265 ตร.ว.', 'price': '2,797.50'},

    'spray_table': [
        {'name': 'ท่าทราย 1',     'total': '6 ไร่ 290 ตร.ว.', 'area': '257 ตร.ว.',       'price': '205.60'},
        {'name': 'สมุทรสาคร 2',   'total': '3 ไร่ 363 ตร.ว.', 'area': '2 ไร่ 215 ตร.ว.', 'price': '812'},
        {'name': 'บางปลา',        'total': '2 ไร่ 40 ตร.ว.',  'area': '-',               'price': '-'},
        {'name': 'ท่าทราย 2 (ช)', 'total': '1 ไร่ 112 ตร.ว.', 'area': '1 ไร่ 88 ตร.ว.',  'price': '390.40'},
    ],
    'spray_total': {'total': '14 ไร่ 5 ตร.ว.', 'area': '4 ไร่ 160 ตร.ว.', 'price': '1,408'},

    'last_hired': 'จัดจ้างครั้งสุดท้ายเมื่อเดือน สิงหาคม 2568',

    'price_basis': 'เป็นราคากลางค่าจ้างตัดหญ้าและฉีดยากำจัดวัชพืชภายในสถานีไฟฟ้า อ้างอิงจากราคาที่เคยจ้างครั้งหลังสุดภายในระยะเวลาไม่เกิน 2 ปีงบประมาณ ตามหนังสือเลขที่ ก.3กปบ.(จฟ.1) xxx/2569 ลงวันที่ xx xxxx รายงานสรุปผลการพิจารณา,ตรวจรับ และอนุมัติจ่ายเงิน (เอกสารแนบ 2)',

    'budget_detail': 'จัดจ้างตัดหญ้าและฉีดยากำจัดวัชพืชสถานีไฟฟ้าในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 (สถานีไฟฟ้าท่าทราย 1) จำนวน 4 สถานีฯ ในวงเงิน 4,205.50 บาท ภาษีมูลค่าเพิ่ม 7% จำนวนเงิน 295.79 บาท รวมเป็นเงินทั้งสิ้น 4,501.29 บาท (สี่พันห้าร้อยหนึ่งบาทยี่สิบเก้าสตางค์) โดยให้เบิกจ่ายจากค่าจ้างบำรุงรักษาสวน รหัสบัญชี 53034030 ศูนย์ต้นทุน I301031040',

    'deadline': 'การจัดจ้าง กำหนดวันส่งมอบพัสดุภายใน 30 วัน นับแต่วันถัดจากวันลงนามในสัญญา/ใบสั่งจ้าง',

    'method': 'พิจารณาเห็นสมควรดำเนินการจัดซื้อจัดจ้างโดยวิธีเฉพาะเจาะจง ตามพระราชบัญญัติการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ.2560 ตามมาตรา 56 (2)(ข) เนื่องจากการจัดซื้อจัดจ้างครั้งนี้มีราคาไม่เกิน 500,000.00 บาท และดำเนินการตามระเบียบกระทรวงการคลังว่าด้วยการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ.2560 ข้อ 79 (3)',

    'officer_name': 'นายกฤติณภัทร เสียงใหญ่',
    'officer_pos': 'พชง.6 ผจฟ.1 กปบ.(ก3)',

    'committee': [
        {'name': 'นายสุรชาติ  อมรวงศ์ไพบูลย์', 'pos': 'พชง.7 ผจฟ.1 กปบ.(ก3)', 'role': 'ประธานกรรมการ'},
        {'name': 'นายนามชัย  นุชประเสริฐ',     'pos': 'พชง.6 ผจฟ.1 กปบ.(ก3)', 'role': 'กรรมการ'},
        {'name': 'นายนฤเทพ  จันทร์วงค์',       'pos': 'พชง.5 ผจฟ.1 กปบ.(ก3)', 'role': 'กรรมการ'},
    ],
    'committee_order': 'ทั้งนี้เป็นอำนาจของ อก.ปบ.(ก3) ตามคำสั่งที่ พ.(ม) 37/2566 สั่ง ณ วันที่ 20 ตุลาคม 2566 ข้อ 5.3 วิธีเฉพาะเจาะจง (ค)',

    'closing': 'จึงเรียนมาเพื่อโปรดพิจารณา หากเห็นชอบขอได้โปรดอนุมัติให้ดำเนินการจัดจ้างตัดหญ้าและฉีดยากำจัดวัชพืชสถานีไฟฟ้าในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 โดยวิธีเฉพาะเจาะจงตามมาตรา 56 (2)(ข) ตามรายละเอียดในรายงานขอจัดจ้างดังกล่าว',

    'approve_text': 'อนุมัติและลงนามแล้ว',
    'signature_approve': '(นายเลอพงศ์ แก่นจันทร์)',
    'position_approve': 'อก.ปบ.(ก3) ปฏิบัติงานแทน ผวก.',
    'signature_from': '(นายภานุพงค์ เจนสุริยะกุล)',
    'position_from': 'หผ.จฟ.1',

    'dept_phone': '(33) 10520-21',

    'qualification_intro': '1.1 ผู้เสนอราคา ต้องเป็นผู้มีอาชีพขาย/รับจ้าง ดังกล่าว\n1.2 ผู้เสนอราคา ต้องไม่เป็นผู้ที่ถูกระบุชื่อไว้ในบัญชีรายชื่อผู้ทิ้งงานของทางราชการและได้แจ้งเวียนชื่อแล้ว หรือไม่เป็นผู้ที่ได้รับผลของการสั่งให้นิติบุคคล หรือบุคคลอื่นเป็นผู้ทิ้งงานตามระเบียบของทางราชการ\n1.3 ผู้เสนอราคาต้องไม่เป็นผู้ได้รับเอกสิทธิ์หรือความคุ้มกัน ซึ่งอาจปฏิเสธไม่ยอมขึ้นศาลไทย เว้นแต่รัฐบาลของผู้เสนอราคาได้มีคำสั่งให้สละสิทธิ์และความคุ้มกันเช่นว่านั้น\n1.4 ผู้เสนอราคาต้องไม่เป็นผู้ที่ถูกประเมินสิทธิผู้เสนอราคาในสถานะที่ห้ามเข้าเสนอราคาและห้ามทำสัญญาตามที่ กวพ. กำหนด\n1.5 บุคคลหรือนิติบุคคลที่จะเข้าเป็นคู่สัญญาต้องไม่อยู่ในฐานะเป็นผู้ไม่แสดงบัญชีรายรับรายจ่าย หรือแสดงบัญชีรายรับรายจ่ายไม่ถูกต้องครบถ้วนในสาระสำคัญ\n1.6 บุคคลหรือนิติบุคคลที่จะเข้าเป็นคู่สัญญากับหน่วยงานภาครัฐซึ่งได้ดำเนินการจัดซื้อจัดจ้างด้วยระบบอิเล็กทรอนิกส์ (e-Government Procurement : e-GP) ต้องลงทะเบียนในระบบอิเล็กทรอนิกส์ ของกรมบัญชีกลาง ที่เว็บไซต์ศูนย์ข้อมูลจัดซื้อจัดจ้างภาครัฐ\n1.7 คู่สัญญาต้องรับและจ่ายเงินผ่านบัญชีธนาคาร เว้นแต่การจ่ายเงินแต่ละครั้งซึ่งมีมูลค่าเกินสามหมื่นบาทคู่สัญญาอาจจ่ายเป็นเงินสดก็ได้\n1.8 ให้กำหนดคุณสมบัติอื่น ๆ',

    'condition_offer': 'ปฏิบัติตามเงื่อนไขที่ระบุไว้ในเอกสารซื้อ/จ้าง\nราคาที่เสนอจะต้องเป็นราคาที่รวมภาษีมูลค่าเพิ่ม และภาษีอื่น ๆ (ถ้ามี)รวมค่าใช้จ่ายทั้งปวงไว้ด้วยแล้ว\nห้ามผู้เสนอราคาถอนการเสนอราคา',

    'delivery_days': '30',
    'delivery_place': 'สถานีไฟฟ้าท่าทราย 1, สถานีไฟฟ้าสมุทรสาคร 2, สถานีไฟฟ้าบางปลา, สถานีไฟฟ้าท่าทราย 2 (ชั่วคราว)',
    'warranty_period': '',

    'penalty_clause': 'การไฟฟ้าส่วนภูมิภาค สงวนสิทธิ์ค่าปรับกรณีส่งมอบพัสดุเกินกำหนดเวลา โดยคิดค่าปรับเป็นรายวันในอัตราร้อยละ 0.20 ของราคาพัสดุ/งานจ้างที่ยังไม่ได้รับมอบโดยรวมภาษีมูลค่าเพิ่ม เว้นแต่การจ้างซึ่งต้องการผลสำเร็จของงานทั้งหมดพร้อมกัน ค่าปรับเป็นเงินรวมภาษีมูลค่าเพิ่มวันละ – บาท (ในอัตราร้อยละ 0.10 ของราคางานจ้างรวมภาษีมูลค่าเพิ่ม แต่ต้องไม่ต่ำกว่าวันละ 100.- บาท)',
    'rejection_clause': 'การไฟฟ้าส่วนภูมิภาค สงวนสิทธิ์ที่จะไม่รับมอบพัสดุ/งานนั้น ถ้าปรากฏว่า พัสดุ/งานนั้นมีลักษณะไม่ตรงตามรายการที่ระบุไว้ในใบสั่งซื้อ/สั่งจ้าง กรณีผู้ขาย/ผู้รับจ้าง ต้องดำเนินการแก้ไขให้ถูกต้องตามใบสั่งซื้อ/สั่งจ้างทุกประการ ด้วยค่าใช้จ่ายของผู้ขาย/ผู้รับจ้างเอง และระยะเวลาที่เสียไปเพราะเหตุดังกล่าว ผู้ขาย/ผู้รับจ้างจะนำมาอ้างเป็นเหตุขอขยายเวลาทำการตามใบสั่งซื้อ/สั่งจ้าง หรือของด หรือลดค่าปรับไม่ได้',
}

DEFAULT_DATA_PAGE4 = {
    'report_from': 'ผจฟ.1',
    'report_to': 'กปบ.(ก3)',
    'report_number': 'ก.3 กปบ.(จฟ.1)',
    'report_date': '',
    'report_subject': 'รายงานสรุปผลการพิจารณา, ตรวจรับ และอนุมัติจ่ายเงิน',
    'report_receiver': 'อก.ปบ.(ก3) ผ่าน ชก.ปบ.(ก3)',
    'report_intro': 'ตามที่ หน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 (สถานีไฟฟ้าท่าทราย 1) ผจฟ.1 กปบ.(ก3) ดำเนินการจัดจ้างตัดหญ้า และฉีดยากำจัดวัชพืชภายในสถานีไฟฟ้าจำนวน 4 แห่ง โดยวิธีเฉพาะเจาะจง ขอรายงานผลการพิจารณาการจัดซื้อ/จ้าง ดังนี้',

    'order_table': [
        {
            'item': 'จัดจ้างตัดหญ้า สฟฟ.ท่าทราย 1, สฟฟ.สค. 2, สฟฟ.บางปลา และ สฟฟ.ท่าทราย 2 ชั่วคราว พื้นที่ 4 ไร่ 265 ตร.วา',
            'offer_price': '2,568',
            'vat': '-',
            'agreed_price': '2,568',
        },
        {
            'item': 'ฉีดยากำจัดวัชพืช สฟฟ.ท่าทราย 1, สฟฟ.สค. 2, สฟฟ.บางปลา และ สฟฟ.ท่าทราย 2 ชั่วคราว พื้นที่ 4 ไร่ 190 ตร.วา',
            'offer_price': '1,232',
            'vat': '-',
            'agreed_price': '1,232',
        },
    ],
    'order_total': {'amount': '3,800'},

    'report_consideration': 'พิจารณาแล้วเห็นสมควรจัดจ้าง นายสมพร คำกลั่น เป็นจำนวนเงิน 3,800 บาท (สามพันแปดร้อยบาทถ้วน) ราคาไม่รวมภาษีมูลค่าเพิ่ม',
    'report_budget_source': 'โดยเบิกจากงบทำการค่าจ้างบำรุงรักษาสวน รหัสบัญชี 53034030 ศูนย์ต้นทุน I301031040',
    'report_closing': 'จึงเรียนมาเพื่อโปรดพิจารณา หากเห็นชอบ ขอได้โปรดอนุมัติให้สั่งซื้อ/จ้าง จากผู้เสนอราคาดังกล่าว พร้อมทั้งแจ้งคณะกรรมการตรวจรับ ดำเนินการต่อไป',

    'vendor_name': 'นายสมพร คำกลั่น',
    'vendor_address': 'เลขที่ 136 หมู่ที่ 6 ตำบลยกกระบัตร อำเภอบ้านแพ้ว จังหวัดสมุทรสาคร 74120',
    'vendor_phone': '',
    'bank_account_no': '',
    'bank_account_name': '',
    'bank_name': '',

    'po_intro': 'ตามที่ นายสมพร คำกลั่น ได้เสนอราคาไว้ต่อ กองปฏิบัติการ ฝ่ายปฏิบัติการและบำรุงรักษา การไฟฟ้าส่วนภูมิภาค เขต 3 (ภาคกลาง) จ.นครปฐม ตามใบเสนอราคา ลงวันที่ 30 ตุลาคม 2568 ซึ่งได้รับราคา และตกลงจ้างตัดหญ้าและฉีดยากำจัดวัชพืชภายในสถานีไฟฟ้า รายละเอียดดังต่อไปนี้',

    'po_table': [
        {
            'item': 'ค่าจ้างตัดหญ้าและฉีดยากำจัดวัชพืชภายในสถานีไฟฟ้าจำนวน 4 แห่ง (รายละเอียดตามรายงานขออนุมัติจัดจ้าง)',
            'qty': '1',
            'unit': 'งาน',
            'unit_price': '3,800',
            'amount': '3,800',
        },
    ],
    'po_total': {
        'text': 'สามพันแปดร้อยบาทถ้วน',
        'subtotal': '3,800',
        'vat': '-',
        'grand_total': '3,800',
    },

    'po_note': 'ตามเงื่อนไขการสั่งซื้อ/สั่งจ้าง ตามเอกสารแนบ',

    'approver_name': 'นายพัทธนันท์ พชิราสุวรรณ์ชล',
    'approver_pos': 'อก.ปบ.(ก3)',

    'delivery_doc_count': '',
    'delivery_days': '30',
    'delivery_due_date': '',
    'delivery_place': 'สถานีไฟฟ้าท่าทราย 1, สถานีไฟฟ้าท่าทราย 2 (ชั่วคราว), สถานีไฟฟ้าบางปลา และสถานีไฟฟ้าสมุทรสาคร 2',
    'warranty_period': '',
    'penalty_rate_daily': '0.20',
    'penalty_lump_sum': '–',
    'penalty_rate_lump': '0.10',
    'penalty_min_daily': '100',

    'station_areas': [
        {
            'name': 'สถานีไฟฟ้าท่าทราย 1',
            'mow_images': [],
            'spray_images': [],
        },
        {
            'name': 'สถานีไฟฟ้าสมุทรสาคร 2',
            'mow_images': [],
            'spray_images': [],
        },
        {
            'name': 'สถานีไฟฟ้าบางปลา',
            'mow_images': [],
            'spray_images': [],
        },
        {
            'name': 'สถานีไฟฟ้าท่าทราย 2',
            'mow_images': [],
            'spray_images': [],
        },
    ],
}

DEFAULT_DATA_PAGE5 = {
    'from': 'คณะกรรมการตรวจรับพัสดุ',
    'to': 'กปบ.(ก3)',
    'number': 'ก.3 กปบ.(จฟ.1)',
    'date': '',
    'subject': 'รายงานผลการจ้างทำความสะอาดสถานีไฟฟ้าภายในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 (สถานีไฟฟ้าท่าทราย 1)',
    'month': 'ธันวาคม',
    'year': '2568',
    'period': '12',
    'receiver': 'อก.ปบ.(ก3) ผ่าน รก.ปบ.(ก3)',

    'section1': 'ตามหนังสือเลขที่ ก.3 กปบ.(จฟ.1) xxx/xxxx ลงวันที่ xxxxx อก.ปบ.(ก3)อนุมัติจ้างทำความสะอาดสถานีไฟฟ้าภายในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 (สถานีไฟฟ้าท่าทราย 1) ประจำปี 2569 (เอกสารแนบ)',
    'section2': 'คณะกรรมการตรวจรับงานจ้างได้ทำการตรวจรับงานที่ผู้รับจ้างดำเนินการทำความสะอาดสถานีไฟฟ้าภายในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 (สถานีไฟฟ้าท่าทราย 1) ประจำเดือน ธันวาคม 2568 เป็นไปด้วยความเรียบร้อย คณะกรรมการฯ ได้พิจารณาแล้วเห็นควรอนุมัติจ่ายเงินจ้างทำความสะอาดสถานีไฟฟ้าภายในหน่วยปฏิบัติงานสถานีไฟฟ้าที่ 1 (สถานีไฟฟ้าท่าทราย 1) ประจำเดือน ธันวาคม 2568 เป็นจำนวนเงิน 3,600 บาท (สามพันหกร้อยบาทถ้วน) ไม่รวมภาษีมูลค่าเพิ่ม',
    'closing': 'จึงเรียนมาเพื่อโปรดพิจารณาและอนุมัติให้ต่อไป',

    'committee': [
        {'name': 'นายนามชัย  นุชประเสริฐ', 'position': 'ประธานกรรมการฯ'},
        {'name': 'นายกฤติณภัทร  เสียงใหญ่', 'position': 'กรรมการฯ'},
        {'name': 'นายนฤเทพ  จันทร์วงค์', 'position': 'กรรมการฯ'},
    ],

    'amount': '3,600',
    'amount_text': 'สามพันหกร้อยบาทถ้วน',
    'vat_note': 'ไม่รวมภาษีมูลค่าเพิ่ม',

    'signature_approve': '(นายเลอพงศ์  แก่นจันทร์)',
    'position_approve': 'อก.ปบ.(ก3)',

    'dept': 'แผนกจัดการงานสถานีไฟฟ้า 1',
    'tel': '10520 - 21',
}

DEFAULT_DATA_PAGE6 = {
    'receipt_ref': '',
    'number': '',
    'date_day': '',
    'date_month': 'เมษายน',
    'date_year': '2569',
    'payee': 'นายอาทิตย์  จันทร์น้ำเงิน  (495969)',
    'payee_address': '',
    'branch': 'กฟก.3',
    'budget_type': 'งบทำการ',
    'job_number': 'I301031040',
    'account_code': '53051040',
    'cashbook_page': '',
    'debit_account': '',
    'posted_date': '',

    'voucher_items': [
        {'description': 'ค่าจ้างเปลี่ยนกระจกแตกร้าวห้องคอนโทรล สถานีไฟฟ้าดอนเจดีย์', 'amount': '3500', 'satang': '-'},
    ],
    'subtotal': '3500',
    'subtotal_satang': '-',
    'vat': '',
    'vat_satang': '-',
    'total_text': 'สามพันห้าร้อยบาทถ้วน',
    'total_amount': '3500',

    'receipt_no': '',
    'receipt_date': '',
    'check_no': '',
    'check_date': '',

    'dept': 'แผนกจัดการงานสถานีไฟฟ้า 1',
    'tel': '10520-21',
}


VALID_PAGES = ['main', 'spec_page1', 'spec_page2', 'report', 'spec_page3', 'spec_page4', 'spec_page5', 'spec_page6']

CATEGORY_MOWING = 'หมวดหมู่ที่1: จัดซื้อจัดจ้าง — ตัดหญ้าและฉีดยากำจัดวัชพืช'
PAGE_TITLES = {
    'main': 'หนังสือขอความเห็นชอบดำเนินการตัดหญ้า',
    'report': 'รายงานสรุปผลการพิจารณา',
    'spec_page1': '1.หนังสือขอความเห็นชอบดำเนินการตัดหญ้า',
    'spec_page2': '2.มอบหมายผู้จัดทำรายละเอียดคุณลักษณะเฉพาะ',
    'spec_page3': '3.รายงานขอจัดจ้างตัดหญ้าและฉีดยา ททร.1(1)แผนก',
    'spec_page4': '4.รายงาน ใบสั่งจ้างตัดหญ้า หน่วย พค 68 แบบแผน',
    'spec_page5': '5.จ่ายรายงวด ขออนุมัติจ่ายเงินค่าจ้างทำความสะอาด',
    'spec_page6': '6.ใบสำคัญจ่ายเงิน',
}
PAGE_CATEGORY = {page: CATEGORY_MOWING for page in VALID_PAGES}

COMMON_DATA_LOCKED_FIELDS = {
    'main': ['signature_from', 'from', 'to', 'position_from', 'dept_name', 'dept_tel'],
    'spec_page1': ['signature_from', 'from', 'to', 'position_from', 'dept_name', 'dept_tel'],
    'spec_page2': ['signature_from', 'from', 'to', 'position_from', 'dept_name', 'dept_tel'],
    'spec_page3': ['signature_from', 'from', 'to', 'dept_name', 'dept_phone', 'committee'],
    'spec_page5': ['dept', 'tel', 'committee'],
    'spec_page6': ['dept', 'tel'],
}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'status': 'error', 'message': 'เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่'}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({'status': 'error', 'message': 'เฉพาะแอดมินเท่านั้นที่ทำรายการนี้ได้'}), 403
        return f(*args, **kwargs)
    return decorated


@app.errorhandler(413)
def handle_file_too_large(e):
    if request.path.startswith('/api/'):
        return jsonify({'status': 'error', 'message': 'ไฟล์มีขนาดใหญ่เกินไป (จำกัดไม่เกิน 8MB ต่อไฟล์)'}), 413
    return e


PAGE_DEFAULTS = {
    'spec_page2': DEFAULT_DATA_PAGE2,
    'spec_page3': DEFAULT_DATA_PAGE3,
    'spec_page4': DEFAULT_DATA_PAGE4,
    'spec_page5': DEFAULT_DATA_PAGE5,
    'spec_page6': DEFAULT_DATA_PAGE6,
}

def get_active_case_id():
    case_id = session.get('case_id')
    if case_id:
        return case_id
    case_id = document_cases.create_case(session['user_id'], session.get('name') or '', CATEGORY_MOWING)
    session['case_id'] = case_id
    return case_id


def latest_case_id_for_user(user_id):
    cases = document_cases.list_cases(user_id)
    return cases[0]['id'] if cases else None


def get_form_data(page_key, owner_id=None):
    if owner_id is None:
        case_id = get_active_case_id()
    else:
        case_id = latest_case_id_for_user(owner_id)

    default = PAGE_DEFAULTS.get(page_key, DEFAULT_DATA)
    draft = get_draft(case_id, page_key)

    if draft is None:
        page_data = dict(default)
    else:
        page_data = dict(default)
        page_data.update(draft)

    apply_common_data(page_key, page_data)
    return page_data


def resolve_viewer():
    my_id = session.get('user_id')
    requested = request.args.get('user', type=int)
    if not requested or requested == my_id:
        return my_id, False, None

    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT name FROM users WHERE id = %s", (requested,))
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    if not row:
        return my_id, False, None

    return requested, True, row['name']


@app.route('/folder')
@login_required
def case_folder():
    keyword = request.args.get('keyword', '').strip()
    status = request.args.get('status', '').strip()
    cases = document_cases.list_cases(session['user_id'], keyword=keyword or None, status=status or None)
    return render_template(
        'folder.html', username=session.get('name'), cases=cases,
        filters={'keyword': keyword, 'status': status},
    )


@app.route('/api/case/mark-in-progress', methods=['POST'])
@login_required
def api_mark_in_progress():
    case_id = get_active_case_id()
    document_cases.mark_in_progress(case_id)
    return jsonify({'status': 'success'})


@app.route('/folder/new')
@login_required
def case_new():
    case_id = document_cases.create_case(session['user_id'], session.get('name') or '', CATEGORY_MOWING)
    session['case_id'] = case_id
    return redirect(url_for('select_category'))


@app.route('/folder/open/<int:case_id>')
@login_required
def case_open(case_id):
    case = document_cases.get_case(case_id, session['user_id'])
    if not case:
        return redirect(url_for('case_folder'))

    if case['status'] == 'closed' and case['history_entry_id']:
        return redirect(url_for('history_detail', entry_id=case['history_entry_id']))

    session['case_id'] = case_id
    return redirect('/spec-page-1')


@app.route('/api/folder/<int:case_id>/delete', methods=['POST'])
@login_required
def case_delete(case_id):
    deleted = document_cases.delete_case(case_id, session['user_id'])
    if not deleted:
        return jsonify({'status': 'error', 'message': 'ไม่พบงานนี้ หรือไม่ใช่งานของคุณ'}), 404

    if session.get('case_id') == case_id:
        session.pop('case_id', None)

    return jsonify({'status': 'success', 'message': 'ลบงานแล้ว'})


@app.route('/select')
@login_required
def select_category():
    return render_template('select_category.html', username=session.get('name'))


@app.route('/select/mowing')
@login_required
def select_mowing():
    return render_template('select_group_mowing.html', username=session.get('name'))


@app.route('/history')
@login_required
def history():
    category = request.args.get('category', '').strip()
    keyword = request.args.get('keyword', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    entries = search_history(
        category=category or None,
        keyword=keyword or None,
        date_from=date_from or None,
        date_to=date_to or None,
    )

    return render_template(
        'history.html',
        username=session.get('name'),
        entries=entries,
        categories=[CATEGORY_MOWING],
        filters={'category': category, 'keyword': keyword, 'date_from': date_from, 'date_to': date_to},
        is_admin=session.get('is_admin', False),
    )


@app.route('/api/history/<int:entry_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_history(entry_id):
    deleted = delete_history_entry(entry_id)
    if not deleted:
        return jsonify({'status': 'error', 'message': 'ไม่พบประวัตินี้ อาจถูกลบไปแล้ว'}), 404
    return jsonify({'status': 'success', 'message': 'ลบประวัติแล้ว'})


@app.route('/history/<int:entry_id>')
@login_required
def history_detail(entry_id):
    entry = get_history_entry(entry_id)
    if not entry:
        return redirect(url_for('history'))

    if entry['page_key'] == 'mowing_all' and entry['data']:
        d = entry['data']
        return render_template(
            'spec_print_all.html',
            data1=d.get('spec_page1', {}),
            data2=d.get('spec_page2', {}),
            data3=d.get('spec_page3', {}),
            data4=d.get('spec_page4', {}),
            data5=d.get('spec_page5', {}),
            username=session.get('name'),
            history_id=entry_id,
        )

    return render_template('history_detail.html', username=session.get('name'), entry=entry)


@app.route('/spec-print-all')
@login_required
def spec_print_all():
    owner_id, readonly, owner_name = resolve_viewer()
    data1 = get_form_data('spec_page1', owner_id)
    data2 = get_form_data('spec_page2', owner_id)
    data3 = get_form_data('spec_page3', owner_id)
    data4 = get_form_data('spec_page4', owner_id)
    data5 = get_form_data('spec_page5', owner_id)
    return render_template(
        'spec_print_all.html',
        data1=data1,
        data2=data2,
        data3=data3,
        data4=data4,
        data5=data5,
        username=session.get('name'),
    )

@app.route("/select/mowing2")
@login_required
def select_mowing2():
    return render_template(
        "select_mowing2.html",
        username=session["username"]
    )
@app.route("/select/mowing3")
@login_required
def select_mowing3():
    return render_template(
        "select_mowing3.html",
        username=session["username"]
    )

@app.route("/select/mowing4")
@login_required
def select_mowing4():
    return render_template(
        "select_mowing4.html",
        username=session["username"]
    )

@app.route("/select/mowing5")
@login_required
def select_mowing5():
    return render_template(
        "select_mowing5.html",
        username=session["username"]
    )


@app.route('/main')
@login_required
def main():
    data = get_form_data('main')
    return render_template('spec_page1.html', data=data, username=session.get('name'), page_key='main')


@app.route('/report')
@login_required
def report():
    data = get_form_data('report')
    return render_template('report.html', data=data, username=session.get('name'), page_key='report')


@app.route('/spec-page-1')
@app.route('/spec_page1')
@login_required
def spec_page_1():
    owner_id, readonly, owner_name = resolve_viewer()
    data = get_form_data('spec_page1', owner_id)
    return render_template('spec_page1.html', data=data, username=session.get('name'), current_page=1,
                            page_key='spec_page1', readonly=readonly, owner_name=owner_name, owner_id=owner_id)


@app.route('/spec-page-2')
@login_required
def spec_page_2():
    owner_id, readonly, owner_name = resolve_viewer()
    data = get_form_data('spec_page2', owner_id)
    return render_template('spec_page2.html', data=data, username=session.get('name'), current_page=2,
                            page_key='spec_page2', readonly=readonly, owner_name=owner_name, owner_id=owner_id)


@app.route('/spec-page-3')
@login_required
def spec_page_3():
    owner_id, readonly, owner_name = resolve_viewer()
    data = get_form_data('spec_page3', owner_id)
    return render_template('spec_page3.html', data=data, username=session.get('name'), current_page=3,
                            page_key='spec_page3', readonly=readonly, owner_name=owner_name, owner_id=owner_id)


@app.route('/spec-page-4')
@login_required
def spec_page_4():
    owner_id, readonly, owner_name = resolve_viewer()
    data = get_form_data('spec_page4', owner_id)
    return render_template('spec_page4.html', data=data, username=session.get('name'), current_page=4,
                            page_key='spec_page4', readonly=readonly, owner_name=owner_name, owner_id=owner_id)


@app.route('/spec-page-5')
@login_required
def spec_page_5():
    owner_id, readonly, owner_name = resolve_viewer()
    data = get_form_data('spec_page5', owner_id)
    return render_template('spec_page5.html', data=data, username=session.get('name'), current_page=5,
                            page_key='spec_page5', readonly=readonly, owner_name=owner_name, owner_id=owner_id)


@app.route('/spec-page-6')
@login_required
def spec_page_6():
    owner_id, readonly, owner_name = resolve_viewer()
    data = get_form_data('spec_page6', owner_id)
    return render_template('spec_page6.html', data=data, username=session.get('name'), current_page=6,
                            page_key='spec_page6', readonly=readonly, owner_name=owner_name, owner_id=owner_id)


EDIT_PAGE_NUMBERS = {
    'spec_page1': 1, 'spec_page2': 2, 'spec_page3': 3,
    'spec_page4': 4, 'spec_page5': 5, 'spec_page6': 6,
}


@app.route('/edit-form')
@login_required
def edit_form():
    page_key = request.args.get('page', 'main')
    if page_key not in VALID_PAGES:
        page_key = 'main'

    data = get_form_data(page_key)
    locked_fields = COMMON_DATA_LOCKED_FIELDS.get(page_key, [])
    return render_template('edit_form.html', data=data, username=session.get('name'), page_key=page_key,
                            locked_fields=locked_fields, is_editing=True,
                            current_page=EDIT_PAGE_NUMBERS.get(page_key))


@app.route('/api/save-form', methods=['POST'])
@login_required
def save_form():
    payload = request.json or {}
    page_key = payload.pop('_page_key', 'main')
    if page_key not in VALID_PAGES:
        page_key = 'main'

    case_id = get_active_case_id()
    save_draft(session['user_id'], case_id, page_key, payload)
    document_cases.mark_in_progress(case_id)

    subject = payload.get('subject') or payload.get('report_subject')
    if subject:
        document_cases.update_subject(case_id, subject)

    return jsonify({'status': 'success', 'message': 'บันทึกแล้ว', 'page_key': page_key})


SUBMIT_COOLDOWN_SECONDS = 10


@app.route('/api/submit-history', methods=['POST'])
@login_required
def submit_history():
    # กันกด "ส่งข้อมูล" ซ้ำในเวลาไล่เลี่ยกัน (เน็ตช้าแล้ว fetch ยิงซ้อน หรือเปิดสองแท็บ
    # กดพร้อมกัน) — ถ้าเพิ่ง log ไปเมื่อไม่กี่วินาทีก่อน ให้ตอบ success เดิมกลับไปเฉย ๆ
    # โดยไม่สร้างแถวประวัติซ้ำ
    since = seconds_since_last_submission(session['user_id'], 'mowing_all')
    if since is not None and since < SUBMIT_COOLDOWN_SECONDS:
        return jsonify({'status': 'success', 'message': 'ส่งข้อมูลสำเร็จ'})

    case_id = get_active_case_id()
    pages_data = {page_key: get_form_data(page_key) for page_key in VALID_PAGES if page_key in PAGE_TITLES}

    subject = (
        pages_data.get('spec_page1', {}).get('subject')
        or pages_data.get('spec_page4', {}).get('report_subject')
        or ''
    )
    budget_amount = pages_data.get('spec_page6', {}).get('total_amount') or ''

    history_id = log_submission(
        user_id=session['user_id'],
        user_name=session.get('name') or '',
        category=CATEGORY_MOWING,
        page_key='mowing_all',
        page_title='จัดซื้อจัดจ้าง — ตัดหญ้าและฉีดยากำจัดวัชพืช (ทั้งชุด 6 หน้า)',
        subject=subject,
        data=pages_data,
    )

    document_cases.close_case(case_id, subject, budget_amount, history_id)
    session.pop('case_id', None)

    return jsonify({'status': 'success', 'message': 'ส่งข้อมูลสำเร็จ'})


@app.route('/api/clone-draft', methods=['POST'])
@login_required
def clone_draft():
    source_user_id = request.json.get('source_user_id') if request.json else None
    if not source_user_id or source_user_id == session['user_id']:
        return jsonify({'status': 'error', 'message': 'ไม่พบเจ้าของงานที่จะโคลน'}), 400

    source_case_id = latest_case_id_for_user(source_user_id)
    if not source_case_id:
        return jsonify({'status': 'error', 'message': 'เพื่อนร่วมงานคนนี้ยังไม่เคยบันทึกงานเลย ไม่มีอะไรให้โคลน'}), 400

    case_id = get_active_case_id()
    cloned_pages = []
    for page_key in VALID_PAGES:
        draft = get_draft(source_case_id, page_key)
        if draft is not None:
            save_draft(session['user_id'], case_id, page_key, draft)
            cloned_pages.append(page_key)

    if not cloned_pages:
        return jsonify({'status': 'error', 'message': 'เพื่อนร่วมงานคนนี้ยังไม่เคยบันทึกงานเลย ไม่มีอะไรให้โคลน'}), 400

    document_cases.mark_in_progress(case_id)
    return jsonify({'status': 'success', 'message': f'โคลนงานสำเร็จ ({len(cloned_pages)} หน้า)'})


@app.route('/api/clone-history/<int:entry_id>', methods=['POST'])
@login_required
def clone_history(entry_id):
    entry = get_history_entry(entry_id)
    if not entry or not entry.get('data'):
        return jsonify({'status': 'error', 'message': 'ไม่พบข้อมูลประวัตินี้'}), 404

    case_id = get_active_case_id()
    cloned_pages = []
    for page_key, page_data in entry['data'].items():
        if page_key in VALID_PAGES and isinstance(page_data, dict):
            save_draft(session['user_id'], case_id, page_key, page_data)
            cloned_pages.append(page_key)

    if not cloned_pages:
        return jsonify({'status': 'error', 'message': 'ไม่มีข้อมูลหน้าเอกสารให้โคลนในประวัตินี้'}), 400

    document_cases.mark_in_progress(case_id)
    return jsonify({'status': 'success', 'message': f'โคลนงานสำเร็จ ({len(cloned_pages)} หน้า)'})


@app.route('/api/upload-image', methods=['POST'])
@login_required
def upload_image():
    file = request.files.get('image')
    if not file or file.filename == '':
        return jsonify({'status': 'error', 'message': 'ไม่พบไฟล์รูปภาพ'}), 400

    field = request.form.get('field', '')
    allowed_ext = FIELD_ALLOWED_EXT.get(field, ALLOWED_IMAGE_EXT)

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_ext:
        return jsonify({'status': 'error', 'message': f'รองรับเฉพาะไฟล์นามสกุล {", ".join(sorted(allowed_ext))}'}), 400

    original_name = sanitize_original_filename(file.filename)
    filename = f"{uuid.uuid4().hex}_{original_name}"
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    url = url_for('static', filename=f'uploads/{filename}')

    return jsonify({'status': 'success', 'url': url})


@app.route('/edit-common-data', methods=['GET', 'POST'])
@login_required
def edit_common_data():
    if request.method == 'POST':
        committee = []
        for i in range(3):
            committee.append({
                'name': request.form.get(f'committee_name_{i}', '').strip(),
                'job_pos': request.form.get(f'committee_job_pos_{i}', '').strip(),
                'role': request.form.get(f'committee_role_{i}', '').strip(),
            })

        new_data = {
            'signature_from': request.form.get('signature_from', '').strip(),
            'position_from': request.form.get('position_from', '').strip(),
            'org_from': request.form.get('org_from', '').strip(),
            'org_to': request.form.get('org_to', '').strip(),
            'dept_name': request.form.get('dept_name', '').strip(),
            'dept_tel': request.form.get('dept_tel', '').strip(),
            'committee': committee,
        }
        save_common_data(new_data)
        return redirect(url_for('spec_page_1', saved=1))

    common = get_common_data()
    return render_template(
        'edit_common_data.html',
        common=common,
        username=session.get('name'),
        saved=request.args.get('saved'),
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)