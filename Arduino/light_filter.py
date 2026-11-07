"""조도센서 값을 이동평균·지수이동평균으로 필터링하고, 어두우면 LED를 켠다 (Part D).

- 이동평균(MA): 최근 N개 값의 평균
- 지수이동평균(EMA): ema = alpha * 새값 + (1 - alpha) * 이전 ema
- 히스테리시스: EMA가 --dark보다 작아지면 LED ON, --bright보다 커지면 LED OFF

사용 예:
    python3 light_filter.py
    python3 light_filter.py --window 10 --alpha 0.2 --dark 300 --bright 400 --csv light.csv
종료: Ctrl+C
"""
import argparse
import csv
import sys
import time
from collections import deque

import serial

from led_blink_serial import find_arduino_port


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="예: /dev/ttyACM0 (생략하면 자동 탐색)")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--window", type=int, default=10, help="이동평균에 쓸 값의 개수")
    parser.add_argument("--alpha", type=float, default=0.2, help="지수이동평균 계수 (0~1, 작을수록 부드러움)")
    parser.add_argument("--dark", type=int, default=300, help="EMA가 이 값보다 작으면 LED ON")
    parser.add_argument("--bright", type=int, default=400, help="EMA가 이 값보다 크면 LED OFF")
    parser.add_argument("--csv", help="기록할 CSV 파일 이름 (생략하면 기록하지 않음)")
    args = parser.parse_args()

    port = args.port or find_arduino_port()
    if port is None:
        sys.exit("아두이노 포트를 찾지 못했습니다. `ls /dev/ttyACM* /dev/ttyUSB*`로 확인하세요.")
    print(f"포트: {port}, 속도: {args.baud}")

    buf = deque(maxlen=args.window)   # 최근 window개 값만 보관
    ema = None
    led_on = False

    f = open(args.csv, "w", newline="") if args.csv else None
    writer = csv.writer(f) if f else None
    if writer:
        writer.writerow(["time_s", "raw", "ma", "ema", "led"])

    with serial.Serial(port, args.baud, timeout=None) as ser:
        time.sleep(2)  # 포트를 열면 아두이노가 리셋되므로 부팅을 기다린다.
        ser.write(b"OFF\n")
        ser.write(b"STREAM ON\n")
        t0 = time.time()
        print(" raw     MA    EMA  LED")

        try:
            while True:
                line = ser.readline().decode(errors="ignore").strip()
                if not line.startswith("LIGHT "):
                    continue                     # READY, ACK, BTN ... 은 건너뛴다
                try:
                    raw = int(line.split()[1])
                except (IndexError, ValueError):
                    continue

                buf.append(raw)
                ma = sum(buf) / len(buf)
                ema = raw if ema is None else args.alpha * raw + (1 - args.alpha) * ema

                # 히스테리시스: 어두워지면 켜고, 충분히 밝아져야 끈다.
                if not led_on and ema < args.dark:
                    ser.write(b"ON\n")
                    led_on = True
                elif led_on and ema > args.bright:
                    ser.write(b"OFF\n")
                    led_on = False

                print(f"{raw:4d} {ma:6.1f} {ema:6.1f}  {'ON' if led_on else 'OFF'}")
                if writer:
                    writer.writerow([f"{time.time() - t0:.2f}", raw, f"{ma:.1f}", f"{ema:.1f}", int(led_on)])
        except KeyboardInterrupt:
            print("\n종료")
        finally:
            ser.write(b"STREAM OFF\n")
            ser.write(b"OFF\n")
            if f:
                f.close()
                print(f"기록 저장: {args.csv}")


if __name__ == "__main__":
    main()
