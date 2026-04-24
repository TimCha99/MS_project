import requests
import time

url = "http://192.168.108.66:5000/api/external_alert"

while True:
    data = {
        "art_id": "123456",   # DB에 있는 ID로 바꿔야 함
        "cam_id": "cam1"
    }

    print("🚨 테스트 전송:", data)

    try:
        res = requests.post(url, json=data)
        print("응답:", res.json())
        requests.post("http://192.168.108.66:5000/api/external_alert", json={
            "art_id": "123456",
            "cam_id": "cam1"
        })
    except Exception as e:
        print("에러:", e)

    time.sleep(5)