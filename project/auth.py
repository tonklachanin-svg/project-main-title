from flask import Blueprint, app, render_template, request, session, redirect, url_for
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db

auth = Blueprint("auth", __name__)

@auth.route('/')
@auth.route('/login')
def login():
    session.clear()
    return render_template('login.html')


@auth.route('/auth/login', methods=['POST'])
def auth_login():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, password, position, supervisor_id FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()

    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['username'] = username
        session['name'] = user['name']
        session['position'] = user.get('position') or ''

        # ดึงชื่อ + ตำแหน่งของหัวหน้า/รองหัวหน้า (ชผ.) มาเก็บไว้ใน session ด้วย
        supervisor_name = ''
        supervisor_position = ''
        if user.get('supervisor_id'):
            cursor.execute(
                "SELECT name, position FROM users WHERE id = %s",
                (user['supervisor_id'],)
            )
            supervisor = cursor.fetchone()
            if supervisor:
                supervisor_name = supervisor['name']
                supervisor_position = supervisor.get('position') or ''

        session['supervisor_name'] = supervisor_name
        session['supervisor_position'] = supervisor_position

        cursor.close()
        conn.close()
        return redirect(url_for('select_category'))

    cursor.close()
    conn.close()
    return render_template('login.html', error='ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'), 401


def get_supervisors():
    """ดึงรายชื่อผู้ที่มีตำแหน่งหัวหน้า/รองหัวหน้า สำหรับใส่ใน dropdown ตอนสมัครสมาชิก"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, name, position FROM users WHERE position IN ('หัวหน้า', 'รองหัวหน้า') ORDER BY position, name"
    )
    supervisors = cursor.fetchall()
    cursor.close()
    conn.close()
    return supervisors


@auth.route('/register')
def register_page():
    return render_template('register.html', supervisors=get_supervisors())


@auth.route('/auth/register', methods=['POST'])
def auth_register():
    name          = request.form.get('name', '').strip()
    username      = request.form.get('username', '').strip()
    password      = request.form.get('password', '')
    confirm       = request.form.get('confirm_password', '')
    phone         = request.form.get('phone', '').strip()
    email         = request.form.get('email', '').strip()
    position      = request.form.get('position', '').strip()
    supervisor_id = request.form.get('supervisor_id') or None

    if not name or not username or not password:
        return render_template('register.html', error='กรุณากรอกข้อมูลให้ครบ', supervisors=get_supervisors()), 400

    if password != confirm:
        return render_template('register.html', error='รหัสผ่านไม่ตรงกัน', supervisors=get_supervisors()), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (name, username, password, phone, email, position, supervisor_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (name, username, generate_password_hash(password), phone, email, position or None, supervisor_id)
        )
        conn.commit()
    except mysql.connector.IntegrityError:
        cursor.close()
        conn.close()
        return render_template('register.html', error='ชื่อผู้ใช้นี้มีอยู่แล้ว', supervisors=get_supervisors()), 400
    cursor.close()
    conn.close()

    return redirect(url_for("auth.login"))


@auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for("auth.login"))