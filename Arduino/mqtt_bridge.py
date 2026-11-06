"""Arduino(시리얼) ↔ HiveMQ public broker(MQTT) 브리지.

Arduino 스케치는 Serial 통신 Lab.1의 led_serial.ino를 그대로 사용한다.

토픽 (<id>는 --id로 지정한 팀/학번):
    aiot-hs/<id>/switch      Jetson → 앱   "PRESSED" / "RELEASED"     스위치 이벤트
    aiot-hs/<id>/led/state   Jetson → 앱   "ON" / "OFF"  (retained)   LED 현재 상태
    aiot-hs/<id>/led/set     앱 → Jetson   "ON" / "OFF" / "TOGGLE"    LED 제어 명령
    aiot-hs/<id>/status      Jetson → 앱   "online" / "offline" (retained, LWT)

사용 예:
    python3 mqtt_bridge.py --id team01
종료: Ctrl+C
"""
import argparse
import sys
import threading
import time
import uuid

import paho.mqtt.client as mqtt
import serial

from led_blink_serial import find_arduino_port


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="토픽에 들어갈 팀/학번 (다른 팀과 겹치지 않게)")
    parser.add_argument("--broker", default="broker.hivemq.com")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--port", help="시리얼 포트 (생략하면 자동 탐색)")
    parser.add_argument("--baud", type=int, default=9600)
    args = parser.parse_args()

    base = f"aiot-hs/{args.id}"
    t_switch = f"{base}/switch"
    t_led_state = f"{base}/led/state"
    t_led_set = f"{base}/led/set"
    t_status = f"{base}/status"

    # ---------------- 시리얼 연결 ----------------
    port = args.port or find_arduino_port()
    if port is None:
        sys.exit("아두이노 포트를 찾지 못했습니다. `ls /dev/ttyACM* /dev/ttyUSB*`로 확인하세요.")
    ser = serial.Serial(port, args.baud, timeout=None)
    time.sleep(2)  # 포트를 열면 아두이노가 리셋되므로 부팅을 기다린다.
    print(f"[serial] {port} 연결")

    write_lock = threading.Lock()  # MQTT 스레드와 메인 스레드가 동시에 쓰지 않도록
    led = {"on": False}            # ACK로 확인된 LED 상태

    def send_cmd(cmd):
        with write_lock:
            ser.write((cmd + "\n").encode())
        print(f"[serial] -> {cmd}")

    # ---------------- MQTT 연결 ----------------
    connected = threading.Event()

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[mqtt] 연결 실패: {reason_code}")
            return
        print(f"[mqtt] {args.broker}:{args.mqtt_port} 연결")
        client.subscribe(t_led_set, qos=1)
        client.publish(t_status, "online", qos=1, retain=True)
        print(f"[mqtt] 구독: {t_led_set}")
        connected.set()

    def on_message(client, userdata, msg):
        payload = msg.payload.decode(errors="ignore").strip().upper()
        print(f"[mqtt] <- {msg.topic}: {payload}")
        if payload in ("ON", "OFF"):
            send_cmd(payload)
        elif payload == "TOGGLE":
            send_cmd("OFF" if led["on"] else "ON")
        else:
            print("[mqtt]    알 수 없는 명령입니다 (ON / OFF / TOGGLE)")

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"jetson-{args.id}-{uuid.uuid4().hex[:6]}",
    )
    # 비정상 종료(전원 차단, 네트워크 끊김) 시 broker가 대신 "offline"을 발행한다.
    client.will_set(t_status, "offline", qos=1, retain=True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.broker, args.mqtt_port, keepalive=30)
    client.loop_start()  # MQTT 송수신은 별도 스레드에서 처리

    if not connected.wait(timeout=10):
        ser.close()
        sys.exit("[mqtt] broker에 연결하지 못했습니다. 네트워크와 --broker 주소를 확인하세요.")

    send_cmd("OFF")  # 시작 상태를 OFF로 맞추고 앱에 알린다.
    print(f"앱에서 '{base}/#' 를 구독하세요. 종료: Ctrl+C")

    # ---------------- 시리얼 수신 루프 ----------------
    try:
        while True:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue
            print(f"[serial] <- {line}")

            if line == "BTN PRESSED":
                client.publish(t_switch, "PRESSED", qos=1)
                send_cmd("OFF" if led["on"] else "ON")  # 스위치를 누를 때마다 토글
            elif line == "BTN RELEASED":
                client.publish(t_switch, "RELEASED", qos=1)
            elif line in ("ACK ON", "ACK OFF"):
                state = line.split()[1]
                led["on"] = state == "ON"
                client.publish(t_led_state, state, qos=1, retain=True)
                print(f"[mqtt] -> {t_led_state}: {state}")
    except KeyboardInterrupt:
        print("\n종료")
    finally:
        send_cmd("OFF")
        client.publish(t_led_state, "OFF", qos=1, retain=True)
        client.publish(t_status, "offline", qos=1, retain=True).wait_for_publish(timeout=3)
        client.loop_stop()
        client.disconnect()
        ser.close()


if __name__ == "__main__":
    main()
