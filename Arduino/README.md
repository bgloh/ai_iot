# Arduino 실습 참조 코드 (AIoT 11·12주차)

Jetson Orin Nano ↔ Arduino Uno 시리얼 통신(Lab.1, 11주차)과 MQTT 브리지(Lab.2, 12주차) 실습의 참조 코드입니다.
실습은 강의자료를 보며 **직접 입력**하고, 이 폴더의 코드는 오타·누락 확인용으로 사용합니다.

| 파일 | 실습 | 설명 |
|---|---|---|
| `led_serial/led_serial.ino` | Lab.1 Part A~E, Lab.2 공용 | LED(D7)·스위치(D6, 외부 10kΩ 풀업)·조도센서(A0)·서보(D9) |
| `led_blink_serial.py` | Lab.1 Part A | `ON`/`OFF` 명령으로 LED 점멸, `ACK` 확인 |
| `button_led_serial.py` | Lab.1 Part B | `BTN PRESSED/RELEASED` 이벤트로 LED 제어 |
| `light_read.py` | Lab.1 Part C | 조도 값(0~1023) 수신, 전압·막대그래프 표시 |
| `light_filter.py` | Lab.1 Part D | 이동평균·EMA·히스테리시스, CSV 기록 |
| `servo_control.py` | Lab.1 Part E | `SERVO <각도>` 명령, 직접 입력·`--sweep` |
| `mqtt_bridge.py` | Lab.2 | 시리얼 ↔ HiveMQ public broker 브리지 |
| `Serial_통신_Lab1.md`, `MQTT_통신_Lab2.md` | — | 실습 문서 |

## 배선 요약 (Arduino Uno)

- D7 → 220Ω → LED(+) → LED(−) → GND
- 5V → 10kΩ → D6 → 스위치 → GND (외부 풀업, 누르면 `LOW`)
- 5V → CdS → A0 → 10kΩ → GND (전압 분배, 밝을수록 값 증가)
- 서보 SG90: 갈색 GND, 빨강 5V, 주황 D9

## 받기와 실행 (Jetson)

```bash
git clone https://github.com/bgloh/ai_iot.git ~/ai_iot     # 실습 폴더(~/Arduino)와 다른 곳에 받는다
pip3 install --user pyserial paho-mqtt
arduino-cli lib install Servo                              # led_serial.ino 컴파일에 필요
```

모든 Python 프로그램은 `--port /dev/ttyACM0`처럼 시리얼 포트를 지정할 수 있습니다(생략 시 자동 탐색).
`light_read.py`, `light_filter.py`, `servo_control.py`, `button_led_serial.py`, `mqtt_bridge.py`는 `led_blink_serial.py`와 **같은 폴더**에 있어야 합니다.
