# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, send_file
import sqlite3
import cv2
import time
import os
from collections import deque
import threading
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'secret_key'

DB = 'MS_db.db'
UPLOAD_FOLDER = 'static/images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
turtlebot_location = {"x": 0, "y": 0, "zone": "A"}
turtle_cam = cv2.VideoCapture("http://192.168.108.108:8080/video0")
if not turtle_cam.isOpened():
    print("turtlebot camera upload fail")

# ======================
# DB 연결 함수
# ======================
def get_db():
    return sqlite3.connect(DB)

# ======================
# 로그인
# ======================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['username'] = username
            return redirect(url_for('home'))
        else:
            flash("Login Failed")

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ======================
# 홈
# ======================
@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('home.html')

# ======================
# 전시품 CRUD
# ======================
@app.route('/artifacts')
def artifacts():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM artifacts")
    data = cursor.fetchall()
    conn.close()
    return render_template('artifacts.html', data=data)


@app.route('/add_artifact', methods=['GET', 'POST'])
def add_artifact():
    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        price = request.form['price']

        file = request.files['image']
        filename = secure_filename(file.filename)

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO artifacts (name, location, price, image)
        VALUES (?, ?, ?, ?)
        """, (name, location, price, filepath))

        conn.commit()
        conn.close()

        return redirect(url_for('artifacts'))

    return render_template('add_artifact.html')


@app.route('/edit_artifact/<int:id>', methods=['GET', 'POST'])
def edit_artifact(id):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        price = request.form['price']

        cursor.execute("UPDATE artifacts SET name=?, location=?, price=? WHERE id=?",
                       (name, location, price, id))
        conn.commit()
        conn.close()
        return redirect(url_for('artifacts'))

    cursor.execute("SELECT * FROM artifacts WHERE id=?", (id,))
    data = cursor.fetchone()
    conn.close()
    return render_template('edit_artifact.html', data=data)


@app.route('/delete_artifact/<int:id>')
def delete_artifact(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM artifacts WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('artifacts'))

# ======================
# 영상 스트리밍 + 저장
# ======================
camera = cv2.VideoCapture(0)
FPS = 20
buffer = deque(maxlen=FPS * 30)

def gen_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break

        buffer.append(frame.copy())

        _, buffer_img = cv2.imencode('.jpg', frame)
        frame_bytes = buffer_img.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


# ======================
# 영상 저장 (버튼)
# ======================
def save_video(filename):
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, FPS, (640, 480))

    for frame in buffer:
        out.write(frame)

    out.release()


@app.route('/save_video')
def save_video_route():
    filename = f"static/videos/manual_{int(time.time())}.mp4"

    save_video(filename)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO videos (path, source, duration) VALUES (?, ?, ?)",
                   (filename, "webcam", 30))
    conn.commit()
    conn.close()

    return "Video saved"

# ======================
# 이벤트 영상 (전후 30초)
# ======================
def save_event_video():
    filename = f"static/videos/event_{int(time.time())}.mp4"

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, FPS, (640, 480))

    for frame in buffer:
        out.write(frame)

    for _ in range(FPS * 30):
        success, frame = camera.read()
        if not success:
            break
        out.write(frame)

    out.release()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO videos (path, source, duration) VALUES (?, ?, ?)",
                   (filename, "event", 60))
    conn.commit()
    conn.close()


# ======================
# 영상 목록 + 다운로드
# ======================
@app.route('/videos')
def videos():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM videos ORDER BY time DESC")
    data = cursor.fetchall()
    conn.close()
    return render_template('videos.html', data=data)


@app.route('/download/<int:id>')
def download(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT path FROM videos WHERE id=?", (id,))
    file = cursor.fetchone()
    conn.close()

    return send_file(file[0], as_attachment=True)
#로그 페이지
@app.route('/logs')
def logs():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM logs ORDER BY time DESC")
    data = cursor.fetchall()

    conn.close()
    return render_template('logs.html', data=data)
#로그 저장 함수
def save_log(action, detail):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO logs (action, detail)
    VALUES (?, ?)
    """, (action, detail))

    conn.commit()
    conn.close()

#터틀봇 위치 가져오기
@app.route('/update_location', methods=['POST'])
def update_location():
    global turtlebot_location
    turtlebot_location = request.json
    return "OK"

@app.route('/get_location')
def get_location():
    return turtlebot_location

#터틀봇 영상 실행
def gen_turtle():
    while True:
        success, frame = turtle_cam.read()
        if not success:
            break

        _, buffer_img = cv2.imencode('.jpg', frame)
        frame_bytes = buffer_img.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
@app.route('/turtle')
def turtle_page():
    return render_template('turtle.html')
        
#라우트
@app.route('/turtle_feed')
def turtle_feed():
    return Response(gen_turtle(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# ======================
# 실행
# ======================
if __name__ == '__main__':
    if not os.path.exists('static/videos'):
        os.makedirs('static/videos')

    app.run(debug=True)
