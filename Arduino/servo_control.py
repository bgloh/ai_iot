"""Jetson → Arduino 시리얼 명령으로 서보모터(D9) 각도를 제어 (Part E).

사용 예:
    python3 servo_control.py              # 각도를 입력해서 이동
    python3 servo_control.py --sweep      # 0도 → 180도 → 0도 왕복
    python3 servo_control.py --sweep --step 30
종료: q 또는 Ctrl+C
"""
import argparse
import sys
import time

import serial

from led_blink_serial import find_arduino_port, send


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="예: /dev/ttyACM0 (생략하면 자동 탐색)")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--sweep", action="store_true", help="0~180도를 자동으로 왕복")
    parser.add_argument("--step", type=int, default=10, help="sweep 각도 간격(도)")
    args = parser.parse_args()

    port = args.port or find_arduino_port()
    if port is None:
        sys.exit("아두이노 포트를 찾지 못했습니다. `ls /dev/ttyACM* /dev/ttyUSB*`로 확인하세요.")
    print(f"포트: {port}, 속도: {args.baud}")

    with serial.Serial(port, args.baud, timeout=2) as ser:
        time.sleep(2)  # 포트를 열면 아두이노가 리셋되므로 부팅을 기다린다.
        print("아두이노:", ser.readline().decode(errors="ignore").strip() or "(READY 없음)")

        try:
            if args.sweep:
                angles = list(range(0, 181, args.step)) + list(range(180 - args.step, -1, -args.step))
                for deg in angles:
                    send(ser, f"SERVO {deg}")
                    time.sleep(0.2)              # 서보가 움직일 시간을 준다.
            else:
                while True:
                    text = input("각도 0~180 (q: 종료) > ").strip()
                    if text.lower() == "q":
                        break
                    if not text.isdigit() or int(text) > 180:
                        print("   0~180 사이의 숫자를 입력하세요")
                        continue
                    send(ser, f"SERVO {int(text)}")
        except (KeyboardInterrupt, EOFError):
            print("\n중단됨")
        finally:
            send(ser, "SERVO 90")                # 가운데로 돌려놓고 끝낸다.


if __name__ == "__main__":
    main()
