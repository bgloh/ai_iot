# Serial 통신 Lab.1 — Jetson ↔ Arduino LED 점멸

## 1. 실험 목적

본 실험의 목적은 Jetson Orin Nano와 Arduino Uno를 USB 케이블로 연결하고, Jetson에서 실행한 Python 프로그램(pyserial)이 시리얼 통신으로 명령을 보내 Arduino의 LED를 켜고 끄는 것이다.

이 실험을 통해 다음을 익힌다.

- 시리얼(UART) 통신의 기본 개념: 통신 속도(baud rate), 데이터 프레임, 줄바꿈 기반 메시지
- 리눅스에서 USB 시리얼 장치(`/dev/ttyACM0`)를 확인하고 접근 권한을 설정하는 방법
- `arduino-cli`로 Jetson에서 직접 Arduino 스케치를 컴파일하고 업로드하는 방법
- 명령(Command)과 응답(ACK)으로 이루어진 간단한 통신 프로토콜 설계

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
        ↓  USB 시리얼  "ON\n" / "OFF\n"
     Arduino Uno
        ├─ LED(13번 핀) 켜기/끄기
        └─ "ACK ON" / "ACK OFF" 응답
```

---

# 2. 실험 환경

본 실험에서 확인된 주요 환경은 다음과 같다.

```text
Host PC: Windows 11 + VS Code (Remote - SSH 확장)
Device: NVIDIA Jetson Orin Nano
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
| Arduino Uno R3 | 호환보드(CH340 칩)도 가능 — 14장 참고 |
| USB 케이블 | **데이터 전송용** 케이블. 충전 전용 케이블은 인식되지 않음 |
| PC | VS Code + Remote - SSH 확장 설치 |

추가 회로는 필요 없다. Uno 보드에 내장된 LED(보드에 **L**로 표시, 13번 핀)를 사용한다.

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

- 모든 메시지는 **줄바꿈 문자(`\n`)로 끝난다.** 수신 측은 줄바꿈이 올 때까지 읽으면 메시지 하나를 얻는다.
- 명령마다 응답(ACK)을 받으므로, Jetson은 Arduino가 명령을 제대로 처리했는지 확인할 수 있다.

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

```cpp
// Jetson에서 시리얼로 받은 명령으로 LED를 켜고 끈다.
// 명령: "ON\n", "OFF\n"  →  응답: "ACK ON", "ACK OFF"

const int LED_PIN = LED_BUILTIN;  // Uno/Nano 보드 내장 LED (13번 핀)

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial.begin(9600);
  Serial.println("READY");
}

void loop() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd == "ON") {
      digitalWrite(LED_PIN, HIGH);
      Serial.println("ACK ON");
    } else if (cmd == "OFF") {
      digitalWrite(LED_PIN, LOW);
      Serial.println("ACK OFF");
    } else if (cmd.length() > 0) {
      Serial.print("ERR ");
      Serial.println(cmd);
    }
  }
}
```

## 8.1 코드 설명

| 코드 | 설명 |
|---|---|
| `LED_BUILTIN` | 보드 내장 LED 핀 번호. Uno에서는 13번 |
| `pinMode(LED_PIN, OUTPUT)` | 13번 핀을 출력으로 설정 |
| `Serial.begin(9600)` | 시리얼 통신을 9600 bps로 시작. **Python 쪽과 같아야 함** |
| `Serial.println("READY")` | 부팅이 끝났음을 Jetson에 알림. `println`은 끝에 줄바꿈(`\r\n`)을 붙임 |
| `Serial.available()` | 수신 버퍼에 도착한 바이트 수. 0보다 크면 읽을 데이터가 있음 |
| `Serial.readStringUntil('\n')` | 줄바꿈이 올 때까지 읽어 문자열로 반환. 줄바꿈 자체는 포함하지 않음 |
| `cmd.trim()` | 앞뒤 공백과 `\r` 제거. 송신 측이 `\r\n`을 보내도 정상 동작하게 함 |
| `digitalWrite(LED_PIN, HIGH/LOW)` | LED 켜기 / 끄기 |
| `Serial.println("ACK ...")` | 명령 처리 결과를 Jetson에 응답 |

`setup()`은 전원이 켜지거나 리셋될 때 **한 번** 실행되고, `loop()`는 그 뒤로 **계속 반복** 실행된다.

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

## 9.3 컴파일

```bash
cd ~/Arduino
arduino-cli compile --fqbn arduino:avr:uno led_serial
```

```text
Sketch uses 3604 bytes (11%) of program storage space. Maximum is 32256 bytes.
Global variables use 224 bytes (10%) of dynamic memory, leaving 1824 bytes for local variables. Maximum is 2048 bytes.
```

Uno는 프로그램 저장 공간이 32 KB, RAM이 2 KB뿐이다. 이 스케치는 각각 11%, 10%를 사용한다.

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

# 10. Python 프로그램 작성

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
    ser.write((cmd + "\n").encode())
    reply = ser.readline().decode(errors="ignore").strip()
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

# 11. 실행 및 결과

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
- Arduino 보드의 **L** LED가 0.5초 간격으로 3번 깜빡이는 것을 눈으로 확인한다.

간격과 횟수를 바꿔 실행해 본다.

```bash
python3 led_blink_serial.py --count 10 --interval 0.2
```

---

# 12. 동작 순서 정리

```text
Jetson (Python)                                  Arduino
───────────────                                  ───────
serial.Serial() 로 포트 열기  ───(DTR 신호)───►  자동 리셋
time.sleep(2)                                    setup() 실행
                              ◄── "READY\r\n" ── Serial.println("READY")
readline() → "READY"

write("ON\n")                 ─── "ON\n" ─────►  readStringUntil('\n') → "ON"
                                                 digitalWrite(13, HIGH)  💡
                              ◄── "ACK ON\r\n" ─ Serial.println("ACK ON")
readline() → "ACK ON"
sleep(interval)

write("OFF\n")                ─── "OFF\n" ────►  digitalWrite(13, LOW)
                              ◄── "ACK OFF\r\n"─
   ... count 만큼 반복 ...

포트 닫기 (with 블록 종료)
```

---

# 13. 실습 과제

**과제 1. 응답 시간 측정**

`send()` 함수에서 `write()` 직전과 `readline()` 직후의 시간을 `time.perf_counter()`로 측정해, 명령 하나의 왕복 시간(RTT, Round-Trip Time)을 ms 단위로 출력하라. 10회 측정 평균을 구하라.

**과제 2. 통신 속도 변경**

Arduino의 `Serial.begin()`과 Python의 `--baud`를 `115200`으로 바꾸고 과제 1의 RTT를 다시 측정하라. 9600일 때와 비교하고 차이가 나는 이유를 설명하라.

> 한쪽만 바꾸면 어떤 결과가 나오는지도 확인해 보라.

**과제 3. 명령 추가**

`BLINK <n>` 명령을 추가하라. Arduino가 이 명령을 받으면 **스스로** LED를 n번 깜빡이고, 끝나면 `ACK BLINK <n>`을 응답하게 하라. Python에서 `ON/OFF`를 n번 보내는 방식과 비교해 장단점을 설명하라.

**과제 4. 잘못된 명령 처리**

Python에서 `HELLO`를 보내 `ERR HELLO` 응답이 오는지 확인하라. 그리고 `time.sleep(2)`를 지운 뒤 실행하면 어떤 일이 일어나는지 관찰하고 그 이유를 3.5절의 내용으로 설명하라.

---

# 14. 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
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
