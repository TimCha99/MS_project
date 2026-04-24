import rclpy
from rclpy.node import Node
from sensor_msgs.msg import BatteryState
import requests
import json

class RobotStatusPusher(Node):
    def __init__(self):
        super().__init__('robot_status_pusher')
        
        # --- 설정 파라미터 (Parameters) ---
        self.robot_id = 'TURTLEBOT_02'  # 로봇 식별 ID
        self.flask_url = 'http://192.168.108.60:5000/api/robot_status' # 서버 주소
        self.update_interval = 2.0  # 전송 주기 (초)
        
        # 배터리 상태 구독
        self.subscription = self.create_subscription(
            BatteryState,
            '/robot8/battery_state',
            self.battery_callback,
            10
        )
        
        # 최신 배터리 값 저장 변수
        self.current_battery_percent = 0.0
        
        # 주기적 전송을 위한 타이머
        self.timer = self.create_timer(self.update_interval, self.send_to_server)
        self.get_logger().info(f'{self.robot_id} 상태 전송 노드가 시작되었습니다.')

    def battery_callback(self, msg):
        """배터리 토픽이 수신될 때마다 값을 업데이트 (0.0 ~ 1.0 -> 0 ~ 100)"""
        self.current_battery_percent = round(msg.percentage * 100, 1)

    def send_to_server(self):
        """Flask 서버로 데이터 POST 전송"""
        payload = {
            'robot_id': self.robot_id,
            'battery': self.current_battery_percent,
            'status': 'CONNECTED'
        }
        
        try:
            # 1초 타임아웃 설정으로 로봇 루프 지연 방지
            response = requests.post(self.flask_url, json=payload, timeout=1.0)
            if response.status_code == 200:
                self.get_logger().info(f'전송 성공: {self.current_battery_percent}%')
            else:
                self.get_logger().error(f'서버 응답 에러: {response.status_code}')
        except requests.exceptions.RequestException as e:
            self.get_logger().error(f'서버 연결 실패: {e}')

def main(args=None):
    rclpy.init(args=args)
    node = RobotStatusPusher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()