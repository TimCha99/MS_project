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

# ==========================================
# 1. 시스템 설정 및 초기화
# ==========================================
app = Flask(__name__)

# 세션을 안전하게 암호화하기 위한 비밀 키
app.secret_key = os.urandom(24)

# [카메라 설정] 0번 포트 + V4L2 백엔드 사용
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# [DB 경로 설정] 현재 파일 위치 기준으로 database 폴더 안의 db 파일 지정
DB_PATH = os.path.join(os.path.dirname(__file__), 'database/ms_database.db')


# ==========================================
# 2. 영상 스트리밍 엔진
# ==========================================
def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            print("카메라를 읽을 수 없습니다.")
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video_feed')
def video_feed():
    """실시간 영상 스트리밍 파이프라인"""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


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
    """[보안 구역] 메인 대시보드 - 로그인 체크 필수"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('main.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/database')
def database_page():
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
        conn = sqlite3.connect(DB_PATH, timeout=10) # 10초 동안 대기 허용
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO admins (emp_id, password, username, phone) 
            VALUES (?, ?, ?, ?)
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
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/send_sms', methods=['POST'])
def send_sms():
    """문자 발송 로직 (Solapi API)"""
    req_data = request.get_json() or {}
    to_number = req_data.get('to_number', '01081843638').replace('-', '')
    text = req_data.get('text', '종진아 화이팅')
    
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

# 3. DB 데이터 내보내기 (CSV 다운로드)
@app.route('/download_items')
def download_items():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT art_id, art_name, location, price, status FROM items')
    rows = cursor.fetchall()
    conn.close()

    # CSV 생성
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['작품ID', '작품명', '위치', '가격', '상태']) # 헤더
    cw.writerows(rows)
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=museum_items_db.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8-sig" # 한글 깨짐 방지
    return output

# ==========================================
# 5. 서버 실행
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)