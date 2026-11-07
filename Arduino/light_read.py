"""조도센서(A0) 값을 시리얼로 받아 숫자와 막대그래프로 표시 (Part C).

Arduino에 STREAM ON을 보내면 0.1초마다 "LIGHT <0~1023>"이 온다.

사용 예:
    python3 light_read.py
    python3 light_read.py --port /dev/ttyACM0
종료: Ctrl+C
"""
import argparse
import sys
import time

import serial

from led_blink_serial import find_arduino_port


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="예: /dev/ttyACM0 (생략하면 자동 탐색)")
    parser.add_argument("--baud", type=int, default=9600)
    args = parser.parse_args()

    port = args.port or find_arduino_port()
    if port is None:
        sys.exit("아두이노 포트를 찾지 못했습니다. `ls /dev/ttyACM* /dev/ttyUSB*`로 확인하세요.")
    print(f"포트: {port}, 속도: {args.baud}")

    with serial.Serial(port, args.baud, timeout=None) as ser:
        time.sleep(2)  # 포트를 열면 아두이노가 리셋되므로 부팅을 기다린다.
        ser.write(b"STREAM ON\n")
        print("  값   전압  밝기 (손으로 가리거나 빛을 비춰 보세요. 종료: Ctrl+C)")

        try:
            while True:
                line = ser.readline().decode(errors="ignore").strip()
                if not line.startswith("LIGHT "):
                    print(f"<- {line}")          # READY, ACK, BTN ... 은 그대로 출력
                    continue
                try:
                    raw = int(line.split()[1])   # "LIGHT 523" → 523
                except (IndexError, ValueError):
                    continue                     # 깨진 줄은 건너뛴다
                volt = raw * 5.0 / 1023          # 0~1023 → 0~5V
                bar = "#" * (raw // 25)          # 최대 40칸
                print(f"{raw:4d}  {volt:4.2f}V  {bar}")
        except KeyboardInterrupt:
            print("\n종료")
        finally:
            ser.write(b"STREAM OFF\n")           # 종료할 때 전송을 멈춘다.


if __name__ == "__main__":
    main()
