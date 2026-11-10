"""Part C — 자연어로 Arduino를 제어하는 LLM 에이전트.

"LED 켜줘", "서보를 45도로", "지금 어두워? 어두우면 LED 켜줘" 같은 말을
LLM이 도구 호출(set_led, set_servo, read_light)로 바꾸고, Python이 Lab.1의
시리얼 명령(ON/OFF, SERVO <각도>, LIGHT)으로 Arduino를 움직인다.
Arduino 스케치는 Lab.1의 led_serial.ino를 그대로 사용한다.

사용 예:
    python3 fc_c_arduino_agent.py                    # 포트 자동 탐색
    python3 fc_c_arduino_agent.py --port /dev/ttyACM0
    python3 fc_c_arduino_agent.py --fake             # Arduino 없이 가짜 장치로 연습
종료: q 또는 Ctrl+C   /   대화 기록 지우기: reset
"""
import argparse
import random
import sys
import time

from fc_b_tools_api import answer

DARK_THRESHOLD = 300  # 조도 값이 이보다 작으면 '어두움' (Lab.1 배선: 밝을수록 값 증가)


# ---------------- Arduino 연결 ----------------
class Arduino:
    """Lab.1 프로토콜로 명령을 보내고 응답 한 줄을 받는다."""

    def __init__(self, port, baud=9600):
        import serial
        self.ser = serial.Serial(port, baud, timeout=2)
        time.sleep(2)  # 포트를 열면 Arduino가 리셋되므로 부팅을 기다린다
        print("아두이노:", self.ser.readline().decode(errors="ignore").strip() or "(READY 없음)")

    def query(self, cmd, expect=("ACK", "ERR")):
        """cmd를 보내고 expect로 시작하는 응답을 기다린다. 스위치 이벤트는 건너뛴다."""
        self.ser.write((cmd + "\n").encode())
        deadline = time.time() + 2
        while time.time() < deadline:
            line = self.ser.readline().decode(errors="ignore").strip()
            if line.startswith(expect):
                print(f"      시리얼 -> {cmd} | <- {line}")
                return line
            if line:
                print(f"      (이벤트: {line})")
        return "TIMEOUT"


class FakeArduino:
    """Arduino 없이 연습할 때 쓰는 가짜 장치."""

    def __init__(self):
        self.light = random.randint(100, 900)
        print(f"가짜 Arduino 사용 (조도 값 {self.light})")

    def query(self, cmd, expect=("ACK", "ERR")):
        if cmd in ("ON", "OFF"):
            reply = f"ACK {cmd}"
        elif cmd.startswith("SERVO "):
            reply = f"ACK {cmd}"
        elif cmd == "LIGHT":
            reply = f"LIGHT {self.light}"
        else:
            reply = f"ERR {cmd}"
        print(f"      (가짜) 시리얼 -> {cmd} | <- {reply}")
        return reply


# ---------------- 도구 정의 ----------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_led",
            "description": "Arduino에 연결된 LED를 켜거나 끈다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "enum": ["on", "off"],
                              "description": "on이면 켜기, off면 끄기"},
                },
                "required": ["state"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_servo",
            "description": "서보모터를 지정한 각도로 회전시킨다. 90도가 가운데다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "angle": {"type": "integer", "minimum": 0, "maximum": 180,
                              "description": "목표 각도(0~180도)"},
                },
                "required": ["angle"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_light",
            "description": "조도센서 값을 읽는다. 0~1023이며 클수록 밝다. 어두운지 판단할 때 사용한다.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM_PROMPT = f"""너는 Jetson에 연결된 Arduino 장치를 제어하는 도우미다.
장치: LED 1개, 서보모터 1개(0~180도), 조도센서 1개(0~1023, 클수록 밝음, {DARK_THRESHOLD} 미만이면 어두움).
사용자의 요청을 수행하려면 반드시 도구를 호출하라. 도구 결과를 확인한 뒤 한국어로 짧게 보고하라.
장치에 없는 기능을 요청하면 할 수 없다고 답하라."""


def make_functions(dev):
    """도구 이름 → 실제 동작 함수. LLM이 준 인자는 여기서 다시 검사한다."""

    def set_led(state):
        if state not in ("on", "off"):
            return {"error": "state는 on 또는 off"}
        reply = dev.query("ON" if state == "on" else "OFF")
        return {"ok": reply.startswith("ACK"), "reply": reply}

    def set_servo(angle):
        angle = int(angle)
        if not 0 <= angle <= 180:  # 모델을 믿지 말고 범위를 직접 검사한다
            return {"error": f"각도 {angle}는 범위(0~180)를 벗어남"}
        reply = dev.query(f"SERVO {angle}")
        return {"ok": reply.startswith("ACK"), "reply": reply}

    def read_light():
        reply = dev.query("LIGHT", expect=("LIGHT",))
        try:
            value = int(reply.split()[1])  # "LIGHT 523" → 523
        except (IndexError, ValueError):
            return {"error": f"조도 값을 읽지 못함: {reply}"}
        return {"value": value, "is_dark": value < DARK_THRESHOLD}

    return {"set_led": set_led, "set_servo": set_servo, "read_light": read_light}


def find_arduino_port():
    from serial.tools import list_ports
    for p in list_ports.comports():
        if "ttyACM" in p.device or "ttyUSB" in p.device:
            return p.device
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080", help="llama-server 주소")
    parser.add_argument("--port", help="예: /dev/ttyACM0 (생략하면 자동 탐색)")
    parser.add_argument("--fake", action="store_true", help="Arduino 없이 가짜 장치 사용")
    parser.add_argument("--show-json", action="store_true", help="LLM 응답 JSON 원문 출력")
    args = parser.parse_args()

    if args.fake:
        dev = FakeArduino()
    else:
        port = args.port or find_arduino_port()
        if port is None:
            sys.exit("아두이노 포트를 찾지 못했습니다. --port로 지정하거나 --fake로 실행하세요.")
        dev = Arduino(port)
    functions = make_functions(dev)

    # 대화 기록을 유지하므로 "다시 꺼줘"처럼 앞 대화를 이어서 말할 수 있다.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("명령 예: LED 켜줘 / 서보 45도로 돌려 / 어두우면 LED 켜줘 (reset: 기록 삭제, q: 종료)")
    try:
        while True:
            try:
                text = input("\n명령 > ").strip()
            except EOFError:
                break
            if text.lower() == "q":
                break
            if text.lower() == "reset":
                messages = messages[:1]
                print("대화 기록을 지웠습니다.")
                continue
            if not text:
                continue
            messages.append({"role": "user", "content": text})
            t0 = time.time()
            reply = answer(args.url, messages, TOOLS, functions, args.show_json)
            print(f"답변: {reply}   (총 {time.time() - t0:.1f}s)")
    except KeyboardInterrupt:
        print("\n중단됨")
    finally:
        dev.query("OFF")  # 끝낼 때 LED를 끄고 서보를 가운데로 돌려놓는다
        dev.query("SERVO 90")


if __name__ == "__main__":
    main()
