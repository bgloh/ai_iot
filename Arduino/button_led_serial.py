"""Arduino 스위치(D6) 이벤트를 받아 LED(D7)를 제어.

스위치를 누르면 Arduino가 "BTN PRESSED"를 보내고, Jetson이 "ON" 명령으로 LED를 켠다.
스위치를 떼면 "BTN RELEASED"를 받고 "OFF" 명령으로 LED를 끈다.

사용 예:
    python3 button_led_serial.py
    python3 button_led_serial.py --port /dev/ttyACM0
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

    # timeout=None: 한 줄이 완성될 때까지 기다린다 (Ctrl+C로 종료).
    with serial.Serial(port, args.baud, timeout=None) as ser:
        time.sleep(2)  # 포트를 열면 아두이노가 리셋되므로 부팅을 기다린다.
        print("스위치를 누르면 LED가 켜집니다. 종료: Ctrl+C")

        try:
            while True:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                print(f"<- {line}")

                if line == "BTN PRESSED":
                    ser.write(b"ON\n")
                    print("-> ON")
                elif line == "BTN RELEASED":
                    ser.write(b"OFF\n")
                    print("-> OFF")
        except KeyboardInterrupt:
            print("\n종료")
        finally:
            ser.write(b"OFF\n")  # 종료할 때 LED를 끈다.


if __name__ == "__main__":
    main()
