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
from werkzeug.utils import secure_filename
import csv
from io import StringIO
import threading
import threading
from werkzeug.utils import secure_filename
import csv
from io import StringIO

# ==========================================
# 1. 시스템 설정 및 초기화
# ==========================================
app = Flask(__name__)

# 세션을 안전하게 암호화하기 위한 비밀 키
app.secret_key = os.urandom(24)

# [카메라 설정] 0번 포트 + V4L2 백엔드 사용
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
app.secret_key = os.urandom(24)

# [수정] 업로드 폴더 및 DB 경로
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# [DB 경로 설정] 현재 파일 위치 기준으로 database 폴더 안의 db 파일 지정
DB_PATH = os.path.join(os.path.dirname(__file__), 'database/ms_database.db')

# [수정] 다중 카메라 지원을 위한 글로벌 변수 및 락(Lock)
# 이유: 여러 YOLO 노드가 동시에 접속할 때 데이터 충돌을 방지합니다.
frames = {
    # "cam1": {"data": None, "ts": 0},
    # "cam2": {"data": None, "ts": 0}, ...
}
frame_lock = threading.Lock()
# VALID_CAM_IDS에 터틀봇이 보내는 실제 이름을 추가하세요.
VALID_CAM_IDS = {"cam1", "cam2", "robot8_cam1", "robot8_cam2"}

# 🔥 캡쳐 이미지 저장용
captured_images = {}

# 🔥 캡쳐 폴더
CAPTURE_FOLDER = 'static/capture'
if not os.path.exists(CAPTURE_FOLDER):
    os.makedirs(CAPTURE_FOLDER)

#자동 보안 ON/OFF
security_active = False
#알림
alert_state = {"active": False, "zone": None}
@app.route('/api/security_status')
def security_status():
    global security_active

    return jsonify({
        "security_active": security_active
    })
#20시 되면 자동 보안 감지 시작, 6시 되면 자동으로 꺼짐
def security_scheduler():
    global security_active

    last_state = None

    while True:
        now = datetime.datetime.now().time()

        # 18:00 ~ 06:00
        if now >= datetime.time(12, 0) or now < datetime.time(6, 0):
            new_state = True
        else:
            new_state = False

        if new_state != last_state:
            security_active = new_state
            last_state = new_state

            print("🔒 ON" if new_state else "🔓 OFF")

        time.sleep(60) #1분마다 확인

# ==========================================
# 2. 영상 스트리밍 엔진
# ==========================================
# 알림 상태
alert_state = {
    "active": False,
    "zone": None,
    "captured_image": None,
    "db_image": None,
    "art_name": None
}

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
    last_sent_ts = 0  # 브라우저에 마지막으로 보낸 프레임의 시간
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

#테스트용 코드 
@app.route('/fake_frame')
def fake_frame():
    cam_id = "cam1"

    test_img_path = os.path.join("static/uploads", "990041.jpg")

    if not os.path.exists(test_img_path):
        return "❌ test.jpg 없음", 404

    with open(test_img_path, "rb") as f:
        frame_data = f.read()

    with frame_lock:
        frames[cam_id] = {
            "data": frame_data,
            "ts": time.time()
        }

    print("🧪 fake frame 삽입 완료")

    return "OK"
# ==========================================
# 3. 화면 렌더링 라우트 (GET)
# ==========================================

@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():        #로그인 페이지
    return render_template('login.html')

@app.route('/main')
def main_page():
    """[보안 구역] 메인 대시보드 - 로그인 체크 필수"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('main.html')

@app.route('/register') #관리자 등록
def register_page():
    return render_template('register.html')

@app.route('/database')
def database_page():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM web_items
        UNION ALL
        SELECT * FROM turtle_items
    ''')

    items = cursor.fetchall()
    conn.close()

    return render_template('database.html', items=items)

# ==========================================
# 4. 데이터 처리 로직 (POST) - SMS, LOG, DB 관리
# ==========================================

@app.route('/register_process', methods=['POST'])
def register_process():
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

@app.route('/logout')
def logout():   #관리자 로그아웃 시, 메인 페이지 접근 불가
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

@app.route('/send_sms', methods=['POST'])
def send_sms():
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

@app.route('/db_register', methods=['POST'])
def db_register():
    art_id = request.form.get('art_id')
    art_name = request.form.get('art_name')
    location = request.form.get('art_location')
    price = request.form.get('art_price')
    status = request.form.get('art_status', '정상')
    item_type = request.form.get('item_type')

    file = request.files.get('art_image')
    image_path = "/static/css/no_image.png"

    if file:
        filename = secure_filename(f"{art_id}.jpg")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_path = f"/static/uploads/{filename}"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    table = "turtle_items" if item_type == "turtle" else "web_items"

    cursor.execute(f'''
        INSERT INTO {table} (art_id, art_name, location, price, status, image_path)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (art_id, art_name, location, price, status, image_path))

    conn.commit()
    conn.close()

    return "<script>alert('등록 완료'); location.href='/database';</script>"
# 1. 전시품 목록 가져오기 API
@app.route('/get_items')
def get_items():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM web_items
        UNION ALL
        SELECT * FROM turtle_items
    ''')

    rows = cursor.fetchall()
    conn.close()

    return jsonify(rows)

# 2. 전시품 삭제 API
@app.route('/delete_item/<art_id>', methods=['POST'])
def delete_item(art_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DELETE FROM web_items WHERE art_id=?', (art_id,))
    cursor.execute('DELETE FROM turtle_items WHERE art_id=?', (art_id,))

    conn.commit()
    conn.close()

    return jsonify({"success": True})
    
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

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # web 먼저 확인
    cursor.execute('SELECT art_name, status FROM web_items WHERE art_id=?', (art_id,))
    item = cursor.fetchone()

    if item:
        table = "web_items"
    else:
        cursor.execute('SELECT art_name, status FROM turtle_items WHERE art_id=?', (art_id,))
        item = cursor.fetchone()
        table = "turtle_items"

    if not item:
        return jsonify({"success": False})

    new_status = "비정상" if item[1] == "정상" else "정상"

    cursor.execute(f'UPDATE {table} SET status=? WHERE art_id=?', (new_status, art_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True})
    
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

    # 전체
    cursor.execute('''
        SELECT art_id FROM web_items
        UNION
        SELECT art_id FROM turtle_items
    ''')
    all_items = set([r[0] for r in cursor.fetchall()])

    # 감지
    cursor.execute('SELECT art_id FROM detected_items')
    detected = set([r[0] for r in cursor.fetchall()])

    conn.close()

    return list(all_items - detected)

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
#도난 외부 감지 API
@app.route('/api/external_alert', methods=['POST'])
def external_alert():
    global alert_state

    data = request.get_json()
    art_id = data.get("art_id")
    cam_id = data.get("cam_id")

    if not art_id or not cam_id:
        return jsonify({"error": "missing data"}), 400

    # 캡쳐
    captured_path = capture_frame(cam_id)

    # DB 조회 (수정 완료 버전)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT art_id, art_name, location, image_path FROM web_items WHERE art_id=?
        UNION ALL
        SELECT art_id, art_name, location, image_path FROM turtle_items WHERE art_id=?
    ''', (art_id, art_id))

    item = cursor.fetchone()
    conn.close()

    if not item:
        return jsonify({"error": "item not found"}), 404

    # alert 상태
    alert_state = {
        "active": True,
        "cam_id": cam_id,
        "captured_image": captured_path,
        "missing_items": [{
            "id": item[0],
            "name": item[1],
            "location": item[2],
            "image": item[3]
        }]
    }

    add_log(f"[외부 감지] {art_id}", "CRIT")

    return jsonify({"success": True})

ALERT_IMAGE_PATH  =  "static/uploads/alert.jpg" 
def capture_frame(cam_id):
    with frame_lock:
        frame_obj = frames.get(cam_id)

    if not frame_obj:
        return None

    try:
        with open(ALERT_IMAGE_PATH, "wb") as f:
            f.write(frame_obj["data"])
        return "/" + ALERT_IMAGE_PATH
    except Exception as e:
        print("캡쳐 실패:", e)
        return None
    
#YOLO팀에 데이터베이스 테이블 보내주는 코드
@app.route('/items/<table_name>')
def get_items_simple(table_name):
    if table_name not in ['web_items', 'turtle_items']:
        return jsonify({"error": "invalid table"}), 400
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(f"SELECT art_name FROM {table_name}")
    rows = cursor.fetchall()

    conn.close()

    return jsonify({"items": [row[0] for row in rows]})

# 3. DB 데이터 내보내기 (CSV 다운로드)
@app.route('/download_items')
def download_items():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT art_id, art_name, location, price, status FROM web_items
        UNION ALL
        SELECT art_id, art_name, location, price, status FROM turtle_items
    ''')

    rows = cursor.fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Name', 'Location', 'Price', 'Status'])
    cw.writerows(rows)

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=items.csv"
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
#DB에서 도난 전시품 이름으로 찾기
def get_artifact(art_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT art_id, art_name, location, image_path FROM web_items WHERE art_id=?
        UNION
        SELECT art_id, art_name, location, image_path FROM turtle_items WHERE art_id=?
    ''', (art_id, art_id))

    item = cursor.fetchone()
    conn.close()

    return item

# ==========================================
# 5. 서버 실행
# ==========================================
if __name__ == '__main__':
    threading.Thread(target=security_scheduler, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)