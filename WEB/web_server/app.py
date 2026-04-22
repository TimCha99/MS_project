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
<<<<<<< HEAD
from werkzeug.utils import secure_filename
import csv
from io import StringIO
import threading
=======
import threading
from werkzeug.utils import secure_filename
import csv
from io import StringIO
>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503

# ==========================================
# 1. 시스템 설정 및 초기화
# ==========================================
app = Flask(__name__)
<<<<<<< HEAD

# 세션을 안전하게 암호화하기 위한 비밀 키
app.secret_key = os.urandom(24)

# [카메라 설정] 0번 포트 + V4L2 백엔드 사용
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)

=======
app.secret_key = os.urandom(24)

# [수정] 업로드 폴더 및 DB 경로
>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
<<<<<<< HEAD

# [DB 경로 설정] 현재 파일 위치 기준으로 database 폴더 안의 db 파일 지정
DB_PATH = os.path.join(os.path.dirname(__file__), 'database/ms_database.db')
=======
DB_PATH = os.path.join(os.path.dirname(__file__), 'database/ms_database.db')

>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
# [수정] 다중 카메라 지원을 위한 글로벌 변수 및 락(Lock)
# 이유: 여러 YOLO 노드가 동시에 접속할 때 데이터 충돌을 방지합니다.
frames = {
    # "cam1": {"data": None, "ts": 0},
    # "cam2": {"data": None, "ts": 0}, ...
}
frame_lock = threading.Lock()
# VALID_CAM_IDS에 터틀봇이 보내는 실제 이름을 추가하세요.
VALID_CAM_IDS = {"cam1", "cam2", "robot8_cam1", "robot8_cam2"}

<<<<<<< HEAD
#자동 보안 ON/OFF
security_active = False
#알림
alert_state = {"active": False, "zone": None}
#20시 되면 자동 보안 감지 시작, 6시 되면 자동으로 꺼짐
def security_scheduler():
    global security_active

    while True:
        now = datetime.datetime.now().time()

        # 20:00 ~ 23:59 OR 00:00 ~ 06:00
        if now >= datetime.time(18, 0) or now <= datetime.time(6, 0):
            if not security_active:
                print("🔒 자동 보안 ON")
                security_active = True
        else:
            if security_active:
                print("🔓 자동 보안 OFF")
                security_active = False

        time.sleep(10)  # 10초마다 체크

# ==========================================
# 2. 영상 스트리밍 엔진
# ==========================================
=======
# 알림 상태
alert_state = {"active": False, "zone": None}

# ==========================================
# 2. YOLO 영상 수신 및 스트리밍 엔진 (핵심 최적화)
# ==========================================

>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
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
<<<<<<< HEAD
    last_sent_ts = 0  # 브라우저에 마지막으로 보낸 프레임의 시간
=======
    """지능형 프레임 스킵이 적용된 스트리밍 엔진"""
    last_sent_ts = 0  # 브라우저에 마지막으로 보낸 프레임의 시간
    
>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
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

<<<<<<< HEAD


# ==========================================
# 3. 화면 렌더링 라우트 (GET)
# ==========================================
=======
# ==========================================
# 3. 화면 렌더링 라우트 (GET)
# ==========================================

>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/login')
<<<<<<< HEAD
def login_page():        #로그인 페이지
=======
def login_page():
>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
    return render_template('login.html')

@app.route('/main')
def main_page():
<<<<<<< HEAD
    """[보안 구역] 메인 대시보드 - 로그인 체크 필수"""
=======
>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('main.html')

<<<<<<< HEAD
@app.route('/register') #관리자 등록
=======
@app.route('/register')
>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
def register_page():
    return render_template('register.html')

@app.route('/database')
def database_page():
<<<<<<< HEAD
    """[핵심] DB에서 전시품 목록을 가져와서 페이지에 전달해야 합니다!"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. items 테이블의 모든 데이터 조회
        cursor.execute('SELECT * FROM items')
        items = cursor.fetchall() # 모든 행을 리스트로 가져옴
        conn.close()

        # 2. [중요] items 변수를 HTML로 넘겨줍니다.
        return render_template('database.html', items=items)
        
    except Exception as e:
        print(f"DB 조회 오류: {e}")
        return render_template('database.html', items=[]) # 오류 시 빈 목록 전달


# ==========================================
# 4. 데이터 처리 로직 (POST)
=======
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
>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
# ==========================================

@app.route('/register_process', methods=['POST'])
def register_process():
<<<<<<< HEAD
    """관리자 신규 가입 처리 (Master Code: 0123)"""
    emp_id = request.form.get('emp_id')
    password = request.form.get('password')
    name = request.form.get('name') 
    phone = request.form.get('phone')
    auth_code = request.form.get('auth_code')

    # 1. 마스터 코드 검증
    if auth_code != "0123":
        return "<script>alert('관리자 허가번호가 일치하지 않습니다.'); history.back();</script>"

    # 2. DB 저장
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO admins VALUES (?, ?, ?, ?)
        ''', (emp_id, password, name, phone))
        conn.commit()
        conn.close()
        return "<script>alert('등록 성공! 로그인을 진행해 주세요.'); location.href='/';</script>"
    except sqlite3.IntegrityError:
        return "<script>alert('이미 존재하는 사번입니다.'); history.back();</script>"
    except Exception as e:
        return f"DB 오류: {str(e)}"

@app.route('/login_process', methods=['POST'])
def login_process():
    # 보안을 위해 로그인 시도 직전에 한 번 더 세션을 비워줍니다.
    session.clear()
    
    emp_id = request.form.get('username')
    password = request.form.get('password')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 사번(emp_id)과 비밀번호로 관리자 조회
    cursor.execute('SELECT username FROM admins WHERE emp_id = ? AND password = ?', (emp_id, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        # 인증 성공 시 새로운 세션 정보 저장
        session['user_id'] = emp_id
        session['user_name'] = user[0]
        
        # 로그인 성공 로그 기록
        add_log(f"{user[0]} 관리자 접속", "INFO")
        
        return redirect(url_for('main_page'))
    else:
        return "<script>alert('아이디 또는 비밀번호가 틀렸습니다.'); history.back();</script>"

@app.route('/logout')   #관리자 로그아웃 시, 메인 페이지 접근 불가
=======
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
>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/send_sms', methods=['POST'])
def send_sms():
<<<<<<< HEAD
    """문자 발송 로직 (Solapi API)"""
    req_data = request.get_json() or {}
    to_number = req_data.get('to_number', '01081843638').replace('-', '')
    text = req_data.get('text', '관제 시스템 테스트')
    
    from_number = '01081843638' 
    api_key = 'NCS8OH3DQ6JGTFRN' 
    api_secret = 'Y8WIMULNXQ7T1JR2HVPH0BHVYRBMEP6I'

    date = datetime.datetime.now().isoformat() + 'Z'
    salt = str(uuid.uuid1().hex)
    signature = hmac.new(api_secret.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    
    headers = {
        'Authorization': f'HMAC-SHA256 apiKey={api_key}, date={date}, salt={salt}, signature={signature}',
        'Content-Type': 'application/json'
    }
    
    data = {"message": {"to": to_number, "from": from_number, "text": text}}
    
    try:
        res = requests.post('https://api.solapi.com/messages/v4/send', headers=headers, json=data)
        return jsonify({"success": True}) if 'errorCode' not in res.json() else jsonify({"success": False})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

def add_log(event_name, severity="INFO"):
    """시스템 이벤트를 logs 테이블에 한국 시간(KST)으로 저장하는 함수"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # [수정] 파이썬에서 직접 KST 시간을 생성합니다.
        now_kst = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # [수정] DB의 timestamp 컬럼에 직접 시간을 입력합니다.
        cursor.execute('''
            INSERT INTO logs (event, timestamp, severity) 
            VALUES (?, ?, ?)
        ''', (event_name, now_kst, severity))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"로그 저장 중 오류 발생: {e}")

# [추가] 로그 데이터를 전송하는 API 엔드포인트
@app.route('/get_logs')
def get_logs():
    """DB에서 최신 로그 50개를 가져와 JSON 형식으로 반환"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # 최신 로그가 위로 오도록 내림차순 정렬
        cursor.execute('SELECT id, event, timestamp, severity FROM logs ORDER BY id DESC LIMIT 50')
        rows = cursor.fetchall()
        conn.close()

        # 데이터 가공 (요청하신 형식 반영)
        logs = []
        for row in rows:
            logs.append({
                "id": f"{row[0]:04d}",
                "event": row[1],
                "time": row[2],
                "severity": row[3]
            })
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)})
    
=======
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

>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
@app.route('/download_logs')
def download_logs():
    """DB에 저장된 모든 로그를 CSV 파일로 변환하여 다운로드"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 최신 로그부터 과거 로그까지 모두 가져옵니다.
    cursor.execute('SELECT id, event, timestamp, severity FROM logs ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    # CSV의 첫 번째 줄(헤더) 작성
    cw.writerow(['Log ID', 'Event Description', 'Timestamp', 'Severity'])
    # 데이터 행 작성
    cw.writerows(rows)

    output = make_response(si.getvalue())
    # 다운로드되는 파일 이름 지정
    output.headers["Content-Disposition"] = "attachment; filename=security_event_logs.csv"
    output.headers["Content-type"] = "text/csv"
    return output

<<<<<<< HEAD
@app.route('/db_register', methods=['POST'])
def db_register():
    # 1. 폼 데이터 수집
    art_id = request.form.get('art_id') # 6자리 숫자
    art_name = request.form.get('art_name')
    location = request.form.get('art_location')
    price = request.form.get('art_price')
    status = request.form.get('art_status', '정상')

    # 2. 이미지 파일 처리
    file = request.files.get('art_image')
    image_path = "/static/css/no_image.png" # 기본 이미지
    
    if file:
        filename = secure_filename(f"{art_id}.jpg") # ID를 파일명으로 사용
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_path = f"/static/uploads/{filename}"

    # 3. DB 저장
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO items (art_id, art_name, location, price, status, image_path)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (art_id, art_name, location, price, status, image_path))
        conn.commit()
        conn.close()
        
        add_log(f"신규 전시품 등록: {art_name} ({art_id})", "INFO")
        return "<script>alert('전시품이 등록되었습니다.'); location.href='/database';</script>"
    except Exception as e:
        return f"등록 오류: {str(e)}"

# 1. 전시품 목록 가져오기 API
@app.route('/get_items')
def get_items():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM items')
    rows = cursor.fetchall()
    conn.close()

    items = []
    for row in rows:
        items.append({
            "art_id": row[0],
            "name": row[1],
            "location": row[2],
            "price": row[3],
            "status": row[4],
            "image": row[5]
        })
    return jsonify(items)

# 2. 전시품 삭제 API
@app.route('/delete_item/<art_id>', methods=['POST'])
def delete_item(art_id):
    try:
        # 1. 세션에서 현재 로그인한 관리자 이름 추출
        admin_name = session.get('user_name', '알 수 없는 관리자')
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # [디테일] 삭제 전, 로그에 남길 작품 이름을 미리 가져옵니다.
        cursor.execute('SELECT art_name FROM items WHERE art_id = ?', (art_id,))
        item = cursor.fetchone()
        item_name = item[0] if item else "알 수 없는 작품"
        
        # 2. DB에서 삭제 실행
        cursor.execute('DELETE FROM items WHERE art_id = ?', (art_id,))
        conn.commit()
        conn.close()
        
        # 3. [핵심] 관리자 이름을 포함하여 로그 기록
        add_log(f"{admin_name} 관리자가 전시품 [{item_name}({art_id})] 삭제함", "WARN")
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    
# [app.py] 수정된 비밀번호 검증 API
@app.route('/api/verify_password', methods=['POST'])
def verify_password():
    data = request.get_json()
    input_pw = data.get('password')
    user_id = session.get('user_id') # 세션에 저장된 사번

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # [수정 포인트] WHERE id -> WHERE emp_id
    cursor.execute('SELECT 1 FROM admins WHERE emp_id = ? AND password = ?', (user_id, input_pw))
    result = cursor.fetchone()
    conn.close()

    return jsonify({"success": bool(result)})

@app.route('/api/toggle_status', methods=['POST'])
def toggle_status():
    data = request.get_json()
    art_id = data.get('art_id')
    admin_name = session.get('user_name', '관리자')

    try:        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 현재 상태 확인
        cursor.execute('SELECT art_name, status FROM items WHERE art_id = ?', (art_id,))
        item = cursor.fetchone()
        
        if item:
            new_status = "비정상" if item[1] == "정상" else "정상"
            cursor.execute('UPDATE items SET status = ? WHERE art_id = ?', (new_status, art_id))
            conn.commit()
            
            # 로그 기록
            add_log(f"{admin_name} 관리자가 [{item[0]}] 상태를 {new_status}으로 전환함", "INFO")
            conn.close()
            return jsonify({"success": True})
        
        conn.close()
        return jsonify({"success": False, "error": "ID 미발견"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    
# 웹캠으로 인식한 전시품 품목 업데이트
@app.route('/api/update_detected', methods=['POST'])
def update_detected():
    global alert_state, security_active
    data = request.get_json()
    detected_list = data.get('items', [])  # ['A001', 'A002']

    print("📥 받은 감지:", detected_list)
    print("🔒 보안 상태:", security_active)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 기존 감지 데이터 삭제
    cursor.execute('DELETE FROM detected_items')

    # 새 데이터 삽입
    for art_id in detected_list:
        cursor.execute('INSERT INTO detected_items (art_id) VALUES (?)', (art_id,))
    conn.commit()
    conn.close()
    
    # 🔥 detected_items를 ID → 상세정보로 변환
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if detected_list:
        placeholders = ','.join(['?'] * len(detected_list))
        cursor.execute(f'''
            SELECT art_id, art_name, location
            FROM items
            WHERE art_id IN ({placeholders})
        ''', detected_list)

        alert_state["detected_items"] = [
            {"id": row[0], "name": row[1], "location": row[2]}
            for row in cursor.fetchall()
        ]
    else:
        alert_state["detected_items"] = []

    conn.close()

    missing = check_missing_items()

    if missing:
        alert_state["active"] = True
        alert_state["zone"] = "yolo"
        alert_state["missing"] = missing

        add_log(f"[YOLO] 도난 감지: {missing}", "CRIT")
        # 🔥 도난 감지 되면 alert에 로그 띄우기
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
    else:
        print("⛔ 보안 꺼짐 또는 이상 없음")

        placeholders = ','.join(['?'] * len(missing))
        cursor.execute(f'''
            SELECT art_id, art_name, location 
            FROM items 
            WHERE art_id IN ({placeholders})
        ''', missing)

        alert_state["missing_items"] = [
            {"id": row[0], "name": row[1], "location": row[2]}
            for row in cursor.fetchall()
        ]

        conn.close()
    print("📥 받은 데이터:", detected_list)
    return jsonify({"success": True, "missing": missing})
# 사라진 전시품이 있는지 확인하는 코드
def check_missing_items():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 전체 전시품
    cursor.execute('SELECT art_id FROM items')
    all_items = set([row[0] for row in cursor.fetchall()])

    # 현재 감지된 전시품
    cursor.execute('SELECT art_id FROM detected_items')
    detected_items = set([row[0] for row in cursor.fetchall()])

    conn.close()

    # 사라진 전시품
    missing = all_items - detected_items

    return list(missing)

# 경보 트리거
@app.route('/api/check_theft')
def check_theft():
    missing = check_missing_items()
    missing = check_missing_items()
    print("🚨 missing:", missing)
    if missing:
        global alert_state
        alert_state = {
            "active": False,
            "zone": None,
            "detected_items": [],
            "missing_items": []
        }

        add_log(f"도난 의심: {missing}", "CRIT")

        return jsonify({
            "alert": True,
            "missing_items": missing
        })

    return jsonify({"alert": False})

# 3. DB 데이터 내보내기 (CSV 다운로드)
=======
>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
@app.route('/download_items')
def download_items():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT art_id, art_name, location, price, status FROM items')
    rows = cursor.fetchall()
    conn.close()
<<<<<<< HEAD
 
    # CSV 생성
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Name', 'Location', 'Price', 'Status']) # 헤더
    cw.writerows(rows)
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=museum_items_db.csv"
    return output

# ======================
# Alert 페이지
# ======================
@app.route('/alert_popup')
def alert_popup():
    return render_template('alert.html')

# ======================
# Alert 상태 API (이미 있음이면 수정만)
# ======================
@app.route('/alert_status')
def alert_status():
    return jsonify(alert_state)


# ======================
# Alert 초기화 (무시 버튼)
# ======================
@app.route('/clear_alert', methods=['POST'])
def clear_alert():
    alert_state["active"] = False
    alert_state["zone"] = None
    return jsonify({"status": "cleared"})
'''
#테스트용 버튼
@app.route('/trigger_alert')
def trigger_alert():
    global alert_state
    alert_state["active"] = True
    alert_state["zone"] = "zoneA"  # 테스트용
    return {"status": "triggered"}
    '''
#DB에서 도난 전시품 이름으로 찾기
def get_artifact_by_name(artifact_id):
    conn = sqlite3.connect('database/ms_database.db')
    cursor = conn.cursor()

    cursor.execute("""
            SELECT art_id, art_name, location, price, status, image_path
            FROM items
            WHERE art_id = ?
        """, (artifact_id,))

    result = cursor.fetchone()
    conn.close()

    return result
'''
#도난 됐을 때 예시 버튼(삭제)
@app.route('/api/theft_detected', methods=['POST'])
def theft_detected():
    data = request.get_json()
    artifact_id = data.get('artifact_id')  # ✔ ID 기준

    admin_name = session.get('user_name', 'SYSTEM')

    try:
        conn = sqlite3.connect('database/ms_database.db')
        cursor = conn.cursor()

        # 1. 전시품 조회 (ID 기준)
        cursor.execute("""
            SELECT art_id, art_name, location, price, status, image_path
            FROM items
            WHERE art_id = ?
        """, (artifact_id,))

        item = cursor.fetchone()

        if not item:
            return jsonify({
                "success": False,
                "error": "해당 ID의 전시품이 없습니다."
            })

        _id, name, location, price, status, image_path = item

        # 2. 이미 도난 상태면 중복 방지
        if status == "abnormal":
            return jsonify({
                "success": True,
                "message": "이미 도난 상태입니다."
            })

        # 3. 상태 변경 (도난 처리)
        cursor.execute("""
            UPDATE items
            SET status = 'abnormal'
            WHERE art_id = ?
        """, (artifact_id,))

        conn.commit()
        conn.close()

        # 4. 로그 기록
        add_log(f"[도난 감지] {name} (ID:{artifact_id}, {location}) abnormal 전환", "CRIT")

        return jsonify({
            "success": True,
            "message": f"{name} 도난 처리 완료"
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
        '''
# ==========================================
# 5. 서버 실행
# ==========================================
if __name__ == '__main__':
    #app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    if __name__ == '__main__':
        threading.Thread(target=security_scheduler, daemon=True).start()
        app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
=======
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
>>>>>>> 0f17db195d509976f27c12d53333e6d7a04cd503
