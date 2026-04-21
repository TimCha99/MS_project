import sqlite3

conn = sqlite3.connect('MS_database.db')
cursor = conn.cursor()

# ======================
# users (로그인)
# ======================
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

# ======================
# artifacts (전시품)
# ======================
cursor.execute("""
CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    location TEXT,
    price INTEGER,
    image TEXT,
    status TEXT DEFAULT 'normal'
)
""")

# ======================
# baseline (폐장 전 데이터)
# ======================
cursor.execute("""
CREATE TABLE IF NOT EXISTS baseline_objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id INTEGER,
    name TEXT,
    location TEXT,
    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================
# detected (폐장 후 감지)
# ======================
cursor.execute("""
CREATE TABLE IF NOT EXISTS detected_objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    location TEXT,
    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================
# detections (YOLO 원본 데이터)
# ======================
cursor.execute("""
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone TEXT,
    items TEXT,
    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================
# 영상
# ======================
cursor.execute("""
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT,
    source TEXT,
    duration INTEGER,
    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================
# 로그
# ======================
cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT,
    detail TEXT,
    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================
# 이벤트
# ======================
cursor.execute("""
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id INTEGER,
    location TEXT,
    event_type TEXT,
    status TEXT,
    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    before_video TEXT,
    after_video TEXT
)
""")

# ======================
# 터틀봇 위치 기록
# ======================
cursor.execute("""
CREATE TABLE IF NOT EXISTS robot_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    x REAL,
    y REAL,
    zone TEXT,
    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================
# 인덱스 (성능 최적화)
# ======================
cursor.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_location ON artifacts(location)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_time ON logs(time)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_time ON videos(time)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_time ON events(time)")

# ======================
# 기본 관리자 계정 생성 (없을 경우만)
# ======================
cursor.execute("SELECT * FROM users WHERE username='admin'")
if not cursor.fetchone():
    cursor.execute("""
    INSERT INTO users (username, password, role)
    VALUES ('admin', '1234', 'admin')
    """)

# ======================
# 커밋 & 종료
# ======================
conn.commit()
conn.close()

print("✅ DB 생성 및 확장 완료")