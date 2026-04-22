import cv2
from flask import Flask, render_template, request, Response, jsonify, session, redirect, url_for, make_response
import time
import datetime
import uuid
import hmac
import hashlib
import requests
import os
import sqlite3
import threading
from werkzeug.utils import secure_filename
import csv
from io import StringIO

# ==========================================
# 1. 시스템 설정 및 초기화
# ==========================================
app = Flask(__name__)
app.secret_key = os.urandom(24)

# [수정] 업로드 폴더 및 DB 경로
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DB_PATH = os.path.join(os.path.dirname(__file__), 'database/ms_database.db')

# [수정] 다중 카메라 지원을 위한 글로벌 변수 및 락(Lock)
# 이유: 여러 YOLO 노드가 동시에 접속할 때 데이터 충돌을 방지합니다.
frames = {
    # "cam1": {"data": None, "ts": 0},
    # "cam2": {"data": None, "ts": 0}, ...
}
frame_lock = threading.Lock()
VALID_CAM_IDS = {"cam1", "cam2", "tb01", "tb02"}

# 알림 상태
alert_state = {"active": False, "zone": None}

# ==========================================
# 2. YOLO 영상 수신 및 스트리밍 엔진 (핵심 최적화)
# ==========================================

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    cam_id = request.form.get('cam_id')

    if file is None or cam_id is None:
        return jsonify({"status": "error"}), 400

    frame_data = file.read()
    
    # [핵심] 수신 시점에 타임스탬프 기록
    with frame_lock:
        frames[cam_id] = {
            "data": frame_data,
            "ts": time.time()  # 데이터가 들어온 시각 기록
        }

    return jsonify({"status": "ok", "cam_id": cam_id})

def generate_frames(cam_id):
    """지능형 프레임 스킵이 적용된 스트리밍 엔진"""
    last_sent_ts = 0  # 브라우저에 마지막으로 보낸 프레임의 시간
    
    while True:
        with frame_lock:
            frame_obj = frames.get(cam_id)

        # 1. 데이터가 아예 없거나, 이미 보낸 데이터와 같은 시점의 데이터면 대기
        if frame_obj is None or frame_obj["ts"] <= last_sent_ts:
            time.sleep(0.01)  # 아주 짧게 쉬면서 최신 데이터 대기
            continue

        # 2. 최신 데이터가 확인되면 송출
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_obj["data"] + b'\r\n')
        
        # 3. 보낸 시점 업데이트 및 강제 휴식 (브라우저 보호)
        last_sent_ts = frame_obj["ts"]
        
        # [파라미터 설정] 
        # YOLO가 10FPS로 보내면 0.08~0.09 정도로 설정하는 것이 가장 부드럽습니다.
        time.sleep(0.08)

@app.route('/video/<cam_id>')
def video_feed(cam_id):
    """HTML <img> 태그와 연결되는 스트리밍 라우트"""
    if cam_id not in VALID_CAM_IDS:
        return "Invalid cam_id", 400
    return Response(generate_frames(cam_id), mimetype='multipart/x-mixed-replace; boundary=frame')

# ==========================================
# 3. 화면 렌더링 라우트 (GET)
# ==========================================

@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/main')
def main_page():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('main.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/database')
def database_page():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM items')
        items = cursor.fetchall()
        conn.close()
        return render_template('database.html', items=items)
    except Exception:
        return render_template('database.html', items=[])

# ==========================================
# 4. 데이터 처리 로직 (POST) - SMS, LOG, DB 관리
# ==========================================

@app.route('/register_process', methods=['POST'])
def register_process():
    emp_id, password = request.form.get('emp_id'), request.form.get('password')
    name, phone, auth_code = request.form.get('name'), request.form.get('phone'), request.form.get('auth_code')
    if auth_code != "0123":
        return "<script>alert('관리자 허가번호 불일치'); history.back();</script>"
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO admins VALUES (?, ?, ?, ?)', (emp_id, password, name, phone))
        conn.commit()
        conn.close()
        return "<script>alert('등록 성공!'); location.href='/';</script>"
    except Exception as e:
        return f"오류: {e}"

@app.route('/login_process', methods=['POST'])
def login_process():
    session.clear()
    emp_id, password = request.form.get('username'), request.form.get('password')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM admins WHERE emp_id = ? AND password = ?', (emp_id, password))
    user = cursor.fetchone()
    conn.close()
    if user:
        session['user_id'], session['user_name'] = emp_id, user[0]
        add_log(f"{user[0]} 관리자 접속", "INFO")
        return redirect(url_for('main_page'))
    return "<script>alert('로그인 실패'); history.back();</script>"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/send_sms', methods=['POST'])
def send_sms():
    req_data = request.get_json() or {}
    to_number = req_data.get('to_number', '01081843638').replace('-', '')
    text = req_data.get('text', '관제 시스템 테스트')
    # Solapi 설정 (기존 키 유지)
    api_key, api_secret = 'NCS8OH3DQ6JGTFRN', 'Y8WIMULNXQ7T1JR2HVPH0BHVYRBMEP6I'
    date = datetime.datetime.now().isoformat() + 'Z'
    salt = str(uuid.uuid1().hex)
    signature = hmac.new(api_secret.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    headers = {'Authorization': f'HMAC-SHA256 apiKey={api_key}, date={date}, salt={salt}, signature={signature}', 'Content-Type': 'application/json'}
    data = {"message": {"to": to_number, "from": '01081843638', "text": text}}
    try:
        res = requests.post('https://api.solapi.com/messages/v4/send', headers=headers, json=data)
        return jsonify({"success": True})
    except Exception:
        return jsonify({"success": False})

def add_log(event_name, severity="INFO"):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now_kst = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('INSERT INTO logs (event, timestamp, severity) VALUES (?, ?, ?)', (event_name, now_kst, severity))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"로그 오류: {e}")

@app.route('/get_logs')
def get_logs():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id, event, timestamp, severity FROM logs ORDER BY id DESC LIMIT 50')
        rows = cursor.fetchall()
        conn.close()
        return jsonify([{"id": f"{r[0]:04d}", "event": r[1], "time": r[2], "severity": r[3]} for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)})

# 기타 DB 관리 라우트 (항상 동일하게 유지)
@app.route('/db_register', methods=['POST'])
def db_register():
    art_id, art_name = request.form.get('art_id'), request.form.get('art_name')
    location, price, status = request.form.get('art_location'), request.form.get('art_price'), request.form.get('art_status', '정상')
    file = request.files.get('art_image')
    image_path = "/static/css/no_image.png"
    if file:
        filename = secure_filename(f"{art_id}.jpg")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_path = f"/static/uploads/{filename}"
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO items (art_id, art_name, location, price, status, image_path) VALUES (?,?,?,?,?,?)', (art_id, art_name, location, price, status, image_path))
        conn.commit()
        conn.close()
        return "<script>alert('등록완료'); location.href='/database';</script>"
    except Exception:
        return "오류발생"

@app.route('/get_items')
def get_items():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM items')
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"art_id": r[0], "name": r[1], "location": r[2], "price": r[3], "status": r[4], "image": r[5]} for r in rows])

@app.route('/delete_item/<art_id>', methods=['POST'])
def delete_item(art_id):
    admin_name = session.get('user_name', '관리자')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM items WHERE art_id = ?', (art_id,))
    conn.commit()
    conn.close()
    add_log(f"{admin_name} 관리자가 {art_id} 삭제함", "WARN")
    return jsonify({"success": True})

@app.route('/api/verify_password', methods=['POST'])
def verify_password():
    input_pw = request.get_json().get('password')
    user_id = session.get('user_id')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM admins WHERE emp_id = ? AND password = ?', (user_id, input_pw))
    result = cursor.fetchone()
    conn.close()
    return jsonify({"success": bool(result)})

@app.route('/api/toggle_status', methods=['POST'])
def toggle_status():
    art_id = request.get_json().get('art_id')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM items WHERE art_id = ?', (art_id,))
    item = cursor.fetchone()
    if item:
        new_status = "비정상" if item[0] == "정상" else "정상"
        cursor.execute('UPDATE items SET status = ? WHERE art_id = ?', (new_status, art_id))
        conn.commit()
        add_log(f"상태 변경: {art_id} -> {new_status}", "INFO")
    conn.close()
    return jsonify({"success": True})

@app.route('/download_items')
def download_items():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT art_id, art_name, location, price, status FROM items')
    rows = cursor.fetchall()
    conn.close()
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Name', 'Location', 'Price', 'Status'])
    cw.writerows(rows)
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=items.csv"; output.headers["Content-type"] = "text/csv"
    return output

@app.route('/alert_status')
def alert_status(): return jsonify(alert_state)

@app.route('/clear_alert', methods=['POST'])
def clear_alert():
    alert_state["active"] = False
    return jsonify({"status": "cleared"})

# ==========================================
# 5. 서버 실행 (최종 파라미터 적용)
# ==========================================
if __name__ == '__main__':
    # [중요] threaded=True는 다중 피드 처리를 위해 필수입니다.
    # use_reloader=False는 개발 모드 중복 실행을 방지합니다.
    app.run(host='192.168.108.41', port=5000, debug=True, use_reloader=False, threaded=True)