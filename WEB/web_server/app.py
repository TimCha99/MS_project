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
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
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
# 알람 전역 상태: 도난 감지 시 팝업창을 띄우기 위한 서버 측 상태 플래그
alert_state = {"active": False, "zone": None}
recording_writers = {}

# ==========================================
# 2. 실시간 영상 스트리밍 엔진
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
    os.makedirs('records', exist_ok=True)
    now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = f"records/{cam_id}_{now}.avi" 
    
    # 1. 윈도우/리눅스에서 가장 안전한 XVID 코덱 사용
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    # 2. 전송 속도에 맞춰 FPS를 10.0으로 설정 (640x480 해상도 고정)
    writer = cv2.VideoWriter(file_path, fourcc, 10.0, (640, 480))

    with record_lock:
        # 3. 모든 정보(플래그, 도구, 경로)를 하나의 상자에 통합!
        record_state[cam_id] = {
            'is_recording': True,
            'writer': writer,
            'file_path': file_path
        }
    
    # 4. 🔥 [핵심] 일꾼 스레드를 여기서 직접 실행합니다!
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
            state['is_recording'] = False # 일꾼 멈춰!
            time.sleep(0.1) # 마지막 프레임 기록 대기
            state['writer'].release() # 뚜껑 닫기 (안 하면 Demux 에러)
            path = state['file_path']
            del record_state[cam_id] # 상자 비우기
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
    """
    [경로] /database (GET)
    [역할] DB에서 모든 자산(아이템) 레코드를 조회하여 관리 화면에 주입 후 렌더링함.
    [작동 원리] 동적 렌더링(SSR). 서버가 사용자의 요청을 받은 시점에 DB에서 데이터를 꺼내와 
    HTML 템플릿의 변수 영역에 데이터를 채워 넣어 완성된 페이지를 클라이언트에 전달함.
    """
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
# 4. 사용자 인증 및 보안
# ==========================================
@app.route('/register_process', methods=['POST'])
def register_process():
    """
    [경로] /register_process (POST)
    [역할] 회원가입 폼 데이터를 받아 허가번호(0123) 검증 후 새로운 관리자를 DB에 등록(Create)함.
    [파라미터] emp_id, password, name, phone, auth_code
    [반환값] 성공/실패 여부에 따른 자바스크립트 alert 및 리다이렉트 스크립트
    """
    emp_id, password = request.form.get('emp_id'), request.form.get('password')
    name, phone = request.form.get('name'), request.form.get('phone')
    
    if request.form.get('auth_code') != "0123":
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
    return "<script>alert('로그인 실패'); history.back();</script>"

@app.route('/logout')
def logout():
    """
    [경로] /logout (GET)
    [역할] 현재 활성화된 세션 데이터를 파기하여 인증 상태를 초기화(로그아웃)함.
    """
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/api/verify_password', methods=['POST'])
def verify_password():
    """
    [경로] /api/verify_password (POST)
    [역할] 자산 삭제 등 민감한 동작(Critical Action) 수행 전, 현재 세션 사용자의 비밀번호를 다시 검증하여 보안을 강화함.
    [파라미터] JSON: password (입력받은 비밀번호)
    [반환값] JSON: success (True/False)
    """
    input_pw = request.get_json().get('password')
    user_id = session.get('user_id')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM admins WHERE emp_id = ? AND password = ?', (user_id, input_pw))
    result = cursor.fetchone()
    conn.close()
    return jsonify({"success": bool(result)})

# ==========================================
# 5. 자산(아이템) 관리 CRUD
# ==========================================
@app.route('/db_register', methods=['POST'])
def db_register():
    """
    [경로] /db_register (POST)
    [역할] 신규 관제 대상(자산)의 텍스트 정보와 썸네일 이미지를 업로드받아 DB에 추가함 (CRUD: Create).
    [작동 원리] secure_filename을 통해 파일명 변조 공격을 방어하고, 서버 디렉토리에 물리적 파일을 저장한 뒤 그 경로를 DB에 기록함.
    [파라미터] 폼 데이터 (art_id, art_name, art_location, art_price, art_status, art_image)
    [반환값] 성공/실패 알림 스크립트
    """
    art_id, art_name = request.form.get('art_id'), request.form.get('art_name')
    location, price = request.form.get('art_location'), request.form.get('art_price')
    status = request.form.get('art_status', '정상')
    file = request.files.get('art_image')
    
    image_path = "/static/css/no_image.png"
    if file:
        filename = secure_filename(f"{art_id}.jpg")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_path = f"/static/uploads/{filename}"
        
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO items (art_id, art_name, location, price, status, image_path) VALUES (?,?,?,?,?,?)', 
                       (art_id, art_name, location, price, status, image_path))
        conn.commit()
        conn.close()
        return "<script>alert('등록완료'); location.href='/database';</script>"
    except Exception:
        return "오류발생"

@app.route('/get_items')
def get_items():
    """
    [경로] /get_items (GET)
    [역할] 클라이언트의 동적 렌더링을 위해 전체 자산 목록을 조회하여 반환함 (CRUD: Read).
    [반환값] JSON 배열 형태의 자산(아이템) 데이터 집합
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM items')
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"art_id": r[0], "name": r[1], "location": r[2], "price": r[3], "status": r[4], "image": r[5]} for r in rows])

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
    cursor.execute('DELETE FROM items WHERE art_id = ?', (art_id,))
    conn.commit()
    conn.close()
    add_log(f"{admin_name} 관리자가 {art_id} 삭제함", "WARN")
    return jsonify({"success": True})

@app.route('/api/toggle_status', methods=['POST'])
def toggle_status():
    """
    [경로] /api/toggle_status (POST)
    [역할] 특정 자산의 관리 상태값을 변경하고 그 이력을 로깅함 (CRUD: Update).
    [작동 원리] 현재 DB의 상태를 먼저 조회(SELECT)한 뒤, 파이썬 삼항 연산자로 논리를 반전시켜 다시 저장(UPDATE)함.
    [파라미터] JSON: art_id
    [반환값] JSON: success 여부
    """
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

# ==========================================
# 6. 시스템 이벤트 로깅 및 알림
# ==========================================
def add_log(event_name, severity="INFO"):
    """
    [역할] 백엔드 내부 로직에서 발생하는 모든 유의미한 활동(로그인, 자산수정 등)을 DB에 영구 기록하는 공통 유틸리티 함수.
    [파라미터] event_name (사건 내용 문자열), severity (로그 심각도: INFO/WARN/CRIT 등)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now_kst = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('INSERT INTO logs (event, timestamp, severity) VALUES (?, ?, ?)', (event_name, now_kst, severity))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"로그 오류: {e}")

@app.route('/api/add_log', methods=['POST'])
def api_add_log(): 
    """
    [경로] /api/add_log (POST)
    [역할] 클라이언트(JS) 환경에서 프론트엔드의 이벤트(예: 녹화 시작/종료)를 서버 DB에 비동기적으로 기록하기 위한 외부 노출 API.
    [파라미터] JSON: message, severity
    [반환값] JSON: success 여부
    """
    data = request.json
    add_log(data.get('message'), data.get('severity', 'INFO'))
    return jsonify({"success": True})

@app.route('/get_logs')
def get_logs():
    """
    [경로] /get_logs (GET)
    [역할] 대시보드의 실시간 로그창에 표시할 최신 이벤트 로그 50개를 조회하여 반환함.
    [작동 원리] 수많은 과거 로그를 전부 불러와 서버와 브라우저를 멈추게 하는 것을 방지하기 위해 'LIMIT 50' 쿼리로 뷰포트(Viewport)를 제한함.
    [반환값] JSON 배열 형태의 로그 데이터 목록
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id, event, timestamp, severity FROM logs ORDER BY id DESC LIMIT 50')
        rows = cursor.fetchall()
        conn.close()
        return jsonify([{"id": f"{r[0]:04d}", "event": r[1], "time": r[2], "severity": r[3]} for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/send_sms', methods=['POST'])
def send_sms():
    """
    [경로] /send_sms (POST)
    [역할] 보안 임계값 초과 시, 외부 통신 API(Solapi)를 활용해 관리자에게 긴급 SMS를 발송함.
    [작동 원리] API Key와 Secret, 그리고 타임스탬프와 난수(Salt)를 섞어 HMAC-SHA256 알고리즘으로 암호화된 
    '서명(Signature)'을 생성하여 외부 서버에 정당한 요청임을 증명함.
    [파라미터] JSON: to_number, text
    [반환값] JSON: success 여부
    """
    req_data = request.get_json() or {}
    to_number = req_data.get('to_number', '01081843638').replace('-', '')
    text = req_data.get('text', '관제 시스템 테스트')
    
    api_key, api_secret = 'NCS8OH3DQ6JGTFRN', 'Y8WIMULNXQ7T1JR2HVPH0BHVYRBMEP6I'
    date = datetime.datetime.now().isoformat() + 'Z'
    salt = str(uuid.uuid1().hex)
    signature = hmac.new(api_secret.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    
    headers = {
        'Authorization': f'HMAC-SHA256 apiKey={api_key}, date={date}, salt={salt}, signature={signature}', 
        'Content-Type': 'application/json'
    }
    
    try:
        requests.post('https://api.solapi.com/messages/v4/send', headers=headers, json={"message": {"to": to_number, "from": '01081843638', "text": text}})
        return jsonify({"success": True})
    except Exception:
        return jsonify({"success": False})

@app.route('/alert_status')
def alert_status(): 
    """
    [경로] /alert_status (GET)
    [역할] 클라이언트가 주기적으로 서버 상태를 확인하는 폴링(Polling) 요청에 응답하여, 현재 팝업 알람 활성화 여부(True/False)를 반환함.
    """
    return jsonify(alert_state)

@app.route('/clear_alert', methods=['POST'])
def clear_alert():
    """
    [경로] /clear_alert (POST)
    [역할] 관리자가 알람 팝업을 확인한 후, 시스템의 전역 경고 상태(alert_state)를 False로 초기화하여 중복 알람을 차단함.
    """
    alert_state["active"] = False
    return jsonify({"status": "cleared"})


@app.route('/api/robot_status', methods=['POST'])
def handle_robot_status():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data"}), 400

    robot_id = data.get('robot_id')
    battery = data.get('battery')
    status = data.get('status')

    if robot_id in robot_registry:
        robot_registry[robot_id]['battery'] = battery
        robot_registry[robot_id]['status'] = status
        # 현재 시간을 마지막 수신 시간으로 기록
        robot_registry[robot_id]['last_updated'] = time.time() 
        return jsonify({"success": True}), 200
    return jsonify({"success": False}), 404

@app.route('/api/get_robot_states', methods=['GET'])
def get_robot_states():
    current_time = time.time()
    for r_id in robot_registry:
        # 마지막 보고 후 5초 이상 소식이 없으면 연결 끊김으로 처리
        if current_time - robot_registry[r_id]['last_updated'] > 5.0:
            robot_registry[r_id]['status'] = 'DISCONNECTED'
            robot_registry[r_id]['battery'] = 0
    return jsonify(robot_registry)

# ==========================================
# 7. 데이터 추출 및 다운로드 (CSV)
# ==========================================
@app.route('/download_logs')
def download_logs():
    """
    [경로] /download_logs (GET)
    [역할] DB에 기록된 시스템 이벤트 전체 로그를 다운로드 가능한 CSV 파일로 제공함.
    [작동 원리] 하드디스크에 임시 파일을 쓰고 지우는 I/O 작업을 생략하기 위해, StringIO를 사용하여 
    메모리 버퍼 상에서 바로 CSV 문자열을 조립한 뒤 브라우저로 전송함. 서버 자원을 아끼는 최적화 로직.
    [반환값] MIME 타입이 text/csv로 강제 설정된 HTTP Response (첨부파일)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, event, timestamp, severity FROM logs ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Log ID', 'Event Description', 'Timestamp', 'Severity'])
    cw.writerows(rows)

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=security_event_logs.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/download_items')
def download_items():
    """
    [경로] /download_items (GET)
    [역할] DB에 등록된 전체 자산 관리 대장(items)을 CSV 파일 포맷으로 변환하여 백업용으로 제공함.
    [반환값] MIME 타입이 text/csv로 강제 설정된 HTTP Response (첨부파일)
    """
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
    output.headers["Content-Disposition"] = "attachment; filename=items.csv"
    output.headers["Content-type"] = "text/csv"
    return output

# ==========================================
# 8. 서버 실행
# ==========================================
if __name__ == '__main__':
    # [교수님 질문 대비] threaded=True: 영상 스트리밍(video_feed)은 계속 루프를 돌기 때문에 스레드를 하나 점유합니다.
    # 이 옵션이 없으면 첫 번째 접속자가 영상을 보는 동안 다른 사람은 로그인을 하거나 웹페이지에 접근할 수 없습니다. 
    # 다중 접속 처리를 위해 필수적인 설정입니다.
    # use_reloader=False: 개발 모드에서 코드가 변경될 때 서버가 두 번 실행되어 포트 충돌이 나는 현상을 방지합니다.
    app.run(host='192.168.108.60', port=5000, debug=True, use_reloader=False, threaded=True)