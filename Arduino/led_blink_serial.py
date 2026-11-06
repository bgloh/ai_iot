"""Jetson → Arduino 시리얼 통신으로 LED 점멸.

사용 예:
    python3 led_blink_serial.py                      # 포트 자동 탐색, 10회 점멸
    python3 led_blink_serial.py --port /dev/ttyACM0 --count 5 --interval 0.3
"""
import argparse
import sys
import time

import serial
from serial.tools import list_ports


def find_arduino_port():
    """ttyACM*(정품 Uno 등) 또는 ttyUSB*(CH340 호환보드) 포트를 찾는다."""
    for p in list_ports.comports():
        if "ttyACM" in p.device or "ttyUSB" in p.device:
            return p.device
    return None


def send(ser, cmd):
    """명령을 보내고 ACK/ERR 응답을 기다린다. 중간에 온 스위치 이벤트는 따로 출력한다."""
    ser.write((cmd + "\n").encode())
    while True:
        reply = ser.readline().decode(errors="ignore").strip()
        if not reply or reply.startswith(("ACK", "ERR")):
            break
        print(f"   (이벤트: {reply})")
    print(f"-> {cmd:<3} | <- {reply or '(응답 없음)'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="예: /dev/ttyACM0 (생략하면 자동 탐색)")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--count", type=int, default=10, help="점멸 횟수")
    parser.add_argument("--interval", type=float, default=0.5, help="켜짐/꺼짐 유지 시간(초)")
    args = parser.parse_args()

    port = args.port or find_arduino_port()
    if port is None:
        sys.exit("아두이노 포트를 찾지 못했습니다. `ls /dev/ttyACM* /dev/ttyUSB*`로 확인하세요.")
    print(f"포트: {port}, 속도: {args.baud}")

    with serial.Serial(port, args.baud, timeout=2) as ser:
        # 포트를 열면 아두이노가 리셋되므로 부팅을 기다린다.
        time.sleep(2)
        print("아두이노:", ser.readline().decode(errors="ignore").strip() or "(READY 없음)")

        try:
            for i in range(args.count):
                print(f"[{i + 1}/{args.count}]")
                send(ser, "ON")
                time.sleep(args.interval)
                send(ser, "OFF")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n중단됨")
        finally:
            send(ser, "OFF")


if __name__ == "__main__":
    main()
