import cv2
import requests
import time

# 서버 주소 (본인 서버 IP로 수정하세요)
SERVER_URL = "http://192.168.108.60:5000/upload"
CAM_ID = "robot8_cam2"

# 노트북 기본 캠 열기
cap = cv2.VideoCapture(0)
# 카메라 하드웨어 자체의 캡처 해상도를 관제용(VGA)으로 강제 고정합니다.
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

print(f"[{CAM_ID}] 스트리밍 시작... (종료하려면 'q'를 누르세요)")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # 1. 이미지 크기 조절 (네트워크 부하 감소)
        frame = cv2.resize(frame, (640, 480))

        # 2. JPEG로 압축
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        
        # 3. 서버로 전송 (POST 요청)
        files = {'file': buffer.tobytes()}
        data = {'cam_id': CAM_ID}
        
        try:
            response = requests.post(SERVER_URL, files=files, data=data)
            # print(f"전송 상태: {response.json()}") # 상태 확인용
        except Exception as e:
            print(f"전송 에러: {e}")

        # 키보드 'q' 누르면 종료
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
        # 전송 주기 조절 (0.05초 = 약 20fps)
        time.sleep(0.08)

except KeyboardInterrupt:
    pass

cap.release()
cv2.destroyAllWindows()