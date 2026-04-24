import cv2
import requests
import time
import datetime

# 🚨 송근님의 실제 Flask 서버 IP로 반드시 변경해 주세요! (포트 5000번)
SERVER_URL = "http://192.168.108.60:5000/upload"

# 송근님이 요청하신 터틀봇4 타겟 ID! (서버의 VALID_CAM_IDS와 정확히 일치함)
CAM_ID = "cam1" 

# 노트북 웹캠 켜기 (0번 기본 캠)
cap = cv2.VideoCapture(0)

# OAK-D 카메라 느낌을 위해 초기 캡처는 고해상도(1080p)로 세팅 시도
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

print(f"🚀 [{CAM_ID}] OAK-D 카메라 시뮬레이터를 가동합니다...")
print(f"📡 타겟 서버: {SERVER_URL}")
print("⏹️ 종료하려면 영상 창을 선택하고 'q' 키를 누르세요.")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ 웹캠에서 영상을 읽어올 수 없습니다.")
            break

        # [1] 관제 서버 규격에 맞게 리사이징 (OAK-D ROS 노드의 역할 시뮬레이션)
        # 서버 부하를 막기 위해 640x480(VGA) 사이즈로 압축합니다.
        frame = cv2.resize(frame, (640, 480))

        # [2] 🎨 찐 로봇 느낌을 내는 HUD(상태 표시) 오버레이 합성!
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cv2.putText(frame, f"OAK-D-LITE | {CAM_ID}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"SYS TIME: {now}", (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        cv2.putText(frame, "STATUS: NAV2 ACTIVE", (15, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # [3] JPEG 인코딩
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        
        # [4] 서버로 POST 전송
        files = {'file': buffer.tobytes()}
        data = {'cam_id': CAM_ID}
        
        try:
            # timeout을 짧게 주어 서버가 느려도 전송 스크립트가 멈추지 않게 방어
            requests.post(SERVER_URL, files=files, data=data, timeout=0.5)
        except requests.exceptions.RequestException:
            # 네트워크가 끊겨도 에러를 뿜고 죽지 않도록 조용히 무시 (로봇의 내결함성)
            pass 

        # 송근님 노트북 화면에서도 전송되는 영상 확인
        cv2.imshow("TurtleBot4 OAK-D Simulator", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
        # OAK-D의 일반적인 ROS 스트리밍 속도인 30FPS(약 0.033초)에 맞춤
        time.sleep(0.033) 

except KeyboardInterrupt:
    print("\n🛑 사용자에 의해 시뮬레이터가 종료되었습니다.")
finally:
    cap.release()
    cv2.destroyAllWindows()