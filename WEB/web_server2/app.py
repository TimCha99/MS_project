"""
MS-CMS (Museum Security Hub) - Main Server
다중 카메라 실시간 관제, 보안 로그 기록, 자산(아이템) 관리를 수행하는 Flask 백엔드 서버입니다.
작성 목적: 시스템 아키텍처의 중앙 관제탑 역할 수행 (영상 중계, DB CRUD, 알림 통신)
"""

# ==========================================
# [표준 라이브러리: 시스템 제어 및 데이터 가공]
# ==========================================
import os           # 운영체제 인터페이스: 로그 DB 경로 설정 및 업로드 파일 저장 디렉토리 생성/관리
import time         # 정밀 시간 측정: 프레임 간의 간격을 계산하고 타임스탬프를 비교하여 중복 전송을 방지함
import datetime     # 포맷팅된 시간: '2026-04-23'과 같이 관리자가 읽기 쉬운 형태로 로그 시간을 변환함
import cv2

import uuid         # 유니크 ID 생성: 외부 서버 통신 시 보안을 위해 매 요청마다 중복되지 않는 난수(Salt)를 발급함
import hmac         # 보안 인증: 비밀키를 사용해 메시지가 중간에 변조되지 않았음을 증명하는 서명 알고리즘을 수행함
import hashlib      # 암호 해싱: SHA-256 알고리즘을 사용해 데이터를 안전한 64글자 문자열로 변환함

import sqlite3      # 임베디드 DB: 서버 내부에 경량 관계형 데이터베이스를 구축하여 자산 정보와 로그를 영구 관리함
import threading    # 멀티스레딩 제어: 여러 대의 로봇(스레드)이 동시에 영상 데이터를 쓸 때 충돌(Race Condition)을 막음
import csv          # 데이터 포맷: DB의 정형 데이터를 범용적인 엑셀(CSV) 형식으로 구조화함
from io import StringIO  # 가상 파일 버퍼: 실제 파일을 디스크에 쓰지 않고 메모리 안에서 데이터를 주고받아 성능을 높임
import numpy as np

# ==========================================
# [외부 라이브러리: 네트워크 및 웹 프레임워크]
# ==========================================
import requests     # 외부 API 요청: Solapi 등 외부 통신 규격에 맞춰 서버 간 HTTP 통신을 수행함

# Flask: 경량 웹 서버 프레임워크 (시스템의 메인 관제탑 엔진)
from flask import (
    Flask,          # 웹 애플리케이션 프레임워크 객체: 전체 서버의 중심 엔진 역할을 함
    render_template,# 동적 렌더링: HTML 템플릿에 서버의 DB 데이터를 끼워 넣어 완성된 웹 페이지를 만듦(Server-Side Rendering)
    request,        # 클라이언트 데이터 수신: 클라이언트가 보낸 폼 데이터, 파일, JSON 등을 가로채어 분석함
    Response,       # 스트리밍 응답: 영상을 한 번에 보내지 않고 데이터 조각으로 끊임없이 흘려보내는 특수 응답 수행
    jsonify,        # 데이터 직렬화: 파이썬 객체를 자바스크립트가 읽을 수 있는 JSON 포맷으로 변환함
    session,        # 사용자 세션 관리: 브라우저에 임시 열쇠를 맡겨 로그아웃 전까지 로그인 상태를 안전하게 유지함
    redirect,       # 강제 페이지 이동: 접근 권한이 없거나 특정 작업 완료 후 다른 화면으로 사용자를 보냄
    url_for,        # 경로 자동 계산: 폴더 구조가 바뀌어도 에러 없이 라우트 주소를 동적으로 찾아줌
    make_response   # 응답 커스텀: 파일 다운로드 시 브라우저에 '텍스트가 아니라 파일'이라고 헤더를 직접 조작함
)

# Werkzeug 보안 유틸리티
from werkzeug.utils import secure_filename  # 파일 보안: 업로드 파일명에 포함된 악성 스크립트나 비정상 경로를 필터링함


# ==========================================
# 1. 서버 초기화 및 전역 설정
# ==========================================
app = Flask(__name__)
# 세션 데이터 암호화를 위한 시크릿 키 (이 키가 있어야 쿠키 변조를 막을 수 있음)
app.secret_key = os.urandom(24)

# 업로드 폴더 및 DB 경로 보장 (폴더가 없으면 자동으로 생성함)
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DB_PATH = os.path.join(os.path.dirname(__file__), 'database/ms_database.db')

# 다중 카메라 스트리밍 상태 관리 변수
# frames: 로봇이 영상을 쓰고 웹이 읽어가는 메모리 상의 공유 저장소
frames = {} 
# frame_lock: 여러 스레드가 frames에 동시 접근할 때 데이터가 깨지지 않게 막아주는 뮤텍스(Mutex) 잠금장치
frame_lock = threading.Lock() 

record_state = {}
record_lock = threading.Lock()

robot_registry = {
    'TURTLEBOT_01': {'battery': 0, 'status': 'DISCONNECTED', 'last_updated': 0},
    'TURTLEBOT_02': {'battery': 0, 'status': 'DISCONNECTED', 'last_updated': 0}
}

# 화이트리스트 보안: 등록된 ID를 가진 카메라/로봇의 접속만 허용함
VALID_CAM_IDS = {"cam1", "cam2", "robot8_cam1", "robot8_cam2"}

# 캡쳐 이미지 저장용
captured_images = {}

# 캡쳐 폴더
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

    if not file or not cam_id:
        return jsonify({"status": "error"}), 400

    # 1. 자물쇠를 걸기 전에, 시간이 걸리는 I/O(데이터 읽기)를 먼저 각자 수행합니다.
    img_bytes = file.read()
    current_time = time.time()

    # 2. 아주 짧은 찰나에만 자물쇠를 걸고 데이터를 덮어씁니다.
    with frame_lock:
        frames[cam_id] = {"data": img_bytes, "ts": current_time}

    return jsonify({"status": "ok", "cam_id": cam_id})

def generate_frames(cam_id):
    """
    [역할] 브라우저에 연속적인 영상 스트림(MJPEG)을 공급하는 제너레이터 함수.
    [작동 원리] 지능형 프레임 스킵 로직 적용. 타임스탬프(ts)를 비교하여 이전 프레임과 동일하면 전송하지 않고 
    대기하여 무의미한 네트워크 대역폭 및 CPU 낭비를 방지함.
    [파라미터] cam_id (대상 카메라 식별자)
    [반환값] HTTP 멀티파트 응답 규격에 맞춘 이미지 바이트 스트림 (yield)
    """
    last_sent_ts = 0 
    while True:
        with frame_lock:
            frame_obj = frames.get(cam_id)

        # 데이터가 없거나 방금 전송한 프레임(시간 동일)인 경우 송출하지 않고 대기
        if not frame_obj or frame_obj["ts"] <= last_sent_ts:
            time.sleep(0.01)
            continue

        # 브라우저에 이미지가 계속 바뀔 것임을 알리는 MJPEG 프로토콜 헤더
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_obj["data"] + b'\r\n')
        
        last_sent_ts = frame_obj["ts"]
        time.sleep(0.08) # 브라우저 과부하 방지용 지연시간 (약 12.5 FPS 제한)

@app.route('/video/<cam_id>')
def video_feed(cam_id):
    """
    [경로] /video/<cam_id> (GET)
    [역할] 클라이언트(웹 브라우저)의 <img> 태그와 연결되어 실시간 영상 스트림을 송출함.
    [작동 원리] Response 객체에 제너레이터를 담아 브라우저가 연결을 끊기 전까지 계속 데이터를 쏘게 함(On-the-fly 처리).
    [파라미터] URL 내 동적 변수 <cam_id>
    [반환값] multipart/x-mixed-replace 타입의 Response 객체
    """
    if cam_id not in VALID_CAM_IDS:
        return "Invalid cam_id", 400
    return Response(generate_frames(cam_id), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/start_record/<cam_id>', methods=['POST'])
def start_record(cam_id):
    # [추가] 녹화 시작 시 즉시 로그 기록
    add_log(f"[{cam_id}] 레코딩을 시작합니다", "WARN")
    
    os.makedirs('records', exist_ok=True)
    now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = f"records/{cam_id}_{now}.avi" 
    
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    writer = cv2.VideoWriter(file_path, fourcc, 10.0, (640, 480))

    with record_lock:
        record_state[cam_id] = {
            'is_recording': True,
            'writer': writer,
            'file_path': file_path
        }
    
    t = threading.Thread(target=record_loop, args=(cam_id,))
    t.daemon = True 
    t.start()
    
    return jsonify({"success": True})

def record_loop(cam_id):
    last_ts = 0
    while record_state.get(cam_id, {}).get('is_recording', False):
        with frame_lock:
            frame_obj = frames.get(cam_id)
        
        if frame_obj and frame_obj["ts"] > last_ts:
            np_arr = np.frombuffer(frame_obj["data"], np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if img is not None:
                # 🔥 [해결책] 인코더가 기다리는 규격(640, 480)으로 무조건 깎아버립니다.
                # 이 한 줄이 5.7KB를 5MB로 만들어줄 핵심 포인트입니다!
                img = cv2.resize(img, (640, 480))
                
                # record_state에서 안전하게 writer를 꺼내서 기록
                record_state[cam_id]['writer'].write(img)
                last_ts = frame_obj["ts"]
                
        time.sleep(0.05) # 루프 속도를 전송 속도보다 빠르게 유지

@app.route('/api/stop_record/<cam_id>', methods=['POST'])
def stop_record(cam_id):
    with record_lock:
        state = record_state.get(cam_id)
        if state and state.get('is_recording'):
            state['is_recording'] = False
            time.sleep(0.1) 
            state['writer'].release()
            path = state['file_path']
            del record_state[cam_id]
            
            # [추가] 녹화 종료 시 로그 기록
            add_log(f"[{cam_id}] 레코딩을 종료하고 저장했습니다", "INFO")
            return jsonify({"success": True, "file": path})
    return jsonify({"success": False, "error": "Not recording"})

# ==========================================
# 3. 화면 렌더링 라우트
# ==========================================
@app.route('/')
def index():
    """
    [경로] / (GET)
    [역할] 최상위 도메인 접속 시 기존 세션을 초기화하여 보안을 확보하고 로그인 페이지로 리다이렉트함.
    """
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    """
    [경로] /login (GET)
    [역할] 관리자 인증을 위한 첫 화면(login.html)을 렌더링함.
    """
    return render_template('login.html')

@app.route('/main')
def main_page():
    """
    [경로] /main (GET)
    [역할] 관제 시스템 메인 대시보드를 렌더링함. 
    [보안] 세션(Session)에 'user_id'가 없는 미인증 사용자의 접근을 원천 차단함.
    """
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('main.html')

@app.route('/register')
def register_page():
    """
    [경로] /register (GET)
    [역할] 신규 관리자 계정 생성 화면(register.html)을 렌더링함.
    """
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
# 4. 사용자 인증 및 보안
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
        cursor.execute('INSERT INTO admins VALUES (?, ?, ?, ?)', (emp_id, password, name, phone))
        conn.commit()
        conn.close()
        return "<script>alert('등록 성공! 로그인을 진행해 주세요.'); location.href='/';</script>"
    except sqlite3.IntegrityError:
        return "<script>alert('이미 존재하는 사번입니다.'); history.back();</script>"
    except Exception as e:
        return f"DB 오류: {str(e)}"

@app.route('/login_process', methods=['POST'])
def login_process():
    """
    [경로] /login_process (POST)
    [역할] 로그인 폼에서 전달된 자격 증명을 대조하고, 유효 시 세션(Session)을 발급함.
    [작동 원리] SQL 인젝션 방어를 위해 파라미터 바인딩(?) 방식을 사용하여 DB를 조회하고, 
    인증된 사용자에게만 서버 메모리 기반의 세션 ID를 부여하여 지속적인 인증 상태를 유지함.
    [파라미터] username, password
    [반환값] 성공 시 메인 페이지 리다이렉트, 실패 시 경고창 스크립트
    """
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
    """
    [역할] DB에 기록된 시스템 이벤트 전체 로그를 CSV 파일로 변환하여 다운로드합니다.
    [최적화] StringIO를 사용하여 서버 하드디스크를 사용하지 않고 메모리에서 직접 파일을 생성합니다.
    """
    try:
        # 1. DB 연결 및 로그 조회 (최신순)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id, event, timestamp, severity FROM logs ORDER BY id DESC')
        rows = cursor.fetchall()
        conn.close()

        # 2. 메모리 상에 가상 파일(StringIO) 생성
        si = StringIO()
        cw = csv.writer(si)
        
        # 3. CSV 헤더(제목줄) 및 데이터 작성
        cw.writerow(['Log ID', 'Event Description', 'Timestamp', 'Severity'])
        cw.writerows(rows)

        # 4. Flask 응답 객체 생성 및 헤더 설정
        output = make_response(si.getvalue())
        
        # 파일명을 'security_event_logs_날짜.csv' 형태로 다운로드되게 설정
        now_str = datetime.datetime.now().strftime('%Y%m%d')
        output.headers["Content-Disposition"] = f"attachment; filename=MS_CMS_Logs_{now_str}.csv"
        output.headers["Content-type"] = "text/csv"
        
        return output
    except Exception as e:
        add_log(f"로그 다운로드 중 오류 발생: {str(e)}", "CRIT")
        return f"다운로드 오류: {str(e)}", 500
    
@app.route('/api/robot_status', methods=['POST'])
def handle_robot_status():
    """터틀봇(ROS 2)이 보내는 실시간 배터리 및 연결 상태를 수신하여 서버 메모리에 갱신"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data"}), 400

    robot_id = data.get('robot_id')
    battery = data.get('battery')
    status = data.get('status')

    # 등록된 로봇(TURTLEBOT_01, 02)인지 확인 후 상태 업데이트
    if robot_id in robot_registry:
        robot_registry[robot_id]['battery'] = battery
        robot_registry[robot_id]['status'] = status
        # 현재 시간을 마지막 수신 시간으로 기록 (워치독 용도)
        robot_registry[robot_id]['last_updated'] = time.time() 
        return jsonify({"success": True}), 200
        
    return jsonify({"success": False}), 404

@app.route('/api/get_robot_states', methods=['GET'])
def get_robot_states():
    """웹 대시보드(main.html)에서 2초마다 호출하여 로봇들의 최신 상태를 가져감"""
    current_time = time.time()
    for r_id in robot_registry:
        # 마지막 보고 후 5초 이상 소식이 없으면 연결 끊김으로 처리 (워치독 작동)
        if current_time - robot_registry[r_id]['last_updated'] > 5.0:
            robot_registry[r_id]['status'] = 'DISCONNECTED'
            robot_registry[r_id]['battery'] = 0
            
    return jsonify(robot_registry)

# ==========================================
# 5. 자산(아이템) 관리 CRUD
# ==========================================
@app.route('/db_register', methods=['POST'])
def db_register():
    # 누가 등록했는지 세션에서 가져옵니다 (없으면 '관리자')
    admin_name = session.get('user_name', '관리자') 

    art_id, art_name = request.form.get('art_id'), request.form.get('art_name')
    location, price = request.form.get('art_location'), request.form.get('art_price')
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

    # 🔥 [핵심 추가] 등록이 완료되면 조용히 로그를 남깁니다.
    add_log(f"{admin_name}님이 신규 전시품 [{art_name}] 등록", "INFO")

    return "<script>alert('등록 완료'); location.href='/database';</script>"

# 1. 전시품 목록 가져오기 API
@app.route('/get_items')
def get_items():
    """
    [경로] /get_items (GET)
    [역할] 클라이언트의 동적 렌더링을 위해 전체 자산 목록을 조회하여 반환함 (CRUD: Read).
    [반환값] JSON 배열 형태의 자산(아이템) 데이터 집합
    """
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
    """
    [경로] /delete_item/<art_id> (POST)
    [역할] 특정 자산 데이터를 DB에서 영구 삭제함 (CRUD: Delete).
    [작동 원리] 데이터 삭제 트랜잭션 수행과 동시에, 누가 삭제했는지에 대한 보안 감사(Audit Trail) 로그를 필수적으로 남김.
    [파라미터] URL 동적 변수 <art_id>
    [반환값] JSON: success 여부
    """
    admin_name = session.get('user_name', '관리자')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DELETE FROM web_items WHERE art_id=?', (art_id,))
    cursor.execute('DELETE FROM turtle_items WHERE art_id=?', (art_id,))

    conn.commit()
    conn.close()
    add_log(f"{admin_name} 관리자가 {art_id} 삭제함", "WARN")
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
    
    # 상태를 바꾼 사람이 누구인지 추적합니다.
    admin_name = session.get('user_name', '관리자') 

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

    art_name = item[0]
    new_status = "비정상" if item[1] == "정상" else "정상"

    cursor.execute(f'UPDATE {table} SET status=? WHERE art_id=?', (new_status, art_id))
    conn.commit()
    conn.close()

    # 🔥 [핵심 추가] 팝업 없이 시스템 로그만 남깁니다. (심각도는 INFO)
    add_log(f"{admin_name}님이 [{art_name}] 상태를 '{new_status}'(으)로 변경", "INFO")

    return jsonify({"success": True})
    
# 웹캠으로 인식한 전시품 품목 업데이트
@app.route('/api/update_detected', methods=['POST'])
def update_detected():
    global alert_state, security_active
    data = request.get_json()
    detected_list = data.get('items', [])  # 예: ['A001', 'pig']

    print("📥 받은 감지:", detected_list)
    print("🔒 보안 상태:", security_active)

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. 기존 감지 데이터 삭제
        cursor.execute('DELETE FROM detected_items')
        
        # 2. 새 데이터 삽입 (NOT NULL 제약 조건 해결 로직)
        for art_id in detected_list:
            # DB에서 실제 이름을 조회합니다.
            cursor.execute('''
                SELECT art_name FROM web_items WHERE art_id = ?
                UNION ALL
                SELECT art_name FROM turtle_items WHERE art_id = ?
            ''', (art_id, art_id))
            row = cursor.fetchone()
            
            # [핵심] 이름을 찾으면 그 이름을, 못 찾으면(예: pig) 레이블 자체를 이름으로 씁니다.
            art_name = row[0] if row else f"미등록({art_id})"
            
            # 이제 art_id와 art_name을 모두 채워서 넣습니다!
            cursor.execute('INSERT INTO detected_items (art_id, art_name) VALUES (?, ?)', (art_id, art_name))
        
        conn.commit()
        
        # 3. 상세 정보 변환 및 도난 확인 (전체 테이블 통합 검색)
        if detected_list:
            placeholders = ','.join(['?'] * len(detected_list))
            query = f'''
                SELECT art_id, art_name, location FROM web_items WHERE art_id IN ({placeholders})
                UNION ALL
                SELECT art_id, art_name, location FROM turtle_items WHERE art_id IN ({placeholders})
            '''
            cursor.execute(query, detected_list + detected_list)
            alert_state["detected_items"] = [
                {"id": row[0], "name": row[1], "location": row[2]}
                for row in cursor.fetchall()
            ]
        else:
            alert_state["detected_items"] = []

        missing = check_missing_items()

        if missing:
            alert_state["active"] = True
            alert_state["zone"] = "yolo"
            alert_state["missing"] = missing
            add_log(f"[YOLO] 도난 감지: {missing}", "CRIT")
            
            # 도난 품목 상세 정보 가져오기
            placeholders = ','.join(['?'] * len(missing))
            query = f'''
                SELECT art_id, art_name, location FROM web_items WHERE art_id IN ({placeholders})
                UNION ALL
                SELECT art_id, art_name, location FROM turtle_items WHERE art_id IN ({placeholders})
            '''
            cursor.execute(query, missing + missing)
            alert_state["missing_items"] = [
                {"id": row[0], "name": row[1], "location": row[2]}
                for row in cursor.fetchall()
            ]
        else:
            alert_state["missing_items"] = []

        conn.close()

    except Exception as e:
        print(f"❌ update_detected 에러 발생: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

    print("✅ 데이터 처리 완료")
    return jsonify({"success": True, "missing": missing})

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
    """
    [경로] /download_items (GET)
    [역할] DB에 등록된 전체 자산 관리 대장(items)을 CSV 파일 포맷으로 변환하여 백업용으로 제공함.
    [반환값] MIME 타입이 text/csv로 강제 설정된 HTTP Response (첨부파일)
    """
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
    output.headers["Content-type"] = "text/csv"
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
# 8. 서버 실행
# ==========================================
if __name__ == '__main__':
    threading.Thread(target=security_scheduler, daemon=True).start()
    app.run(host='192.168.108.60', port=5000, debug=True, use_reloader=False)