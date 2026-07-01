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
    cursor.execute("SELECT id, name, password FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['username'] = username
        session['name'] = user['name']
        return redirect(url_for('select_category'))

    return render_template('login.html', error='ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'), 401


@auth.route('/register')
def register_page():
    return render_template('register.html')


@auth.route('/auth/register', methods=['POST'])
def auth_register():
    name     = request.form.get('name', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    confirm  = request.form.get('confirm_password', '')
    phone    = request.form.get('phone', '').strip()
    email    = request.form.get('email', '').strip()

    if not name or not username or not password:
        return render_template('register.html', error='กรุณากรอกข้อมูลให้ครบ'), 400

    if password != confirm:
        return render_template('register.html', error='รหัสผ่านไม่ตรงกัน'), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (name, username, password, phone, email) VALUES (%s, %s, %s, %s, %s)",
            (name, username, generate_password_hash(password), phone, email)
        )
        conn.commit()
    except mysql.connector.IntegrityError:
        cursor.close()
        conn.close()
        return render_template('register.html', error='ชื่อผู้ใช้นี้มีอยู่แล้ว'), 400
    cursor.close()
    conn.close()

    return redirect(url_for("auth.login"))


@auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
