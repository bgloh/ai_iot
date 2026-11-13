"""Part C 전에 Arduino 연결과 스케치(Part C~E 확장판)를 확인한다.

정상 출력:
    READY
    LIGHT -> LIGHT 467
    SERVO 90 -> ACK SERVO 90
'LIGHT -> ERR LIGHT'이면 LED만 다루는 예전 스케치이므로 led_serial.ino를 다시 업로드한다.

사용 예:
    python3 check_arduino.py                  # /dev/ttyACM0
    python3 check_arduino.py /dev/ttyUSB0
"""
import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
s = serial.Serial(port, 9600, timeout=2)
time.sleep(2)  # 포트를 열면 Arduino가 리셋되므로 부팅을 기다린다
print(s.readline().decode(errors="ignore").strip() or "(READY 없음)")
for c in ["LIGHT", "SERVO 90"]:
    s.write((c + "\n").encode())
    print(c, "->", s.readline().decode(errors="ignore").strip() or "(응답 없음)")
