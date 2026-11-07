# Serial 통신 Lab.1 — Jetson ↔ Arduino LED·스위치·조도센서·서보모터

## 1. 실험 목적

본 실험의 목적은 Jetson Orin Nano와 Arduino Uno를 USB 케이블로 연결하고, 시리얼 통신으로 두 장치가 메시지를 주고받게 하는 것이다. 실험은 다섯 부분으로 나뉜다.

| 파트 | 내용 | 데이터 방향 |
|---|---|---|
| **Part A. LED 점멸** (10~12장) | Jetson이 `ON`/`OFF` 명령을 보내 LED(D7)를 깜빡인다 | Jetson → Arduino |
| **Part B. 스위치로 LED 제어** (13장) | 스위치(D6)를 누르면 Arduino가 Jetson에 알리고, Jetson이 LED를 켜는 명령을 보낸다 | Arduino → Jetson → Arduino |
| **Part C. 조도센서 입력** (14장) | 조도센서(A0) 값을 0.1초마다 받아 숫자·전압·막대그래프로 표시한다 | Arduino → Jetson |
| **Part D. 신호 필터링** (14장) | 이동평균·지수이동평균으로 값을 다듬고, 어두우면 LED를 켠다(히스테리시스) | Arduino → Jetson → Arduino |
| **Part E. 서보모터 제어** (14장) | Jetson이 `SERVO <각도>` 명령으로 서보(D9)를 움직인다 | Jetson → Arduino |

이 실험을 통해 다음을 익힌다.

- 시리얼(UART) 통신의 기본 개념: 통신 속도(baud rate), 데이터 프레임, 줄바꿈 기반 메시지
- 리눅스에서 USB 시리얼 장치(`/dev/ttyACM0`)를 확인하고 접근 권한을 설정하는 방법
- `arduino-cli`로 Jetson에서 직접 Arduino 스케치를 컴파일하고 업로드하는 방법
- 명령(Command)과 응답(ACK)으로 이루어진 간단한 통신 프로토콜 설계
- 풀업(pull-up) 스위치 입력과 디바운싱(debouncing), 이벤트 기반 양방향 통신

전체 실험 흐름은 다음과 같다.

```text
PC (VS Code Remote-SSH)
  ↓  SSH 접속
Jetson Orin Nano
  ├─ Arduino 연결 확인 (lsusb, /dev/ttyACM0)
  ├─ 시리얼 포트 권한 설정 (dialout 그룹)
  ├─ pyserial 설치
  ├─ arduino-cli 설치 → 스케치 컴파일 → Arduino에 업로드
  └─ Python 프로그램 실행
        ↕  USB 시리얼
     Arduino Uno
        ├─ "ON\n" / "OFF\n" 수신 → LED(D7) 켜기/끄기 → "ACK ON" / "ACK OFF" 응답
        ├─ 스위치(D6) 누름/뗌 감지 → "BTN PRESSED" / "BTN RELEASED" 전송
        ├─ 조도센서(A0) → "LIGHT <0~1023>" 전송 (Part C·D)
        └─ "SERVO <각도>\n" 수신 → 서보(D9) 회전 → "ACK SERVO <각도>" 응답 (Part E)
```

---

# 2. 실험 환경

본 실험에서 확인된 주요 환경은 다음과 같다.

```text
Host PC: Windows 11 + VS Code (Remote - SSH 확장)
Device: NVIDIA Jetson Orin Nano Developer Kit Super
JetPack: 6.2 (L4T R36.4.3)
OS: Ubuntu 22.04.5 LTS (aarch64)
Python: 3.10
pyserial: 3.5
arduino-cli: 1.5.1
Arduino AVR core: arduino:avr 1.8.8
Microcontroller: Arduino Uno R3 (USB ID 2341:0043)
연결: USB A-B 데이터 케이블 (Jetson USB 포트 ↔ Arduino)
```

준비물

| 준비물 | 비고 |
|---|---|
| Jetson Orin Nano | 같은 네트워크에 연결, SSH 접속 가능 |
| Arduino Uno R3 | 호환보드(CH340 칩)도 가능 — 16장 참고 |
| USB 케이블 | **데이터 전송용** 케이블. 충전 전용 케이블은 인식되지 않음 |
| PC | VS Code + Remote - SSH 확장 설치 |
| LED 1개 | 색상 무관 |
| 저항 220 Ω ~ 330 Ω 1개 | LED 전류 제한용 |
| 푸시 스위치(택트 스위치) 1개 | Part B용 |
| 저항 10 kΩ 2개 | 스위치 풀업 1개(Part B), 조도센서 전압 분배 1개(Part C) |
| 조도센서(CdS) 1개 | Part C·D용 |
| 서보모터 SG90 1개 | Part E용 |
| 브레드보드, 점퍼선 | |

## 2.1 LED 배선

LED를 Arduino의 **디지털 7번 핀(D7)** 에 연결한다.

```text
Arduino D7 ──── [저항 220Ω] ──── (+) LED (−) ──── Arduino GND
                                 긴 다리  짧은 다리
```

- LED는 극성이 있다. **긴 다리(+, 애노드)** 를 저항 쪽, **짧은 다리(−, 캐소드)** 를 GND 쪽에 연결한다.
- 저항 없이 연결하면 과전류로 LED나 Arduino 핀이 손상될 수 있다.
- 배선은 **USB를 뽑은 상태**에서 한다.

> 외부 LED가 없으면 보드 내장 LED(보드에 **L**로 표시, 13번 핀)를 사용해도 된다. 8장 스케치에서 `LED_PIN`을 `LED_BUILTIN`으로 바꾸면 된다.

## 2.2 스위치 배선 (외부 풀업)

스위치를 Arduino의 **디지털 6번 핀(D6)** 에 **외부 10kΩ 풀업(pull-up)** 방식으로 연결한다.

```text
            Arduino 5V
                │
          [저항 10kΩ]          ← 외부 풀업 저항 (갈·검·주)
                │
Arduino D6 ─────┤  (D6 노드)
                │
              [스위치]
                │
Arduino GND ────┘
```

- 외부 10kΩ 풀업 저항(갈·검·주)을 **D6와 5V 사이**에 단다.
- 스위치의 한쪽 다리는 **D6 노드**, 반대쪽 다리는 **GND**에 연결한다.
- 칩 내부에도 풀업 저항(약 20~50kΩ)이 있어 `INPUT_PULLUP`으로 켤 수 있으나, 본 실습은 **외부 풀업**을 사용한다(8장 `pinMode(BUTTON_PIN, INPUT)`).
- 외부 풀업을 쓰는 이유:
  1. 저항값을 직접 정할 수 있어(10kΩ) 잡음에 강하다.
  2. 회로도에 저항이 드러나 있어 동작을 파악하기 쉽다.
  3. 내부 풀업이 없는 핀이나 보드에서도 같은 방법으로 쓸 수 있다.
- ⚠️ 10kΩ 저항을 빼먹으면 D6가 떠서(floating) 누르지 않아도 `BTN PRESSED/RELEASED`가 저절로 발생한다.
- 택트 스위치는 다리가 4개이고 **두 개씩 내부에서 연결**되어 있다. 브레드보드 가운데 홈을 가로지르게 꽂고, **대각선 방향** 다리를 사용하면 실수를 줄일 수 있다.

| 스위치 상태 | D6 전압 | `digitalRead(6)` |
|---|---|---|
| 떼었을 때 | 10kΩ 풀업 저항을 통해 5V | `HIGH` |
| 눌렀을 때 | GND와 직접 연결 | `LOW` |

풀업 회로에서는 **누르면 LOW**가 된다는 점에 주의한다(3.6절).

---

# 3. 배경 지식

## 3.1 시리얼 통신이란?

시리얼(Serial) 통신은 데이터를 **한 비트씩 차례대로** 보내는 통신 방식이다. Arduino가 사용하는 UART 방식은 송신선(TX)과 수신선(RX) 두 가닥으로 양방향 통신을 한다.

```text
  Jetson (Python)                       Arduino
  ┌───────────┐   TX ───────────► RX   ┌───────────┐
  │           │                        │           │
  │           │   RX ◄─────────── TX   │           │
  └───────────┘                        └───────────┘
```

UART 한 글자(1 byte)는 보통 다음 형태로 전송된다. 이를 **8N1**(데이터 8비트, 패리티 없음, 정지 비트 1개)이라고 부르며, pyserial과 Arduino의 기본값이다.

```text
 idle ─┐ start │ b0 │ b1 │ b2 │ b3 │ b4 │ b5 │ b6 │ b7 │ stop ┌─ idle
       └───────┴────┴────┴────┴────┴────┴────┴────┴────┴──────┘
```

## 3.2 통신 속도 (Baud rate)

**Baud rate**는 1초에 전송하는 비트 수다. 본 실험은 `9600` bps를 사용한다.

- 8N1에서는 한 글자에 10비트(시작 1 + 데이터 8 + 정지 1)가 필요하다.
- 따라서 9600 bps는 초당 약 960글자를 보낼 수 있다.
- **송신 측과 수신 측의 baud rate가 반드시 같아야 한다.** 다르면 글자가 깨지거나 아무것도 받지 못한다.

## 3.3 USB 시리얼과 리눅스 장치 파일

Arduino Uno에는 USB를 UART로 바꿔 주는 칩이 들어 있다. USB로 연결하면 Jetson(리눅스)은 이를 **가상 시리얼 포트**로 인식하고 장치 파일을 만든다.

| 보드 종류 | 장치 파일 | 드라이버 |
|---|---|---|
| 정품 Uno R3 (ATmega16U2) | `/dev/ttyACM0` | CDC ACM |
| 호환보드 (CH340 / CH341) | `/dev/ttyUSB0` | ch341 |

리눅스에서는 "장치도 파일"이므로, Python은 이 파일을 열고 읽고 쓰는 방식으로 Arduino와 통신한다.

## 3.4 메시지 경계와 프로토콜

시리얼 통신은 **바이트의 연속(stream)** 일 뿐, 어디서 메시지가 끝나는지 알려 주지 않는다. 그래서 송신 측과 수신 측이 규칙(프로토콜)을 정해야 한다. 본 실험의 규칙은 다음과 같다.

| 방향 | 메시지 | 의미 |
|---|---|---|
| Jetson → Arduino | `ON\n` | LED 켜기 |
| Jetson → Arduino | `OFF\n` | LED 끄기 |
| Arduino → Jetson | `READY` | 부팅 완료 |
| Arduino → Jetson | `ACK ON` / `ACK OFF` | 명령 처리 완료 |
| Arduino → Jetson | `ERR <명령>` | 알 수 없는 명령 |
| Arduino → Jetson | `BTN PRESSED` | 스위치를 누름 (이벤트, Part B) |
| Arduino → Jetson | `BTN RELEASED` | 스위치를 뗌 (이벤트, Part B) |
| Jetson → Arduino | `LIGHT\n` | 조도 값 한 번 요청 → `LIGHT <0~1023>` 응답 (Part C) |
| Jetson → Arduino | `STREAM ON\n` / `STREAM OFF\n` | 조도 값 연속 전송 시작/중지 → `ACK STREAM ON/OFF` (Part C·D) |
| Arduino → Jetson | `LIGHT <0~1023>` | STREAM ON 동안 0.1초마다 보내는 조도 값 (Part C·D) |
| Jetson → Arduino | `SERVO <0~180>\n` | 서보 각도 설정 → `ACK SERVO <각도>`, 범위 밖이면 `ERR ...` (Part E) |

- 모든 메시지는 **줄바꿈 문자(`\n`)로 끝난다.** 수신 측은 줄바꿈이 올 때까지 읽으면 메시지 하나를 얻는다.
- 명령마다 응답(ACK)을 받으므로, Jetson은 Arduino가 명령을 제대로 처리했는지 확인할 수 있다.
- `BTN ...` 메시지는 Jetson이 요청하지 않아도 Arduino가 **스스로 보내는 이벤트**다. 따라서 Jetson은 ACK를 기다리는 도중에도 이벤트가 끼어들 수 있다는 점을 고려해야 한다(10.1절).

## 3.6 풀업 입력과 디바운싱

**풀업(Pull-up)**

입력 핀에 아무것도 연결되지 않으면 전압이 정해지지 않아 `HIGH`와 `LOW`가 무작위로 읽힌다(floating 상태). 이를 막기 위해 저항으로 핀을 5V 쪽에 "끌어올려" 두는 것이 풀업이다.

- 스위치를 떼면 저항을 통해 5V → `HIGH`
- 스위치를 누르면 GND에 직접 연결 → `LOW`

본 실습은 외부 10kΩ 풀업과 `INPUT`을 사용한다. 외부 저항 없이 쓰려면 `INPUT_PULLUP`으로 내부 풀업을 켠다.

**디바운싱(Debouncing)**

기계식 스위치는 누르는 순간 접점이 수 ms 동안 붙었다 떨어졌다를 반복한다(채터링, bouncing). 그대로 읽으면 한 번 눌렀는데 여러 번 누른 것처럼 인식된다.

```text
실제 핀 값:  HIGH ──┐ ┌┐ ┌┐ ┌──────────┐ ┌┐ ┌─── HIGH
                   └─┘└─┘└─┘          └─┘└─┘
                   ← 채터링 →  LOW 안정  ← 채터링 →
확정 상태:   HIGH ─────────┐               ┌──────── HIGH
                           └───────────────┘
                     30ms 유지 후 PRESSED     30ms 유지 후 RELEASED
```

본 실험은 **값이 30 ms 이상 바뀌지 않고 유지될 때만** 상태 변화로 인정하는 방식으로 채터링을 걸러 낸다(8.1절 `checkButton()`).

## 3.5 Arduino 자동 리셋

Arduino Uno는 PC(또는 Jetson)가 시리얼 포트를 **여는 순간 자동으로 리셋**된다. 업로드를 편하게 하려고 만든 기능이다(DTR 신호).

리셋 후 프로그램이 다시 시작되기까지 약 1~2초가 걸린다. 그 사이에 보낸 명령은 사라지므로, **포트를 연 뒤 2초 정도 기다려야 한다.** 본 실험 코드의 `time.sleep(2)`가 이 역할을 한다.

---

# 4. Jetson 접속

VS Code의 Remote - SSH로 Jetson에 접속한다. 자세한 방법은 [README.md](../README.md)를 참고한다.

1. VS Code 왼쪽의 **원격 탐색기(Remote Explorer)** 를 연다.
   아이콘이 보이지 않으면 `Ctrl+Shift+P` → **Remote-SSH: Connect to Host...** 를 사용한다.
2. `hansungai@<JETSON_IP>` 에 접속한다.
3. 메뉴 **Terminal → New Terminal** 로 Jetson 터미널을 연다.

이후의 모든 명령은 **Jetson 터미널**에서 실행한다(PC의 PowerShell이 아님).

실습 폴더를 만든다.

```bash
mkdir -p ~/Arduino/led_serial
cd ~/Arduino
```

> `arduino-cli`는 **스케치 폴더 이름과 `.ino` 파일 이름이 같아야** 한다. 그래서 `led_serial/led_serial.ino` 구조를 사용한다.

---

# 5. Arduino 연결 확인

Arduino를 USB 케이블로 Jetson에 연결한 뒤 다음을 실행한다.

```bash
lsusb
```

출력 예:

```text
Bus 001 Device 004: ID 2341:0043 Arduino SA Uno R3 (CDC ACM)
Bus 001 Device 002: ID 0bda:5489 Realtek Semiconductor Corp. 4-Port USB 2.0 Hub
...
```

`Arduino SA Uno R3`가 보이면 USB 장치로 인식된 것이다. 호환보드라면 `QinHeng Electronics CH340`처럼 보인다.

시리얼 장치 파일을 확인한다.

```bash
ls -l /dev/ttyACM* /dev/ttyUSB*
```

출력 예:

```text
ls: cannot access '/dev/ttyUSB*': No such file or directory
crw-rw---- 1 root dialout 166, 0 11월  5 17:19 /dev/ttyACM0
```

여기서 중요한 정보는 다음과 같다.

| 항목 | 값 | 의미 |
|---|---|---|
| 장치 파일 | `/dev/ttyACM0` | Python에서 열어야 할 포트 이름 |
| 소유자 | `root` | |
| 그룹 | `dialout` | **dialout 그룹 사용자만** 읽고 쓸 수 있음 |
| 권한 | `crw-rw----` | 소유자·그룹은 읽기/쓰기 가능, 그 외 사용자는 접근 불가 |

> `lsusb`에 Arduino가 보이지 않으면 케이블이 **충전 전용**인지 먼저 의심한다. 다른 케이블로 바꿔 본다.

---

# 6. 시리얼 포트 권한 설정

5장에서 본 것처럼 `/dev/ttyACM0`은 `dialout` 그룹만 사용할 수 있다. 현재 사용자의 그룹을 확인한다.

```bash
groups
```

```text
hansungai adm cdrom sudo audio dip video plugdev ...
```

`dialout`이 없으면 현재 사용자를 `dialout` 그룹에 추가한다(최초 1회, 비밀번호 필요).

```bash
sudo usermod -aG dialout $USER
```

## 6.1 ⚠️ 그룹 추가 후 반드시 다시 로그인

리눅스의 그룹 정보는 **로그인할 때** 정해진다. 그래서 `usermod`를 실행해도 **이미 열려 있는 터미널에는 반영되지 않는다.**

특히 VS Code Remote-SSH는 Jetson에서 VS Code 서버가 계속 실행되고 있어서, **새 터미널 탭을 열어도 반영되지 않는다.** 다음 중 하나를 수행한다.

| 방법 | 명령 | 적용 범위 |
|---|---|---|
| ① 현재 터미널만 즉시 적용 | `newgrp dialout` | 지금 터미널 |
| ② VS Code 서버 재시작 (권장) | `Ctrl+Shift+P` → **Remote-SSH: Kill VS Code Server on Host...** → 다시 접속 | 이후 모든 터미널 |
| ③ Jetson 재부팅 | `sudo reboot` | 전체 |

다시 확인한다.

```bash
groups
```

```text
hansungai adm dialout cdrom sudo audio ...
```

`dialout`이 보이면 성공이다.

---

# 7. pyserial 설치

`pyserial`은 Python에서 시리얼 포트를 다루는 라이브러리다. 사용자 계정에 설치한다(sudo 불필요).

```bash
pip3 install --user pyserial
```

설치를 확인한다.

```bash
python3 -c "import serial; print('pyserial', serial.__version__)"
```

```text
pyserial 3.5
```

> 패키지 이름은 `pyserial`이지만, 코드에서는 `import serial`로 불러온다. `pip3 install serial`은 **전혀 다른 패키지**이므로 설치하지 않도록 주의한다.

---

# 8. Arduino 스케치 작성

VS Code에서 `~/Arduino/led_serial/led_serial.ino` 파일을 만들고 다음 코드를 입력한다.

이 스케치 하나로 Part A(LED 점멸), Part B(스위치 입력), Part C~E(조도센서·필터링·서보모터)를 모두 수행한다. `← 추가` 표시가 붙은 부분은 Part C~E용이다(14장). 같은 코드가 저장소의 `Arduino/led_serial/led_serial.ino`에 있다.

```cpp
// Jetson과 시리얼로 통신하며 LED(D7)를 제어하고 스위치(D6) 상태를 보고한다.
// Part C~E 확장: 조도센서(A0) 값을 보고하고, 서보모터(D9)를 제어한다.
//
// Jetson → Arduino 명령:  "ON\n", "OFF\n"
//                         "LIGHT\n", "STREAM ON\n", "STREAM OFF\n", "SERVO <0~180>\n"   ← 추가
// Arduino → Jetson 응답:  "ACK ON", "ACK OFF", "ERR <명령>"
//                         "LIGHT <0~1023>", "ACK STREAM ON", "ACK STREAM OFF", "ACK SERVO <각도>"   ← 추가
// Arduino → Jetson 이벤트: "BTN PRESSED", "BTN RELEASED"
//                         STREAM ON 동안 0.1초마다 "LIGHT <0~1023>"   ← 추가

#include <Servo.h>                     // ← 추가

const int LED_PIN = 7;                // 디지털 7번 핀에 연결한 LED
const int BUTTON_PIN = 6;             // 디지털 6번 핀에 연결한 스위치 (외부 10kΩ 풀업, 누르면 LOW)
const unsigned long DEBOUNCE_MS = 30; // 스위치 떨림(채터링) 무시 시간

const int LIGHT_PIN = A0;             // ← 추가: 조도센서(CdS) 전압 분배 출력
const int SERVO_PIN = 9;              // ← 추가: 서보모터 신호선(주황)
const unsigned long STREAM_MS = 100;  // ← 추가: 조도 값 전송 주기 (0.1초)

int lastReading = HIGH;               // 직전에 읽은 핀 값
int buttonState = HIGH;               // 디바운싱이 끝난 확정 상태
unsigned long lastChangeMs = 0;       // 핀 값이 마지막으로 바뀐 시각

Servo servo;                          // ← 추가
bool streaming = false;               // ← 추가: true이면 조도 값을 계속 보낸다
unsigned long lastStreamMs = 0;       // ← 추가

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  pinMode(BUTTON_PIN, INPUT);         // 외부 10kΩ 풀업 사용 (외부 저항 없이 쓰려면 INPUT_PULLUP)
  servo.attach(SERVO_PIN);            // ← 추가
  servo.write(90);                    // ← 추가: 시작 위치는 가운데(90도)
  Serial.begin(9600);
  Serial.println("READY");
}

// Jetson이 보낸 명령을 처리한다.
void handleCommand() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd == "ON") {
      digitalWrite(LED_PIN, HIGH);
      Serial.println("ACK ON");
    } else if (cmd == "OFF") {
      digitalWrite(LED_PIN, LOW);
      Serial.println("ACK OFF");
    } else if (cmd == "LIGHT") {                 // ← 추가: 조도 값 한 번 읽기
      Serial.print("LIGHT ");
      Serial.println(analogRead(LIGHT_PIN));
    } else if (cmd == "STREAM ON") {             // ← 추가: 조도 값 계속 보내기
      streaming = true;
      Serial.println("ACK STREAM ON");
    } else if (cmd == "STREAM OFF") {            // ← 추가
      streaming = false;
      Serial.println("ACK STREAM OFF");
    } else if (cmd.startsWith("SERVO ")) {       // ← 추가: 서보 각도
      int deg = cmd.substring(6).toInt();
      if (deg >= 0 && deg <= 180) {
        servo.write(deg);
        Serial.print("ACK SERVO ");
        Serial.println(deg);
      } else {
        Serial.print("ERR ");
        Serial.println(cmd);
      }
    } else if (cmd.length() > 0) {
      Serial.print("ERR ");
      Serial.println(cmd);
    }
  }
}

// 스위치 상태가 바뀌면 Jetson에 알린다.
void checkButton() {
  int reading = digitalRead(BUTTON_PIN);

  if (reading != lastReading) {       // 값이 바뀌면 시간을 다시 잰다
    lastChangeMs = millis();
    lastReading = reading;
  }

  // 같은 값이 DEBOUNCE_MS 이상 유지되면 상태 변화로 확정한다.
  if (millis() - lastChangeMs > DEBOUNCE_MS && reading != buttonState) {
    buttonState = reading;
    if (buttonState == LOW) {
      Serial.println("BTN PRESSED");
    } else {
      Serial.println("BTN RELEASED");
    }
  }
}

// ← 추가: STREAM ON 상태이면 STREAM_MS마다 조도 값을 보낸다.
void streamLight() {
  if (streaming && millis() - lastStreamMs >= STREAM_MS) {
    lastStreamMs = millis();
    Serial.print("LIGHT ");
    Serial.println(analogRead(LIGHT_PIN));
  }
}

void loop() {
  handleCommand();
  checkButton();
  streamLight();                      // ← 추가
}
```

## 8.1 코드 설명

**핀 설정과 명령 처리 — `setup()`, `handleCommand()`**

| 코드 | 설명 |
|---|---|
| `LED_PIN = 7` | LED를 연결한 디지털 핀 번호 (2.1절 배선) |
| `BUTTON_PIN = 6` | 스위치를 연결한 디지털 핀 번호 (2.2절 배선) |
| `pinMode(LED_PIN, OUTPUT)` | 7번 핀을 출력으로 설정 |
| `pinMode(BUTTON_PIN, INPUT)` | 6번 핀을 입력으로 설정 (외부 10kΩ 풀업 사용, 3.6절) |
| `Serial.begin(9600)` | 시리얼 통신을 9600 bps로 시작. **Python 쪽과 같아야 함** |
| `Serial.println("READY")` | 부팅이 끝났음을 Jetson에 알림. `println`은 끝에 줄바꿈(`\r\n`)을 붙임 |
| `Serial.available()` | 수신 버퍼에 도착한 바이트 수. 0보다 크면 읽을 데이터가 있음 |
| `Serial.readStringUntil('\n')` | 줄바꿈이 올 때까지 읽어 문자열로 반환. 줄바꿈 자체는 포함하지 않음 |
| `cmd.trim()` | 앞뒤 공백과 `\r` 제거. 송신 측이 `\r\n`을 보내도 정상 동작하게 함 |
| `digitalWrite(LED_PIN, HIGH/LOW)` | LED 켜기 / 끄기 |
| `Serial.println("ACK ...")` | 명령 처리 결과를 Jetson에 응답 |

**스위치 감지 — `checkButton()`**

| 코드 | 설명 |
|---|---|
| `digitalRead(BUTTON_PIN)` | 6번 핀 값 읽기. 떼면 `HIGH`, 누르면 `LOW` |
| `millis()` | Arduino가 켜진 뒤 지난 시간(ms) |
| `reading != lastReading` | 핀 값이 바뀌었으면(채터링 포함) 시각을 기록하고 다시 기다림 |
| `millis() - lastChangeMs > DEBOUNCE_MS` | 같은 값이 30 ms 넘게 유지되면 안정된 값으로 봄 |
| `reading != buttonState` | 안정된 값이 이전 확정 상태와 다를 때만 이벤트 전송 → **한 번 누르면 한 번만** 보냄 |
| `Serial.println("BTN PRESSED")` | 누름 이벤트를 Jetson에 전송 |

**메인 루프 — `loop()`**

`loop()`는 `handleCommand()`와 `checkButton()`을 번갈아 매우 빠르게(수 μs~수 ms마다) 호출한다. `delay()`를 쓰지 않았기 때문에 명령 수신과 스위치 감지가 서로를 막지 않는다.

`setup()`은 전원이 켜지거나 리셋될 때 **한 번** 실행되고, `loop()`는 그 뒤로 **계속 반복** 실행된다.

> **생각해 보기:** 이 스케치의 Arduino는 스위치를 눌러도 LED를 **직접 켜지 않는다.** 스위치 상태를 Jetson에 보고만 하고, LED를 켤지는 Jetson이 판단한다. 이렇게 하면 Arduino 코드를 바꾸지 않고 Jetson의 Python 코드만 바꿔서 동작(예: 토글, AI 모델 판단 결과와 결합)을 바꿀 수 있다.

---

# 9. arduino-cli로 스케치 업로드

Arduino IDE 없이 Jetson 터미널에서 직접 컴파일과 업로드를 할 수 있도록 `arduino-cli`를 사용한다.

## 9.1 arduino-cli 설치 (최초 1회)

사용자 폴더(`~/.local/bin`)에 설치하므로 sudo가 필요 없다.

```bash
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=~/.local/bin sh
export PATH=$HOME/.local/bin:$PATH
arduino-cli version
```

```text
arduino-cli  Version: 1.5.1 ...
```

> 새 터미널에서도 `arduino-cli` 명령을 쓰려면 다음을 한 번 실행해 둔다.
> ```bash
> echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc
> ```

## 9.2 Arduino AVR 보드 패키지 설치 (최초 1회)

Uno는 AVR 계열 칩(ATmega328P)을 사용하므로 AVR 컴파일러와 업로드 도구를 설치한다.

```bash
arduino-cli core update-index
arduino-cli core install arduino:avr
```

```text
Platform arduino:avr@1.8.8 installed
```

연결된 보드를 확인한다.

```bash
arduino-cli board list
```

```text
Port         Protocol Type              Board Name  FQBN            Core
/dev/ttyACM0 serial   Serial Port (USB) Arduino UNO arduino:avr:uno arduino:avr
/dev/ttyAMA0 serial   Serial Port       Unknown
```

`/dev/ttyAMA0`은 Jetson 보드 자체의 UART 포트이며 이번 실험에서는 사용하지 않는다.

**FQBN**(Fully Qualified Board Name)은 보드 종류를 나타내는 이름이다. Uno는 `arduino:avr:uno`이다.

**Servo 라이브러리 설치 (최초 1회)**

8장 스케치는 서보모터 제어(Part E)를 위해 `#include <Servo.h>`를 사용한다. 컴파일 전에 라이브러리를 한 번 설치한다.

```bash
arduino-cli lib install Servo
```

```text
Installed Servo@...
```

## 9.3 컴파일

```bash
cd ~/Arduino
arduino-cli compile --fqbn arduino:avr:uno led_serial
```

```text
Sketch uses 3974 bytes (12%) of program storage space. Maximum is 32256 bytes.
Global variables use 256 bytes (12%) of dynamic memory, leaving 1792 bytes for local variables. Maximum is 2048 bytes.
```

Uno는 프로그램 저장 공간이 32 KB, RAM이 2 KB뿐이다. 위 출력은 Part A·B만 있던 스케치 기준(각각 12%)이며, Part C~E 확장판은 Servo 라이브러리가 더해져 사용량이 조금 더 크다.

## 9.4 업로드

```bash
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno led_serial
```

```text
New upload port: /dev/ttyACM0 (serial)
```

업로드하는 동안 보드의 **RX/TX LED가 빠르게 깜빡인다.**

> 업로드 중에는 다른 프로그램(Python 코드, 시리얼 모니터)이 포트를 사용하고 있으면 안 된다.

> **참고:** Jetson 대신 PC의 Arduino IDE로 업로드해도 된다. Arduino를 PC에 연결해 업로드한 뒤, USB 케이블을 Jetson으로 옮겨 꽂으면 된다. 업로드된 프로그램은 전원이 꺼져도 Arduino에 남아 있다.

---

# 10. Part A — LED 점멸 프로그램 작성

VS Code에서 `~/Arduino/led_blink_serial.py` 파일을 만들고 다음 코드를 입력한다.

```python
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
```

## 10.1 코드 설명

**포트 자동 탐색 — `find_arduino_port()`**

`serial.tools.list_ports.comports()`는 시스템의 시리얼 포트 목록을 돌려준다. 그중 이름에 `ttyACM` 또는 `ttyUSB`가 들어간 첫 번째 포트를 Arduino로 간주한다.

**포트 열기 — `serial.Serial(port, 9600, timeout=2)`**

| 인자 | 의미 |
|---|---|
| `port` | 장치 파일 이름 (`/dev/ttyACM0`) |
| `9600` | baud rate. **Arduino의 `Serial.begin(9600)`과 같아야 함** |
| `timeout=2` | `readline()`이 최대 2초까지 기다림. 응답이 없으면 빈 값 반환 |

`with` 문을 사용하면 프로그램이 끝나거나 오류가 나도 포트가 자동으로 닫힌다.

**리셋 대기 — `time.sleep(2)`**

3.5절에서 설명한 자동 리셋 때문에, 포트를 열고 2초를 기다린 뒤 Arduino가 보낸 `READY`를 읽는다.

**명령 전송과 응답 수신 — `send()`**

```python
ser.write((cmd + "\n").encode())          # 문자열 → 바이트로 바꿔 전송
reply = ser.readline().decode(...).strip()  # 줄바꿈까지 읽고 → 문자열로 바꿈
```

- 시리얼 포트는 **바이트(bytes)** 만 주고받는다. 그래서 문자열을 보낼 때는 `.encode()`, 받을 때는 `.decode()`가 필요하다.
- `"ON"` 뒤에 `"\n"`을 붙이는 이유는 Arduino의 `readStringUntil('\n')`이 줄바꿈을 메시지 끝으로 인식하기 때문이다(3.4절).
- `.strip()`은 Arduino `println()`이 붙인 `\r\n`을 제거한다.
- `while True` 반복은 `ACK` 또는 `ERR`로 시작하는 줄이 올 때까지 읽는다. 점멸 도중 스위치를 누르면 `BTN PRESSED`가 ACK보다 먼저 도착할 수 있는데, 이것을 ACK로 착각하지 않고 `(이벤트: ...)`로 따로 출력하기 위해서다.

**안전한 종료 — `try / except KeyboardInterrupt / finally`**

`Ctrl+C`로 중단해도 `finally`에서 `OFF`를 보내므로 LED가 켜진 채로 남지 않는다.

**명령줄 인자 — `argparse`**

| 인자 | 기본값 | 설명 |
|---|---|---|
| `--port` | 자동 탐색 | 시리얼 포트 지정 |
| `--baud` | 9600 | 통신 속도 |
| `--count` | 10 | 점멸 횟수 |
| `--interval` | 0.5 | 켜짐/꺼짐 각각 유지 시간(초) |

---

# 11. Part A — 실행 및 결과

```bash
cd ~/Arduino
python3 led_blink_serial.py --count 3 --interval 0.5
```

실행 결과:

```text
포트: /dev/ttyACM0, 속도: 9600
아두이노: READY
[1/3]
-> ON  | <- ACK ON
-> OFF | <- ACK OFF
[2/3]
-> ON  | <- ACK ON
-> OFF | <- ACK OFF
[3/3]
-> ON  | <- ACK ON
-> OFF | <- ACK OFF
-> OFF | <- ACK OFF
```

- 첫 줄의 `READY`는 Arduino가 리셋 후 `setup()`에서 보낸 메시지다.
- 각 명령마다 `ACK`가 돌아오면 통신이 양방향으로 정상 동작하는 것이다.
- 마지막 `OFF`는 `finally`에서 보낸 종료 명령이다.
- 7번 핀에 연결한 LED가 0.5초 간격으로 3번 깜빡이는 것을 눈으로 확인한다.

간격과 횟수를 바꿔 실행해 본다.

```bash
python3 led_blink_serial.py --count 10 --interval 0.2
```

---

# 12. Part A — 동작 순서 정리

```text
Jetson (Python)                                  Arduino
───────────────                                  ───────
serial.Serial() 로 포트 열기  ───(DTR 신호)───►  자동 리셋
time.sleep(2)                                    setup() 실행
                              ◄── "READY\r\n" ── Serial.println("READY")
readline() → "READY"

write("ON\n")                 ─── "ON\n" ─────►  readStringUntil('\n') → "ON"
                                                 digitalWrite(7, HIGH)  💡
                              ◄── "ACK ON\r\n" ─ Serial.println("ACK ON")
readline() → "ACK ON"
sleep(interval)

write("OFF\n")                ─── "OFF\n" ────►  digitalWrite(7, LOW)
                              ◄── "ACK OFF\r\n"─
   ... count 만큼 반복 ...

포트 닫기 (with 블록 종료)
```

---

# 13. Part B — 스위치를 누르면 LED 켜기

Part A에서는 Jetson이 일방적으로 명령을 보냈다. Part B에서는 **Arduino가 먼저 이벤트를 보내고, Jetson이 그 이벤트에 반응해 명령을 보낸다.**

```text
 스위치 누름 → Arduino ──"BTN PRESSED"──► Jetson ──"ON"──► Arduino → LED 켜짐 💡
 스위치 뗌   → Arduino ──"BTN RELEASED"─► Jetson ──"OFF"─► Arduino → LED 꺼짐
```

스케치는 8장에서 업로드한 것을 그대로 사용한다. 2.2절의 스위치 배선을 확인한다.

## 13.1 코드 작성

VS Code에서 `~/Arduino/button_led_serial.py` 파일을 만들고 다음 코드를 입력한다. `led_blink_serial.py`와 **같은 폴더**에 있어야 한다(포트 탐색 함수를 가져다 쓰기 때문).

```python
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
```

## 13.2 코드 설명

**이벤트 루프 — `while True: ser.readline()`**

Part A는 "명령 보내기 → 응답 기다리기"를 정해진 횟수만큼 반복했다. Part B는 **언제 올지 모르는 이벤트를 계속 기다리다가**, 도착하면 그에 맞는 동작을 하는 구조다. 이런 구조를 **이벤트 루프(event loop)** 라고 한다.

| 받은 메시지 | Jetson의 동작 |
|---|---|
| `BTN PRESSED` | `ON\n` 전송 → LED 켜짐 |
| `BTN RELEASED` | `OFF\n` 전송 → LED 꺼짐 |
| `READY`, `ACK ON`, `ACK OFF` | 출력만 함 |

**`timeout=None`**

`readline()`이 한 줄이 완성될 때까지 무한정 기다린다. 스위치를 언제 누를지 모르므로 시간 제한을 두지 않는다.

> `timeout`을 짧게(예: 0.1초) 주면, 메시지가 반쯤 도착했을 때 `readline()`이 끊겨 `BTN PRE`처럼 잘린 줄을 돌려줄 수 있다. 이벤트를 기다리는 프로그램에서는 `timeout=None`이 안전하다.

**`from led_blink_serial import find_arduino_port`**

Part A에서 만든 포트 탐색 함수를 다시 사용한다. 같은 폴더의 `.py` 파일은 모듈처럼 `import`할 수 있다. `led_blink_serial.py`의 `main()`은 `if __name__ == "__main__":` 안에 있으므로, import할 때 점멸이 실행되지 않는다.

## 13.3 실행 및 결과

```bash
cd ~/Arduino
python3 button_led_serial.py
```

스위치를 두 번 눌렀다 뗀 뒤 `Ctrl+C`로 종료한 결과:

```text
포트: /dev/ttyACM0, 속도: 9600
스위치를 누르면 LED가 켜집니다. 종료: Ctrl+C
<- READY
<- BTN PRESSED
-> ON
<- ACK ON
<- BTN RELEASED
-> OFF
<- ACK OFF
<- BTN PRESSED
-> ON
<- ACK ON
<- BTN RELEASED
-> OFF
<- ACK OFF
^C
종료
```

- 스위치를 **누르고 있는 동안** LED가 켜져 있고, **떼면** 꺼지는 것을 확인한다.
- 한 번 눌렀을 때 `BTN PRESSED`가 **한 번만** 나오는지 확인한다. 여러 번 나오면 디바운싱이 제대로 되지 않은 것이다.

## 13.4 동작 순서 정리

```text
Jetson (Python)                                  Arduino
───────────────                                  ───────
readline() 대기 중 ...                           loop(): checkButton()
                                                 스위치 누름 → D6 = LOW (30ms 유지)
                              ◄─ "BTN PRESSED" ─ Serial.println("BTN PRESSED")
readline() → "BTN PRESSED"
write("ON\n")                 ─── "ON\n" ─────►  loop(): handleCommand()
                                                 digitalWrite(7, HIGH)  💡
                              ◄── "ACK ON" ───── Serial.println("ACK ON")
readline() → "ACK ON"

readline() 대기 중 ...                           스위치 뗌 → D6 = HIGH (30ms 유지)
                              ◄─ "BTN RELEASED"─ Serial.println("BTN RELEASED")
write("OFF\n")                ─── "OFF\n" ────►  digitalWrite(7, LOW)
                              ◄── "ACK OFF" ────
```

---

# 14. Part C~E — 조도센서·신호 필터링·서보모터 (개요)

자세한 설명과 단계별 실습은 강의 슬라이드를 따른다. 이 장은 배선과 실행 방법만 정리한다. 8장 스케치(Part C~E 확장판)를 업로드해 두었다면 Arduino 코드는 더 고칠 필요가 없다.

| 파트 | Python 프로그램 | Arduino에 보내는 명령 | 받는 메시지 |
|---|---|---|---|
| C. 조도센서 입력 | `light_read.py` | `STREAM ON` / `STREAM OFF` | `LIGHT <0~1023>` (0.1초마다) |
| D. 신호 필터링 | `light_filter.py` | `STREAM ON`, `ON` / `OFF` | `LIGHT <0~1023>`, `ACK ON/OFF` |
| E. 서보모터 제어 | `servo_control.py` | `SERVO <0~180>` | `ACK SERVO <각도>` |

세 프로그램 모두 `led_blink_serial.py`의 `find_arduino_port()`(와 `send()`)를 가져다 쓰므로 **같은 폴더**에 두고 실행한다.

## 14.1 조도센서 배선 (Part C·D)

조도센서(CdS)와 10kΩ 저항으로 **전압 분배** 회로를 만들어 **A0**에 연결한다.

```text
Arduino 5V ──── [CdS 조도센서] ──┬── [저항 10kΩ] ──── Arduino GND
                                 │
                             Arduino A0
```

- 밝으면 CdS 저항이 작아져 A0 전압이 올라간다 → `analogRead(A0)` 값이 **커진다**.
- `analogRead()`는 0~5V를 0~1023으로 바꾼다(10비트 ADC). 전압 = 값 × 5.0 / 1023.

## 14.2 서보모터 배선 (Part E)

| SG90 선 색 | 연결 |
|---|---|
| 갈색 | GND |
| 빨강 | 5V |
| 주황 | D9 (신호) |

서보는 움직이는 순간 전류를 많이 쓴다. Arduino가 리셋되거나 서보가 떨리면 16장을 참고한다.

## 14.3 실행

```bash
cd ~/Arduino
python3 light_read.py                         # Part C: 손으로 가리거나 빛을 비추며 값 변화 관찰
python3 light_filter.py --csv light.csv       # Part D: raw / MA / EMA 비교, 어두우면 LED ON
python3 light_filter.py --window 10 --alpha 0.2 --dark 300 --bright 400
python3 servo_control.py                      # Part E: 각도 직접 입력 (q: 종료)
python3 servo_control.py --sweep --step 30    # Part E: 0도 → 180도 → 0도 왕복
```

- **Part D 히스테리시스:** EMA가 `--dark`(300)보다 작아지면 LED를 켜고, `--bright`(400)보다 커져야 끈다. 기준값이 하나뿐이면 경계 근처에서 LED가 계속 깜빡이는데, 두 기준 사이에 간격을 두어 이를 막는다.
- `--csv`로 기록한 파일은 `time_s, raw, ma, ema, led` 열을 가진다. 그래프로 그리면 필터의 효과(잡음 감소와 지연)를 비교할 수 있다.
- 프로그램을 끝내면 `STREAM OFF`, `OFF`(Part D), `SERVO 90`(Part E)을 보내 원래 상태로 돌려놓는다.

---

# 15. 실습 과제

**과제 1. 응답 시간 측정**

`send()` 함수에서 `write()` 직전과 `readline()` 직후의 시간을 `time.perf_counter()`로 측정해, 명령 하나의 왕복 시간(RTT, Round-Trip Time)을 ms 단위로 출력하라. 10회 측정 평균을 구하라.

**과제 2. 통신 속도 변경**

Arduino의 `Serial.begin()`과 Python의 `--baud`를 `115200`으로 바꾸고 과제 1의 RTT를 다시 측정하라. 9600일 때와 비교하고 차이가 나는 이유를 설명하라.

> 한쪽만 바꾸면 어떤 결과가 나오는지도 확인해 보라.

**과제 3. 명령 추가**

`BLINK <n>` 명령을 추가하라. Arduino가 이 명령을 받으면 **스스로** LED를 n번 깜빡이고, 끝나면 `ACK BLINK <n>`을 응답하게 하라. Python에서 `ON/OFF`를 n번 보내는 방식과 비교해 장단점을 설명하라.

**과제 4. 잘못된 명령 처리**

Python에서 `HELLO`를 보내 `ERR HELLO` 응답이 오는지 확인하라. 그리고 `time.sleep(2)`를 지운 뒤 실행하면 어떤 일이 일어나는지 관찰하고 그 이유를 3.5절의 내용으로 설명하라.

**과제 5. 토글 스위치 (Part B)**

`button_led_serial.py`만 수정해서, 스위치를 **누를 때마다** LED가 켜짐 ↔ 꺼짐으로 바뀌게(토글) 하라. Arduino 스케치는 수정하지 않는다. 힌트: `BTN RELEASED`는 무시하고, LED 상태를 기억하는 변수를 사용한다.

**과제 6. 디바운싱 관찰 (Part B)**

스케치의 `DEBOUNCE_MS`를 `0`으로 바꿔 업로드한 뒤 스위치를 여러 번 눌러 보라. 한 번 누를 때 `BTN PRESSED`가 몇 번 출력되는지 기록하고, 3.6절의 내용으로 이유를 설명하라. 실험 후 `30`으로 되돌린다.

**과제 7. 반응 시간 측정 (Part B)**

`button_led_serial.py`에서 `BTN PRESSED`를 받은 시각부터 `ACK ON`을 받은 시각까지를 ms 단위로 측정해 출력하라. 이 시간은 스위치를 누른 뒤 LED가 켜지기까지 걸리는 시간 중 어느 부분에 해당하는가?

---

# 16. 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `ACK ON`/`ACK OFF` 응답은 오는데 LED가 안 켜짐 | LED 극성 반대, 핀 번호 불일치, 배선 접촉 불량 | LED 방향 확인(긴 다리 → D7 쪽), 스케치의 `LED_PIN`과 실제 핀 일치 확인 |
| `lsusb`에 Arduino가 없음 | 충전 전용 케이블, 접촉 불량 | 데이터 케이블로 교체, 다른 USB 포트 사용 |
| `/dev/ttyUSB0`가 생겼다가 바로 사라짐 (CH340 호환보드) | Ubuntu 22.04의 `brltty`(점자 단말 프로그램)가 장치를 가로챔 | `sudo apt remove -y brltty` 후 다시 연결 |
| `PermissionError: [Errno 13] Permission denied: '/dev/ttyACM0'` | `dialout` 그룹이 아니거나, 그룹 추가 후 다시 로그인하지 않음 | 6장 참고. `groups`에 `dialout`이 없으면 `newgrp dialout` 또는 VS Code 서버 재시작 |
| `아두이노: (READY 없음)` 이고 모든 명령이 `(응답 없음)` | Arduino에 스케치가 업로드되지 않음 | 9장의 업로드 수행 |
| 첫 명령만 응답 없음 | 리셋 대기 시간 부족 | `time.sleep(2)` 유지 또는 늘리기 |
| 응답이 깨진 글자 (`�x�`) | 양쪽 baud rate 불일치 | `Serial.begin()`과 `--baud` 값을 같게 |
| `Device or resource busy` | 다른 프로그램이 포트 사용 중 (시리얼 모니터, 다른 Python 실행) | 해당 프로그램 종료. `fuser /dev/ttyACM0`로 사용 중인 프로세스 확인 |
| `arduino-cli: command not found` | PATH에 `~/.local/bin`이 없음 | `export PATH=$HOME/.local/bin:$PATH` (9.1절) |
| 업로드 시 `programmer is not responding` | 포트를 다른 프로그램이 사용 중, 또는 FQBN 불일치 | Python 프로그램 종료 후 재시도. 호환 Nano는 `arduino:avr:nano:cpu=atmega328old` |
| Docker 컨테이너 안에서 포트가 안 보임 | 장치가 컨테이너에 전달되지 않음 | `docker run --device /dev/ttyACM0 ...` |
| 스위치를 눌러도 `BTN PRESSED`가 안 나옴 | 스위치 배선 오류, 같은 쪽 다리 2개 사용 | D6과 GND에 연결됐는지 확인. 택트 스위치는 **대각선 다리** 사용 (2.2절) |
| 누르지 않았는데 `BTN PRESSED`/`RELEASED`가 계속 나옴 | 10kΩ 풀업 저항 누락 또는 접촉 불량(핀이 떠 있음) | D6 열과 5V 사이 10kΩ 확인 (2.2절) |
| 누를 때 `RELEASED`, 뗄 때 `PRESSED`가 나옴 (반대로 동작) | 풀다운 방식으로 배선됨 (스위치가 5V 쪽에 연결) | 스위치를 D6 ↔ **GND**로 다시 배선 |
| 한 번 눌렀는데 `BTN PRESSED`가 여러 번 나옴 | 채터링 | `DEBOUNCE_MS` 값을 50 정도로 늘리기 |
| `ModuleNotFoundError: No module named 'led_blink_serial'` | 두 `.py` 파일이 다른 폴더에 있음 | `button_led_serial.py`, `light_read.py`, `light_filter.py`, `servo_control.py`를 `led_blink_serial.py`와 같은 폴더에 두고, 그 폴더에서 실행 |
| 컴파일 시 `Servo.h: No such file or directory` | Servo 라이브러리 미설치 | `arduino-cli lib install Servo` (9.2절) |
| `LIGHT` 값이 항상 0 또는 1023 근처 | 조도센서·10kΩ 전압 분배 배선 오류 | 5V → CdS → A0 → 10kΩ → GND 순서인지 확인 (14.1절) |
| 밝게 하면 값이 오히려 작아짐 | CdS와 10kΩ 위치가 서로 바뀜 | 두 부품 위치를 바꾸거나, 그대로 두고 판단 기준을 반대로 사용 |
| 서보가 떨리거나 Arduino가 리셋됨 | 서보가 순간적으로 큰 전류를 사용 | 배선 확인, USB 포트 바꾸기. 계속되면 서보 전원을 외부 5V로 분리(GND는 공통) |
