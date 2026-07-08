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
from document_drafts import get_draft, save_draft



app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pea2569-xK9mQ')

# โฟลเดอร์เก็บไฟล์รูปที่แนบผ่านฟอร์มแก้ไข (เช่น รูปพื้นที่ตัดหญ้า/ฉีดยาในหน้า 4)
# เก็บตัวไฟล์จริงไว้บนดิสก์ ส่วนพาธของรูป (string) จะถูกเก็บลง MySQL ผ่าน
# document_drafts.data_json เหมือนข้อมูลฟิลด์อื่น ๆ ของหน้านั้น
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf'}

# ข้อจำกัดชนิดไฟล์เฉพาะบางฟิลด์: mow_images รับเฉพาะรูปภาพ, spray_images รับเฉพาะเอกสาร
# (ฟิลด์อื่นที่ไม่ระบุในนี้ยังใช้ ALLOWED_IMAGE_EXT เดิม คือรูปภาพ + PDF)
FIELD_ALLOWED_EXT = {
    'mow_images': {'jpg', 'jpeg', 'png', 'gif', 'webp'},
    'spray_images': {'pdf', 'doc', 'docx', 'xls', 'xlsx'},
}
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # จำกัดไฟล์แนบไม่เกิน 8MB ต่อไฟล์

# ชื่อไฟล์ที่เซฟลงดิสก์จริงคือ "<uuid สุ่ม 32 ตัวอักษร>_<ชื่อไฟล์เดิม>" เพื่อกันชนกัน
# แต่ยังเก็บชื่อไฟล์เดิม (รวมภาษาไทย) ไว้ด้วย จะได้เอามาโชว์ในฟอร์ม/หน้าเอกสารได้
_UUID_PREFIX_RE = re.compile(r'^[0-9a-f]{32}_')


def sanitize_original_filename(name):
    """ตัดเฉพาะส่วนที่เป็น path/อักขระที่ใช้ในชื่อไฟล์ไม่ได้ออก ส่วนภาษาไทย/ยูนิโค้ด
    อื่น ๆ คงไว้เหมือนเดิม (ไม่ใช้ werkzeug.secure_filename เพราะมันตัดอักษรไทยทิ้งหมด)
    """
    name = os.path.basename(name)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)
    return name[-150:] or 'file'


def display_filename(url):
    """ดึงชื่อไฟล์เดิมที่ผู้ใช้อัปโหลดออกมาจาก URL ที่เก็บไว้ (ตัด uuid prefix ทิ้ง)"""
    name = urllib.parse.unquote(url.rsplit('/', 1)[-1])
    return _UUID_PREFIX_RE.sub('', name, count=1)


app.jinja_env.filters['display_filename'] = display_filename

# เก็บ session ฝั่งเซิร์ฟเวอร์แทน cookie ฝั่งไคลเอนต์ (เดิมติดตั้ง Flask-Session ไว้แล้ว
# แต่ไม่เคยเปิดใช้งานจริง) เพราะ form_store เก็บฉบับร่างของทั้งเอกสาร ขนาดใหญ่เกินกว่า
# ที่ cookie ปกติ (จำกัดราว 4KB ต่อโดเมนในเบราว์เซอร์) จะรับไหว พอเนื้อหายาว (เช่นหน้า 3/4)
# เบราว์เซอร์จะปฏิเสธ Set-Cookie แบบเงียบ ๆ ทำให้ข้อมูลที่บันทึกหายไปโดยไม่มี error ใด ๆ
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(__file__), 'flask_session')
app.config['SESSION_PERMANENT'] = False
Session(app)

app.register_blueprint(auth)

from datetime import datetime

THAI_MONTHS = [
    '', 'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม'
]
 
@app.context_processor
def inject_today_th():
    """ทำให้ทุก template เรียกใช้ตัวแปร today_th ได้เลย
    โดยไม่ต้อง pass มาจากทุก route -- จะได้วันที่ปัจจุบันแบบไทย
    เช่น '2 กรกฎาคม 2569' อัตโนมัติทุกครั้งที่เปิดหน้า
    """
    now = datetime.now()
    thai_year = now.year + 543
    today_th = f"{now.day} {THAI_MONTHS[now.month]} {thai_year}"
    return {'today_th': today_th}


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

# ===== ข้อมูลเริ่มต้นสำหรับหน้า 2: มอบหมายผู้จัดทำรายละเอียดคุณลักษณะเฉพาะ =====
# (เดิมหน้านี้ไม่มีชุดข้อมูลของตัวเอง เลยไปใช้ DEFAULT_DATA ของหน้า 1 แทนโดยไม่ได้ตั้งใจ
#  ข้อความด้านล่างนำมาจากเอกสารจริง 2_มอบหมายผู้จัดทำรายละเอียดคุณลักษณะเฉพาะ.docx)
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

# ===== ข้อมูลเริ่มต้นสำหรับหน้า 3: รายงานขอจัดจ้าง =====
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

# ===== ข้อมูลเริ่มต้นสำหรับหน้า 4: รายงานสรุปผลการพิจารณา + ใบสั่งจ้าง + เอกสารแนบ =====
DEFAULT_DATA_PAGE4 = {
    # --- ส่วนที่ 1: รายงานสรุปผลการพิจารณา, ตรวจรับ และอนุมัติจ่ายเงิน ---
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

    # --- ส่วนที่ 2: ใบสั่งจ้าง ---
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

    # --- ส่วนที่ 3: เงื่อนไขประกอบการสั่งจ้าง ---
    'delivery_doc_count': '',
    'delivery_days': '30',
    'delivery_due_date': '',
    'delivery_place': 'สถานีไฟฟ้าท่าทราย 1, สถานีไฟฟ้าท่าทราย 2 (ชั่วคราว), สถานีไฟฟ้าบางปลา และสถานีไฟฟ้าสมุทรสาคร 2',
    'warranty_period': '',
    'penalty_rate_daily': '0.20',
    'penalty_lump_sum': '–',
    'penalty_rate_lump': '0.10',
    'penalty_min_daily': '100',

    # --- ส่วนที่ 4: เอกสารแนบ 1 - รูปภาพแยกตามสถานี (ใส่ path รูปใน static/uploads/ เพิ่มเองได้ภายหลัง) ---
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

# ===== ข้อมูลเริ่มต้นสำหรับหน้า 5: รายงานผลการจ้าง / ขออนุมัติจ่ายเงินค่าจ้างทำความสะอาด =====
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

# ===== ข้อมูลเริ่มต้นสำหรับหน้า 6: ใบสำคัญจ่ายเงิน =====
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


# รายชื่อหน้าเอกสารที่แก้ไขแยกชุดกันได้
VALID_PAGES = ['main', 'spec_page1', 'spec_page2', 'report', 'spec_page3', 'spec_page4', 'spec_page5', 'spec_page6']

# ฟิลด์ระดับบนสุดที่ apply_common_data() เขียนทับทุกครั้งที่โหลดหน้า (ดึงจาก "ข้อมูลกลาง")
# แก้ผ่านฟอร์มแก้ไขเนื้อหาของหน้านั้นตรง ๆ ไม่มีผล เพราะโหลดครั้งถัดไปจะถูกเขียนทับกลับ
# ต้องไปแก้ที่หน้า "ข้อมูลกลาง" แทน — ใช้รายการนี้บอกฟอร์มแก้ไขไม่ให้เปิดแก้ไขฟิลด์เหล่านี้
# ตรงๆ (กันสับสนว่า "แก้ไปแล้วทำไมไม่เซฟ")
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


@app.errorhandler(413)
def handle_file_too_large(e):
    if request.path.startswith('/api/'):
        return jsonify({'status': 'error', 'message': 'ไฟล์มีขนาดใหญ่เกินไป (จำกัดไม่เกิน 8MB ต่อไฟล์)'}), 413
    return e


# กำหนดชุดข้อมูล default ของแต่ละหน้าไว้ในที่เดียว เพื่อให้ดูแลง่ายเมื่อมีหน้าเพิ่มในอนาคต
PAGE_DEFAULTS = {
    'spec_page2': DEFAULT_DATA_PAGE2,
    'spec_page3': DEFAULT_DATA_PAGE3,
    'spec_page4': DEFAULT_DATA_PAGE4,
    'spec_page5': DEFAULT_DATA_PAGE5,
    'spec_page6': DEFAULT_DATA_PAGE6,
}

def get_form_data(page_key, owner_id=None):
    """อ่านข้อมูลเอกสารของหน้าที่ระบุ สำหรับเจ้าของ (owner_id) ที่ระบุ
    ถ้าไม่ระบุ owner_id จะใช้ผู้ใช้ที่ login อยู่ปัจจุบัน (ดู/แก้ของตัวเอง)
    ถ้า owner_id เป็นคนอื่น จะอ่านฉบับร่างของคนนั้นแบบ read-only

    ฉบับร่างเก็บถาวรใน MySQL (document_drafts) แยกตามผู้ใช้แต่ละคน
    ถ้าเจ้าของยังไม่เคยบันทึกฉบับร่างของหน้านี้เลย จะคืนค่าเริ่มต้น (DEFAULT_DATA)
    ไปก่อน โดยยังไม่บันทึกลงฐานข้อมูลจนกว่าจะมีการแก้ไขจริงผ่าน /api/save-form
    """
    if owner_id is None:
        owner_id = session.get('user_id')

    default = PAGE_DEFAULTS.get(page_key, DEFAULT_DATA)
    draft = get_draft(owner_id, page_key)

    if draft is None:
        page_data = dict(default)
    else:
        # เติม key ใหม่ที่เพิ่งเพิ่มเข้า DEFAULT_DATA แต่ฉบับร่างเดิมยังไม่มี
        page_data = dict(default)
        page_data.update(draft)

    apply_common_data(page_key, page_data)
    return page_data


def resolve_viewer():
    """อ่าน ?user=<id> จาก query string เพื่อรองรับการดูงานของเพื่อนร่วมงานแบบ read-only
    คืนค่า (owner_id, readonly, owner_name) — ถ้าไม่ระบุ หรือระบุเป็นตัวเอง จะถือว่า
    กำลังดู/แก้ไขข้อมูลของตัวเอง (readonly=False)"""
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


@app.route('/select')
@login_required
def select_category():
    return render_template('select_category.html', username=session.get('name'))


@app.route('/select/mowing')
@login_required
def select_mowing():
    """หน้าการ์ดย่อย 5 ใบของหมวด 'จัดซื้อจัดจ้าง-ตัดหญ้า' + ปุ่มพิมพ์ทั้งชุด"""
    return render_template('select_group_mowing.html', username=session.get('name'))


@app.route('/colleagues')
@login_required
def colleagues():
    """รายชื่อเพื่อนร่วมงานทั้งหมด กดเข้าไปดูงาน (เอกสาร) ของคนนั้นแบบ read-only ได้"""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id, name, position FROM users WHERE id != %s ORDER BY name",
            (session['user_id'],),
        )
        people = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    return render_template('colleagues.html', people=people, username=session.get('name'))


@app.route('/spec-print-all')
@login_required
def spec_print_all():
    """รวมข้อมูลเอกสารหน้า 1-5 มาไว้หน้าเดียว สำหรับพิมพ์เป็น PDF ไฟล์เดียว"""
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


@app.route('/edit-form')
@login_required
def edit_form():
    page_key = request.args.get('page', 'main')
    if page_key not in VALID_PAGES:
        page_key = 'main'

    data = get_form_data(page_key)
    locked_fields = COMMON_DATA_LOCKED_FIELDS.get(page_key, [])
    return render_template('edit_form.html', data=data, username=session.get('name'), page_key=page_key,
                            locked_fields=locked_fields)


@app.route('/api/save-form', methods=['POST'])
@login_required
def save_form():
    payload = request.json or {}
    page_key = payload.pop('_page_key', 'main')
    if page_key not in VALID_PAGES:
        page_key = 'main'

    # บันทึกลงฉบับร่างของ "ผู้ใช้ที่ login อยู่" เท่านั้นเสมอ (ไม่อ่านจาก payload/query
    # string เด็ดขาด) เพื่อไม่ให้ใครแก้ไขทับฉบับร่างของคนอื่นได้
    save_draft(session['user_id'], page_key, payload)

    return jsonify({'status': 'success', 'message': 'บันทึกแล้ว', 'page_key': page_key})


@app.route('/api/upload-image', methods=['POST'])
@login_required
def upload_image():
    """รับไฟล์รูปแนบ (เช่น รูปพื้นที่ตัดหญ้า/ฉีดยาในหน้า 4) บันทึกลงดิสก์ที่
    static/uploads/ ด้วยชื่อสุ่มกันชนกัน แล้วคืน URL กลับไปให้ฝั่งฟอร์มเก็บพาธนี้
    ไว้ในข้อมูลของหน้า (ไปบันทึกจริงตอนกด "บันทึก" ผ่าน /api/save-form ตามปกติ)
    """
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
    """หน้าแก้ไข 'ข้อมูลกลาง' ที่เดียว — บันทึกแล้วหน้า 1,2,3,5,6 ที่ใช้
    ข้อมูลชุดนี้ (ลายเซ็นผู้เสนอ/จาก-ถึง, ชื่อแผนก+เบอร์โทร, คณะกรรมการ)
    จะเปลี่ยนตามทันทีในครั้งถัดไปที่เปิดหน้านั้น เพราะดึงจาก MySQL สดทุกครั้ง
    """
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