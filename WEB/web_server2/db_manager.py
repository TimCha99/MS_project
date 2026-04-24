import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'database/ms_database.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 관리자(admins) 테이블 (기존 유지)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            emp_id TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            username TEXT NOT NULL,
            phone TEXT NOT NULL
        )
    ''')

    # 2. [추가] 로그(logs) 테이블 생성
    # 파라미터($COLUMNS$): id, event, timestamp, severity
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            severity TEXT NOT NULL
        )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS web_items (
        art_id TEXT PRIMARY KEY,
        art_name TEXT NOT NULL,
        location TEXT NOT NULL,
        price TEXT NOT NULL,
        status TEXT DEFAULT '정상',
        image_path TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS turtle_items (
        art_id TEXT PRIMARY KEY,
        art_name TEXT NOT NULL,
        location TEXT NOT NULL,
        price TEXT NOT NULL,
        status TEXT DEFAULT '정상',
        image_path TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS detected_items (
        art_id TEXT PRIMARY KEY,
        art_name TEXT NOT NULL
    )
    ''')
   
    conn.commit()
    conn.close()
    print("데이터베이스 최적화 완료: admins 및 logs 테이블이 준비되었습니다.")
    

if __name__ == "__main__":
    init_db()
