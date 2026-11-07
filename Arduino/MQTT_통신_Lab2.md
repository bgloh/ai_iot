# MQTT 통신 Lab.2 — HiveMQ Public Broker로 스위치·LED 원격 모니터링과 제어

## 1. 실험 목적

본 실험의 목적은 [Serial 통신 Lab.1](Serial_통신_Lab1.md)에서 만든 Jetson ↔ Arduino 시스템을 **인터넷에 연결**하는 것이다. Jetson이 시리얼 통신과 MQTT 통신을 이어 주는 **브리지(bridge)** 역할을 하여, 스마트폰이나 PC의 MQTT 클라이언트 앱에서 다음을 할 수 있게 한다.

- 스위치 입력(누름/뗌)을 앱에서 **실시간으로 확인**
- LED의 현재 상태(ON/OFF)를 앱에서 **확인**
- 앱에서 명령을 **전송**해 LED를 켜고 끄기

이 실험을 통해 다음을 익힌다.

- MQTT의 기본 개념: broker, publish / subscribe, topic, wildcard, QoS
- retained 메시지와 LWT(Last Will and Testament)를 이용한 장치 상태 관리
- paho-mqtt를 이용한 Python MQTT 클라이언트 작성
- 시리얼(로컬)과 MQTT(인터넷)를 연결하는 IoT 게이트웨이 구조

전체 구조는 다음과 같다.

```text
 ┌──────────┐  USB 시리얼   ┌──────────────────┐   MQTT (인터넷)   ┌─────────────────────┐   MQTT   ┌──────────────┐
 │ Arduino  │ ◄──────────► │ Jetson           │ ◄──────────────► │ HiveMQ Public Broker│ ◄──────► │ MQTT 클라이언트 앱 │
 │ D6 스위치 │  "BTN ..."   │ mqtt_bridge.py   │  publish /       │ broker.hivemq.com   │          │ (스마트폰 / PC)  │
 │ D7 LED   │  "ON"/"OFF"  │ (시리얼↔MQTT 변환) │  subscribe       │                     │          │              │
 └──────────┘              └──────────────────┘                  └─────────────────────┘          └──────────────┘
```

---

# 2. 실험 환경

```text
Device: NVIDIA Jetson Orin Nano Developer Kit Super
JetPack: 6.2 (L4T R36.4.3), Ubuntu 22.04.5 LTS
Python: 3.10
pyserial: 3.5
paho-mqtt: 2.2.0
MQTT Broker: HiveMQ Public Broker (broker.hivemq.com)
Microcontroller: Arduino Uno R3
  - D7: LED (220Ω 저항 직렬)
  - D6: 푸시 스위치 (외부 10kΩ 풀업, 누르면 LOW)
MQTT 클라이언트 앱: HiveMQ WebSocket Client(브라우저), MQTTX(PC), IoT MQTT Panel(스마트폰) 중 선택
```

**사전 조건:** Serial 통신 Lab.1을 끝까지 수행해 다음이 되어 있어야 한다.

- [ ] Arduino에 `led_serial.ino`가 업로드되어 있다 (Lab.1 8~9장). **이번 Lab에서 스케치는 수정하지 않는다.**
- [ ] `python3 button_led_serial.py`로 스위치를 누르면 LED가 켜진다 (Lab.1 13장).
- [ ] `~/Arduino` 폴더에 `led_blink_serial.py`가 있다 (포트 탐색 함수를 가져다 쓴다).
- [ ] Jetson이 인터넷에 연결되어 있다.

---

# 3. 배경 지식

## 3.1 MQTT란?

MQTT(Message Queuing Telemetry Transport)는 IoT 장치를 위해 만든 **가볍고 단순한 메시지 통신 프로토콜**이다. TCP/IP 위에서 동작하며, 센서·스마트홈·산업 장비 등에서 널리 쓰인다.

Lab.1의 시리얼 통신은 **두 장치가 케이블로 직접(1:1)** 연결되었다. MQTT는 중간에 **broker(중개 서버)** 를 두고 여러 장치가 **인터넷을 통해(N:N)** 메시지를 주고받는다.

| 구분 | Serial (Lab.1) | MQTT (Lab.2) |
|---|---|---|
| 연결 | USB 케이블, 1:1 | 인터넷, N:N |
| 거리 | 수 m | 제한 없음 |
| 상대 지정 | 케이블이 연결된 장치 | **topic** (주제) 이름 |
| 메시지 구분 | 줄바꿈(`\n`) | 프로토콜이 메시지 단위로 전달 |
| 중개자 | 없음 | broker |

## 3.2 Publish / Subscribe 모델

MQTT의 장치들은 서로를 직접 알지 못한다. 모두 broker에만 연결하고, **topic**을 기준으로 메시지를 주고받는다.

```text
           publish                         subscribe
 Jetson ──────────────►  ┌────────┐  ◄──────────────── 앱
 "aiot-hs/team01/        │ Broker │   "aiot-hs/team01/#"
  led/state = ON"        └────────┘
                             │
                             └──── 구독자에게 전달 ────► 앱: "led/state = ON" 수신
```

| 용어 | 의미 |
|---|---|
| **Broker** | 메시지를 받아 해당 topic의 구독자에게 전달하는 서버. 본 실험은 `broker.hivemq.com` |
| **Client** | broker에 연결하는 모든 장치/프로그램. Jetson 브리지, 스마트폰 앱 모두 client |
| **Publish** | 특정 topic으로 메시지를 보내는 것 |
| **Subscribe** | 특정 topic의 메시지를 받겠다고 broker에 등록하는 것 |
| **Topic** | 메시지의 주소. `/`로 계층을 나눈다. 예: `aiot-hs/team01/led/state` |
| **Payload** | 메시지 내용. 본 실험은 `ON`, `PRESSED` 같은 짧은 문자열 |

**발행자와 구독자는 서로를 몰라도 된다.** Jetson은 앱이 몇 개 연결됐는지 신경 쓰지 않고 publish만 하면 된다. 앱을 10개 띄우면 10개 모두 같은 메시지를 받는다.

## 3.3 Topic과 Wildcard

topic은 파일 경로처럼 `/`로 계층을 나눈다. 구독할 때는 wildcard를 쓸 수 있다.

| Wildcard | 의미 | 예 | 매칭되는 topic |
|---|---|---|---|
| `+` | 한 단계 | `aiot-hs/+/led/state` | `aiot-hs/team01/led/state`, `aiot-hs/team02/led/state` |
| `#` | 그 아래 전부 (맨 끝에만) | `aiot-hs/team01/#` | `aiot-hs/team01/switch`, `aiot-hs/team01/led/state`, `aiot-hs/team01/led/set`, ... |

## 3.4 QoS (Quality of Service)

| QoS | 이름 | 의미 |
|---|---|---|
| 0 | At most once | 한 번 보내고 끝. 유실될 수 있음 |
| 1 | At least once | 수신 확인(PUBACK)을 받을 때까지 재전송. **중복**될 수 있음 |
| 2 | Exactly once | 4단계 핸드셰이크로 정확히 한 번. 가장 느림 |

본 실험은 **QoS 1**을 사용한다. Lab.1의 `ACK`와 비슷하게, broker가 받았다는 확인을 받는다.

## 3.5 Retained 메시지

보통 MQTT 메시지는 **그 순간 구독 중인 client에게만** 전달된다. 앱을 나중에 켜면 이전 메시지를 받을 수 없다.

`retain=True`로 발행하면 broker가 그 topic의 **마지막 메시지를 저장**해 두었다가, 새로 구독하는 client에게 **즉시** 보내 준다.

```text
10:00  Jetson → led/state = ON   (retain)     broker가 "ON" 저장
10:05  앱 실행, led/state 구독                 → 즉시 "ON" 수신 (10:00 메시지)
```

- **LED 상태(`led/state`)** 처럼 "현재 값"이 중요한 정보는 retained로 보낸다 → 앱을 켜자마자 LED 상태를 안다.
- **스위치 이벤트(`switch`)** 처럼 "그 순간의 사건"은 retained로 보내지 않는다 → 앱을 켰는데 한참 전의 "PRESSED"가 오면 혼란스럽다.

## 3.6 LWT (Last Will and Testament, 유언 메시지)

Jetson의 전원이 갑자기 꺼지거나 네트워크가 끊기면 "나 꺼진다"는 메시지를 보낼 수 없다. LWT는 client가 **연결할 때 미리** broker에 맡겨 두는 메시지다. broker는 그 client가 **비정상적으로 끊긴 것을 감지하면** 대신 그 메시지를 발행한다.

```text
연결 시:   Jetson → broker  "내가 비정상 종료되면 status = offline 을 발행해 줘" (LWT 등록)
          Jetson → status = online (retain)
...
전원 차단: broker가 keepalive(30초 × 1.5) 동안 Jetson의 신호를 받지 못함
          broker → status = offline (retain)  ← Jetson 대신 발행
```

앱에서 `status`를 보면 Jetson이 살아 있는지 알 수 있다.

## 3.7 ⚠️ Public Broker 사용 시 주의

`broker.hivemq.com`은 HiveMQ가 테스트용으로 **누구에게나 무료로 공개**한 broker다. 편리하지만 다음에 주의해야 한다.

- **아이디·비밀번호가 없다.** topic 이름만 알면 **전 세계 누구나** 우리 메시지를 보고, 우리 LED에 명령을 보낼 수 있다.
- 따라서 **개인정보, 비밀번호, 중요한 데이터는 절대 보내지 않는다.**
- 다른 팀과 topic이 겹치지 않도록 **고유한 팀 ID**를 사용한다(4장).
- 실제 서비스에서는 인증(아이디/비밀번호, 인증서)과 TLS 암호화를 지원하는 **전용 broker**를 사용한다.
- 가용성이 보장되지 않는다. 가끔 느리거나 연결이 끊길 수 있다.

---

# 4. Topic 설계

모든 topic은 `aiot-hs/<팀ID>/`로 시작한다. **`<팀ID>`는 다른 팀과 겹치지 않게** 정한다(예: `team01`, 학번 `2026123456`).

> 아래 설명에서는 `<팀ID>`를 `team01`로 가정한다. 실습할 때는 **자기 팀 ID로 바꿔서** 입력한다.

| Topic | 방향 | Payload | Retain | 의미 |
|---|---|---|---|---|
| `aiot-hs/team01/switch` | Jetson → 앱 | `PRESSED` / `RELEASED` | ✗ | 스위치 이벤트 |
| `aiot-hs/team01/led/state` | Jetson → 앱 | `ON` / `OFF` | ✓ | LED 현재 상태 (Arduino ACK로 확인된 값) |
| `aiot-hs/team01/led/set` | 앱 → Jetson | `ON` / `OFF` / `TOGGLE` | ✗ | LED 제어 명령 |
| `aiot-hs/team01/status` | Jetson → 앱 | `online` / `offline` | ✓ | Jetson 브리지 동작 여부 (LWT) |

**동작 규칙**

| 사건 | Jetson의 동작 | 앱에서 보이는 메시지 |
|---|---|---|
| 브리지 시작 | broker 연결, LED를 OFF로 초기화 | `status = online`, `led/state = OFF` |
| 스위치 누름 | 스위치 이벤트 발행 + LED **토글** | `switch = PRESSED`, `led/state = ON` (또는 OFF) |
| 스위치 뗌 | 스위치 이벤트 발행 | `switch = RELEASED` |
| 앱이 `led/set = ON` 발행 | Arduino에 `ON` 전송 | `led/state = ON` |
| 앱이 `led/set = TOGGLE` 발행 | 현재 상태의 반대 명령 전송 | `led/state = ON` 또는 `OFF` |
| 브리지 정상 종료 (Ctrl+C) | LED OFF, 상태 발행 | `led/state = OFF`, `status = offline` |
| Jetson 전원 차단 / 네트워크 끊김 | (아무것도 못 함) | broker가 LWT 발행: `status = offline` |

> Lab.1 Part B에서는 스위치를 **누르는 동안만** LED가 켜졌다. Lab.2에서는 앱에서도 LED를 켤 수 있으므로, 스위치를 **누를 때마다 켜짐/꺼짐이 바뀌는(토글)** 방식으로 바꾸었다. 그래야 앱에서 켠 LED를 스위치로 끄거나, 그 반대도 할 수 있다.

> **`led/state`는 Arduino의 `ACK`를 받은 뒤에만 발행한다.** 명령을 보냈다고 LED가 켜졌다고 가정하지 않고, Arduino가 실제로 처리했다고 응답한 값만 앱에 알린다.

---

# 5. 준비

## 5.1 paho-mqtt 설치

paho-mqtt는 Eclipse 재단이 만든 Python MQTT client 라이브러리다.

```bash
pip3 install --user paho-mqtt
python3 -c "import paho.mqtt; print('paho-mqtt', paho.mqtt.__version__)"
```

```text
paho-mqtt 2.2.0
```

> paho-mqtt **2.x**는 1.x와 콜백 함수 형식이 다르다. 인터넷의 예제 코드 중 `mqtt.Client()`처럼 인자 없이 만드는 것은 1.x용이다. 본 실험 코드는 2.x 형식(`CallbackAPIVersion.VERSION2`)을 사용한다.

## 5.2 broker 연결 확인

Jetson에서 broker의 1883 포트에 접속할 수 있는지 확인한다.

```bash
timeout 5 bash -c "</dev/tcp/broker.hivemq.com/1883" && echo "broker 접속 가능"
```

```text
broker 접속 가능
```

아무것도 출력되지 않으면 네트워크(방화벽)가 1883 포트를 막고 있는 것이다(12장 참고).

## 5.3 시리얼 포트를 쓰는 다른 프로그램 종료

Lab.1의 `button_led_serial.py`나 `led_blink_serial.py`가 **다른 터미널에서 실행 중이면 반드시 종료**한다(`Ctrl+C`). 시리얼 포트는 한 프로그램만 사용할 수 있다.

```bash
fuser -v /dev/ttyACM0      # 아무것도 안 나오면 사용 중인 프로그램 없음
```

---

# 6. 브리지 프로그램 작성

VS Code에서 `~/Arduino/mqtt_bridge.py` 파일을 만들고 다음 코드를 입력한다. `led_blink_serial.py`와 **같은 폴더**에 있어야 한다.

```python
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
```

## 6.1 프로그램 구조 — 두 개의 스레드

브리지는 **두 곳에서 동시에** 메시지를 기다려야 한다. 시리얼(Arduino)과 MQTT(broker)다. 그래서 두 개의 스레드를 사용한다.

```text
┌───────────────────────── mqtt_bridge.py ─────────────────────────┐
│                                                                  │
│  메인 스레드                          MQTT 스레드 (loop_start)     │
│  ───────────                          ────────────────────────    │
│  ser.readline() 대기                   broker 메시지 대기           │
│    "BTN PRESSED" → publish(switch)      led/set 수신               │
│                  → send_cmd(토글)        → on_message()             │
│    "ACK ON"      → publish(led/state)     → send_cmd("ON")         │
│                                                                  │
│               send_cmd()는 write_lock으로 보호                     │
│               (두 스레드가 동시에 시리얼에 쓰지 않도록)                 │
└──────────────────────────────────────────────────────────────────┘
```

- **메인 스레드:** Lab.1과 같이 `ser.readline()`으로 Arduino 메시지를 기다린다.
- **MQTT 스레드:** `client.loop_start()`가 만든다. broker와의 통신(수신, keepalive, 재전송)을 백그라운드에서 처리하고, 메시지가 오면 `on_message()`를 호출한다.
- **`write_lock`:** 스위치 토글(메인 스레드)과 앱 명령(MQTT 스레드)이 **동시에** 시리얼에 쓰면 `ON\nOFF\n`이 섞여 `OONF...`처럼 깨질 수 있다. `threading.Lock`으로 한 번에 하나만 쓰게 한다.

## 6.2 주요 코드 설명

**MQTT client 생성 — `mqtt.Client(...)`**

| 코드 | 설명 |
|---|---|
| `CallbackAPIVersion.VERSION2` | paho-mqtt 2.x 콜백 형식 사용 |
| `client_id=f"jetson-{id}-{랜덤}"` | broker가 client를 구분하는 이름. **같은 ID로 두 client가 접속하면 먼저 접속한 쪽이 끊긴다.** 그래서 랜덤 문자를 붙인다 |
| `will_set(t_status, "offline", retain=True)` | LWT 등록 (3.6절). **`connect()`보다 먼저** 호출해야 한다 |
| `connect(broker, 1883, keepalive=30)` | broker에 TCP 연결. 30초마다 살아 있다는 신호(PINGREQ)를 보냄 |
| `loop_start()` | MQTT 스레드 시작 |

**연결 콜백 — `on_connect()`**

broker 연결이 끝나면 호출된다. 여기서 구독(`subscribe`)과 `online` 발행을 한다.

> 구독을 `on_connect()` 안에서 하는 이유: 네트워크가 끊겼다가 **자동 재연결**되면 `on_connect()`가 다시 호출되어 구독도 다시 등록된다. `connect()` 직후에 한 번만 구독하면 재연결 후 명령을 받지 못한다.

**`connected.wait(timeout=10)`**

`connect()`는 연결을 **시작**만 하고 바로 돌아온다. 실제 연결은 MQTT 스레드에서 끝난다. `threading.Event`로 `on_connect()`가 호출될 때까지 최대 10초를 기다린 뒤 다음 단계로 넘어간다.

**메시지 콜백 — `on_message()`**

`led/set`으로 메시지가 오면 호출된다. `.upper()`로 대문자로 바꾸므로 앱에서 `on`, `On`을 보내도 동작한다.

**발행 — `client.publish(topic, payload, qos=1, retain=...)`**

| 발행 | retain | 이유 |
|---|---|---|
| `switch` | ✗ | 순간 이벤트 |
| `led/state` | ✓ | 현재 상태. 앱을 나중에 켜도 바로 알 수 있게 |
| `status` | ✓ | 현재 상태 |

**정상 종료 — `finally`**

`Ctrl+C`로 종료하면 LED를 끄고 `led/state = OFF`, `status = offline`을 발행한다. `wait_for_publish()`로 마지막 메시지가 broker에 도착할 때까지 기다린 뒤 연결을 끊는다.

---

# 7. 브리지 실행

**팀 ID를 정해서** 실행한다(아래는 `team01`).

```bash
cd ~/Arduino
python3 mqtt_bridge.py --id team01
```

실행 결과:

```text
[serial] /dev/ttyACM0 연결
[mqtt] broker.hivemq.com:1883 연결
[mqtt] 구독: aiot-hs/team01/led/set
[serial] -> OFF
앱에서 'aiot-hs/team01/#' 를 구독하세요. 종료: Ctrl+C
[serial] <- READY
[serial] <- ACK OFF
[mqtt] -> aiot-hs/team01/led/state: OFF
```

이 상태에서 브리지를 **켜 둔 채로** 8장의 앱을 설정한다.

---

# 8. MQTT 클라이언트 앱 설정

다음 세 가지 중 **하나 이상**을 선택한다. 모두 무료다. 어떤 앱이든 다음 세 가지만 설정하면 된다.

| 설정 | 값 |
|---|---|
| Broker 주소 | `broker.hivemq.com` |
| 포트 | 앱 종류에 따라 다름 (아래 표) |
| 구독 topic | `aiot-hs/team01/#` |
| 명령 발행 topic | `aiot-hs/team01/led/set` |

HiveMQ public broker가 제공하는 포트:

| 포트 | 프로토콜 | 사용하는 곳 |
|---|---|---|
| 1883 | MQTT (TCP) | Jetson 브리지, MQTTX, 스마트폰 앱 |
| 8883 | MQTT over TLS | 암호화가 필요할 때 |
| 8000 | WebSocket | 브라우저 |
| 8884 | WebSocket over TLS | 브라우저 (HiveMQ WebSocket Client 기본값) |

> 앱의 화면과 메뉴 이름은 버전에 따라 조금 다를 수 있다. 위 설정 값만 맞으면 된다.

## 8.1 방법 A — HiveMQ WebSocket Client (브라우저, 설치 불필요)

PC나 스마트폰 브라우저에서 바로 사용할 수 있다.

1. 브라우저에서 <https://www.hivemq.com/demos/websocket-client/> 에 접속한다.
2. **Connection** 영역에서 다음을 입력하고 **Connect**를 누른다.

   | 항목 | 값 |
   |---|---|
   | Host | `mqtt-dashboard.com` (기본값 그대로) |
   | Port | `8884` (기본값 그대로) |
   | ClientID | 자동 생성된 값 그대로 |
   | Username / Password | 비워 둠 |
   | Keep Alive | `60` (기본값 그대로) |
   | SSL | ✓ (기본값 그대로) |
   | Clean Session | ✓ (기본값 그대로) |
   | Last-Will 항목들 | 비워 둠 |

   > `mqtt-dashboard.com`은 `broker.hivemq.com`과 **같은 HiveMQ public broker**의 다른 이름이다. Jetson 브리지가 `broker.hivemq.com`에 발행한 메시지를 웹 클라이언트에서 그대로 받을 수 있다.

   연결되면 Connection 제목 옆의 **빨간 점이 초록색**으로 바뀌고, 입력 영역이 접힌다.
3. **Subscriptions** 영역에서 **Add New Topic Subscription**을 누르고 topic에 `aiot-hs/team01/#`, QoS `1`을 입력한 뒤 **Subscribe**를 누른다.
4. **Messages** 영역에 retained 메시지가 바로 나타난다.
   ```text
   aiot-hs/team01/status      online
   aiot-hs/team01/led/state   OFF
   ```
5. **Publish** 영역에서 Topic에 `aiot-hs/team01/led/set`, Message에 `ON`을 입력하고 **Publish**를 누른다.
   → LED가 켜지고, Messages에 `led/state  ON`이 나타난다.

## 8.2 방법 B — MQTTX (PC 앱)

MQTTX는 EMQ가 만든 무료 MQTT 클라이언트로 Windows / macOS / Linux를 지원한다.

1. <https://mqttx.app> 에서 설치한다. (설치 없이 쓰려면 같은 사이트의 **Web 버전**을 사용한다. 이때는 포트 `8884`, `wss://` 를 선택한다.)
2. 왼쪽의 **+ (New Connection)** 을 누르고 다음을 입력한 뒤 **Connect**를 누른다.

   | 항목 | 값 |
   |---|---|
   | Name | `aiot-team01` (아무 이름) |
   | Host | `mqtt://` `broker.hivemq.com` |
   | Port | `1883` |
   | Client ID | 자동 생성된 값 그대로 |
   | Username / Password | 비워 둠 |

3. **+ New Subscription**을 누르고 Topic `aiot-hs/team01/#`, QoS `1`로 구독한다.
4. 화면 아래 입력창에서
   - Payload 형식을 **Plaintext**로 선택한다.
   - Topic에 `aiot-hs/team01/led/set`을 입력한다.
   - 내용에 `TOGGLE`을 입력하고 **전송(▶)** 버튼을 누른다.
5. 수신 메시지는 왼쪽(받은 메시지), 보낸 메시지는 오른쪽 말풍선으로 표시된다.

## 8.3 방법 C — IoT MQTT Panel (스마트폰 앱, 대시보드)

IoT MQTT Panel은 Android / iOS용 앱으로, 버튼·표시등 같은 **대시보드 위젯**을 만들 수 있다. 스마트폰을 리모컨처럼 사용할 수 있다.

1. Google Play 또는 App Store에서 **IoT MQTT Panel**을 설치한다.
2. **Connection 추가**

   | 항목 | 값 |
   |---|---|
   | Connection name | `aiot-team01` |
   | Broker Web/IP address | `broker.hivemq.com` |
   | Port number | `1883` |
   | Network protocol | `TCP` |
   | Client ID | 자동 생성된 값 그대로 |

3. **Dashboard 추가** (이름: `LED`)
4. 다음 **Panel(위젯)** 들을 추가한다.

   | Panel 종류 | 이름 | Topic | 설정 |
   |---|---|---|---|
   | **LED Indicator** | LED 상태 | `aiot-hs/team01/led/state` | Payload on: `ON`, Payload off: `OFF` |
   | **Switch** | LED 제어 | 발행: `aiot-hs/team01/led/set` | Payload on: `ON`, Payload off: `OFF` |
   | **Button** | 토글 | `aiot-hs/team01/led/set` | Payload: `TOGGLE` |
   | **Text Log** | 스위치 기록 | `aiot-hs/team01/switch` | 수신 메시지 목록 표시 |
   | **LED Indicator** | Jetson 연결 | `aiot-hs/team01/status` | Payload on: `online`, Payload off: `offline` |

   > Switch 패널에 **구독 topic**을 따로 지정할 수 있으면 `aiot-hs/team01/led/state`로 설정한다. 그러면 하드웨어 스위치로 LED를 바꿨을 때 앱의 스위치 표시도 함께 바뀐다.

5. 대시보드에서 **Switch**를 켜면 LED가 켜지고, **LED 상태** 표시등이 초록색으로 바뀐다.

---

# 9. 실험 시나리오

브리지를 실행하고 앱에서 `aiot-hs/team01/#`을 구독한 상태에서 다음을 차례로 수행하고, 앱과 Jetson 터미널의 메시지를 기록한다.

| 단계 | 할 일 | 확인할 것 |
|---|---|---|
| ① | 앱에서 구독 | retained `status = online`, `led/state = OFF`가 **바로** 오는가? |
| ② | 앱에서 `led/set` = `ON` 발행 | LED가 켜지고 `led/state = ON`이 오는가? |
| ③ | 앱에서 `led/set` = `OFF` 발행 | LED가 꺼지는가? |
| ④ | 앱에서 `led/set` = `TOGGLE` 두 번 발행 | 켜짐 → 꺼짐으로 바뀌는가? |
| ⑤ | 하드웨어 스위치를 누른다 | `switch = PRESSED`, `led/state = ON`이 오고 LED가 켜지는가? |
| ⑥ | 스위치를 뗀다 | `switch = RELEASED`가 오고 LED는 **켜진 채로** 있는가? |
| ⑦ | 스위치를 한 번 더 누른다 | LED가 꺼지는가? |
| ⑧ | 앱에서 `led/set` = `hello` 발행 | Jetson 터미널에 "알 수 없는 명령"이 출력되고 LED는 그대로인가? |
| ⑨ | 앱 연결을 끊었다가 다시 연결·구독 | 현재 LED 상태가 retained로 바로 오는가? `switch`는 오지 않는가? |
| ⑩ | Jetson에서 `Ctrl+C` | `led/state = OFF`, `status = offline`이 오는가? |

## 9.1 실행 결과 예

앱 역할의 테스트 프로그램이 ①~④, ⑧ 단계를 수행했을 때의 실제 기록이다(팀 ID만 `team01`로 바꾸어 표시).

**앱(구독자)에서 받은 메시지**

```text
[  0.9s] aiot-hs/team01/status    (retained) = online
[  0.9s] aiot-hs/team01/led/state (retained) = OFF
[  3.6s] aiot-hs/team01/led/set   = ON         ← 앱이 보낸 명령 (# 구독이라 자기 메시지도 보임)
[  4.2s] aiot-hs/team01/led/state = ON         ← Arduino ACK 후 Jetson이 발행
[  5.1s] aiot-hs/team01/led/set   = OFF
[  5.7s] aiot-hs/team01/led/state = OFF
[  6.6s] aiot-hs/team01/led/set   = TOGGLE
[  7.2s] aiot-hs/team01/led/state = ON
[  8.1s] aiot-hs/team01/led/set   = TOGGLE
[  8.7s] aiot-hs/team01/led/state = OFF
[  9.6s] aiot-hs/team01/led/set   = hello
```

**Jetson 브리지 터미널**

```text
[mqtt] <- aiot-hs/team01/led/set: ON
[serial] -> ON
[serial] <- ACK ON
[mqtt] -> aiot-hs/team01/led/state: ON
[mqtt] <- aiot-hs/team01/led/set: OFF
[serial] -> OFF
[serial] <- ACK OFF
[mqtt] -> aiot-hs/team01/led/state: OFF
[mqtt] <- aiot-hs/team01/led/set: TOGGLE
[serial] -> ON
[serial] <- ACK ON
[mqtt] -> aiot-hs/team01/led/state: ON
...
[mqtt] <- aiot-hs/team01/led/set: HELLO
[mqtt]    알 수 없는 명령입니다 (ON / OFF / TOGGLE)
```

- 앱이 `led/set`을 보낸 뒤 `led/state`가 돌아오기까지 약 **0.6초**가 걸렸다(앱 → broker → Jetson → Arduino → Jetson → broker → 앱). broker가 인터넷 너머에 있기 때문에 Lab.1의 시리얼 왕복보다 훨씬 느리다.
- `#`로 구독했기 때문에 앱이 보낸 `led/set` 메시지도 앱에 다시 보인다.

**스위치를 눌렀을 때(⑤~⑦)의 Jetson 터미널**은 다음과 같은 형태가 된다.

```text
[serial] <- BTN PRESSED
[serial] -> ON
[serial] <- ACK ON
[mqtt] -> aiot-hs/team01/led/state: ON
[serial] <- BTN RELEASED
[serial] <- BTN PRESSED
[serial] -> OFF
[serial] <- ACK OFF
[mqtt] -> aiot-hs/team01/led/state: OFF
[serial] <- BTN RELEASED
```

---

# 10. 동작 순서 정리

**앱에서 LED 켜기**

```text
 앱                 Broker                Jetson (bridge)              Arduino
 ──                 ──────                ───────────────              ───────
 publish ─led/set=ON─►
                    ──led/set=ON────────► on_message()
                                          send_cmd("ON") ───"ON\n"───► LED 켜짐 💡
                                          readline() ◄──"ACK ON"────── 
                    ◄─led/state=ON (retain)─ publish
 ◄─led/state=ON─────
 "LED 상태: ON" 표시
```

**하드웨어 스위치 누르기**

```text
 Arduino                     Jetson (bridge)                    Broker               앱
 ───────                     ───────────────                    ──────               ──
 스위치 누름
 "BTN PRESSED" ───────────►  readline()
                             publish ──switch=PRESSED─────────► ───────────────────► 표시
                             send_cmd(토글)
 LED 켜짐 💡 ◄───"ON\n"───── 
 "ACK ON" ────────────────►  publish ──led/state=ON (retain)──► ───────────────────► 표시
```

---

# 11. 실습 과제

**과제 1. 다른 팀 LED 관찰하기**

앱에서 `aiot-hs/+/led/state`를 구독해 보라. 무엇이 보이는가? 이 결과를 바탕으로 public broker의 보안 문제를 설명하고, 실제 서비스에서는 어떻게 해결해야 하는지 조사하라.

**과제 2. LWT 확인**

브리지를 실행한 상태에서 `Ctrl+C`가 아니라 **Jetson의 LAN 케이블(또는 Wi-Fi)을 끊어라.** 앱에 `status = offline`이 오기까지 몇 초가 걸리는지 측정하고, `keepalive=30` 값과 비교해 설명하라. (`Ctrl+C`로 끝냈을 때와 무엇이 다른가?)

**과제 3. 왕복 시간 측정**

앱 역할을 하는 Python 프로그램을 PC에서 작성하라. `led/set = TOGGLE`을 발행한 시각부터 `led/state`를 받은 시각까지를 10회 측정해 평균을 구하고, Lab.1 과제 1(시리얼 왕복 시간)과 비교하라.

**과제 4. 점멸 명령 추가**

`led/set`에 `BLINK 5`를 보내면 LED가 5번 깜빡이도록 `mqtt_bridge.py`를 수정하라. 점멸하는 동안 `led/state`가 어떻게 발행되어야 하는지 설계 이유와 함께 설명하라.

> 힌트: 점멸을 `on_message()` 안에서 `time.sleep()`으로 처리하면 그동안 다른 MQTT 메시지를 처리할 수 없다. 왜 그런지 6.1절의 스레드 구조로 설명하라.

**과제 5. 스위치 누른 횟수 발행**

스위치를 누른 횟수를 세어 `aiot-hs/<팀ID>/switch/count` topic에 retained로 발행하라. 앱을 껐다 켜도 횟수가 보이는지 확인하라.

---

# 12. 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `[mqtt] broker에 연결하지 못했습니다` | Jetson이 인터넷에 연결되지 않음, 1883 포트 차단 | `ping broker.hivemq.com`, 5.2절 확인. 학교 네트워크가 1883을 막으면 스마트폰 핫스팟으로 테스트 |
| `ModuleNotFoundError: No module named 'paho'` | paho-mqtt 미설치 | `pip3 install --user paho-mqtt` |
| `TypeError` 또는 `DeprecationWarning: Callback API version 1` | 인터넷의 paho-mqtt 1.x 예제 사용 | `mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, ...)` 사용, 콜백 인자 확인 |
| `SerialException: device reports readiness to read but returned no data` | 다른 프로그램(Lab.1 코드 등)이 시리얼 포트를 같이 사용 중 | 5.3절. `fuser -v /dev/ttyACM0`로 확인 후 그 프로그램 종료 |
| 앱에 아무 메시지도 안 옴 | topic 오타, 팀 ID 불일치, 대소문자 차이 | topic은 **대소문자를 구분**한다. 브리지가 출력한 `'aiot-hs/<팀ID>/#'`을 그대로 복사해 구독 |
| 앱에서 명령을 보내도 LED 반응 없음 | 발행 topic 오타 (`led/state`에 발행 등) | 발행 topic이 `.../led/set`인지 확인. Jetson 터미널에 `[mqtt] <-` 줄이 찍히는지 확인 |
| 브리지가 계속 끊겼다 다시 연결됨 | 다른 곳에서 **같은 Client ID**로 접속 | 코드는 랜덤 ID를 쓴다. 앱의 Client ID도 다른 사람과 겹치지 않게 자동 생성 값 사용 |
| 브라우저 클라이언트가 연결 안 됨 | 포트/SSL 설정 오류 | WebSocket은 `8884` + SSL, 또는 `8000` + SSL 해제 |
| HiveMQ WebSocket Client에서 Host를 `broker.hivemq.com`으로 바꾸면 연결 안 됨 | 브라우저 환경에 따라 발생 | Host를 기본값 `mqtt-dashboard.com`으로 두고 연결 (같은 broker) |
| HiveMQ WebSocket Client는 연결(초록 점)됐는데 메시지가 안 옴 | 구독 topic의 팀 ID가 브리지의 `--id`와 다름, 또는 브리지가 실행 중이 아님 | 브리지가 출력한 `'aiot-hs/<팀ID>/#'`을 그대로 복사해 구독 |
| 내가 보내지 않은 명령으로 LED가 켜짐 | 다른 사람이 같은 topic 사용 (public broker) | 더 고유한 팀 ID로 변경 (예: 학번 + 이니셜) |
| 브리지를 끈 뒤에도 앱에 예전 `led/state`가 보임 | retained 메시지가 broker에 남아 있음 | 정상 동작이다. 지우려면 같은 topic에 **빈 메시지**를 retain으로 발행 |
