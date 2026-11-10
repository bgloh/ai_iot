"""FunctionGemma 파인튜닝용 학습 데이터(train.jsonl) 생성.

Part C의 도구(set_led, set_servo, read_light)와 시스템 프롬프트를 그대로 사용해,
여러 가지 말투의 한국어/영어 명령과 정답 도구 호출을 템플릿으로 만들어 낸다.
평가 세트(eval_set.jsonl)와 같은 문장은 빼서, 외운 것이 아니라 일반화했는지 평가할 수 있게 한다.

각 줄 형식: {"messages": [system, user, (assistant 호출, tool 결과)..., 정답 assistant]}
마지막 assistant 메시지가 모델이 배워야 할 출력이다.

사용 예:
    python3 make_train_data.py              # train.jsonl 생성 (기본 1500개)
    python3 make_train_data.py --n 3000
"""
import argparse
import json
import random

from fc_c_arduino_agent import DARK_THRESHOLD, SYSTEM_PROMPT

# ---------------- 말투 재료 ----------------
LED_WORDS = ["LED", "엘이디", "led", "불", "조명", "라이트", "전등", "LED 불", "LED 조명"]
ON_VERBS = ["켜", "켜줘", "켜 줘", "켜주세요", "켜 주세요", "켜 줄래?", "켜라", "켜봐", "on 해줘",
            "켜 놔", "좀 켜줘", "켜 줄 수 있어?", "켜 주실래요?", "켜자", "on"]
OFF_VERBS = ["꺼", "꺼줘", "꺼 줘", "꺼주세요", "꺼 주세요", "꺼 줄래?", "꺼라", "꺼봐", "off 해줘",
             "꺼 놔", "좀 꺼줘", "꺼 줄 수 있어?", "꺼 주실래요?", "끄자", "off"]
EN_LED = ["LED", "light", "lamp"]
EN_ON = ["turn on the {x}", "switch the {x} on", "{x} on please", "please turn the {x} on", "power on the {x}"]
EN_OFF = ["turn off the {x}", "switch the {x} off", "{x} off please", "please turn the {x} off", "shut the {x} off"]

SERVO_WORDS = ["서보", "서보모터", "서보 모터", "모터", "servo", "서보를", "서보모터를", "모터를"]
ANGLE_PHRASES = ["{a}도로 돌려", "{a}도로 돌려줘", "{a}도", "{a}도로 맞춰", "각도 {a}", "{a}도 위치로",
                 "{a}도로 회전시켜", "{a}도까지 움직여", "{a}도로 이동", "{a}도로 세팅해줘", "{a}°로", "{a}도 해줘"]
CENTER_WORDS = ["가운데", "중앙", "중간", "정중앙", "센터"]
CENTER_PHRASES = ["{c}로 돌려", "{c}로 맞춰줘", "{c} 위치로", "{c}에 놓아줘", "{c}로 이동시켜"]
EN_SERVO = ["set the servo to {a} degrees", "rotate the servo to {a}", "servo {a} degrees", "move servo to {a}"]

LIGHT_PHRASES = ["조도 값 읽어줘", "밝기 측정해줘", "지금 밝아?", "얼마나 어두워?", "빛 센서 값 알려줘",
                 "조도센서 확인", "주변 밝기 알려줘", "조도 몇이야?", "지금 방 밝기는?", "밝기 좀 재 봐",
                 "조도 센서 값 보여줘", "여기 깜깜해?", "빛이 얼마나 들어와?", "조도 체크",
                 "light sensor reading", "is it dark now?", "how bright is it?", "check the light level"]

COND_DARK = ["어두우면", "깜깜하면", "어두운 경우", "빛이 부족하면"]
COND_BRIGHT = ["밝으면", "환하면", "밝은 경우", "빛이 충분하면"]
COND_PREFIX = ["", "조도 확인하고 ", "주변 밝기 보고 ", "센서 읽어서 ", "지금 "]

GREETINGS = ["안녕하세요", "안녕!", "반가워", "고마워요", "수고했어", "잘했어", "너 누구야?", "뭐 할 수 있어?",
             "도움말", "hello", "thanks", "넌 무슨 장치를 제어해?", "좋아", "ㅎㅎ", "사용법 알려줘"]
UNSUPPORTED = ["부저 켜줘", "스피커로 음악 틀어", "모터 속도 높여", "습도 알려줘", "온도 몇 도야?",
               "카메라로 사진 찍어", "날씨 알려줘", "이메일 보내줘", "LED 색깔 빨간색으로 바꿔",
               "서보 속도 바꿔", "선풍기 켜줘", "문 열어줘", "에어컨 꺼", "거리 센서 값 알려줘",
               "LED 밝기를 50%로", "2 곱하기 3은?", "오늘 무슨 요일이야?", "노래 불러줘",
               "play some music", "what's the temperature?"]
GREET_REPLY = "안녕하세요! 저는 LED, 서보모터, 조도센서를 제어할 수 있습니다. 무엇을 할까요?"
UNSUP_REPLY = "죄송하지만 그 기능은 이 장치에 없습니다. LED, 서보모터, 조도센서만 제어할 수 있습니다."


# ---------------- 메시지 만들기 ----------------
def call(name, **arguments):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"type": "function", "function": {"name": name, "arguments": arguments}}]}


def tool(name, result):
    return {"role": "tool", "name": name, "content": json.dumps(result, ensure_ascii=False)}


def say(text):
    return {"role": "assistant", "content": text}


def led_text(on):
    if random.random() < 0.15:
        return random.choice(EN_ON if on else EN_OFF).format(x=random.choice(EN_LED))
    word = random.choice(LED_WORDS)
    verb = random.choice(ON_VERBS if on else OFF_VERBS)
    obj = "을" if word in ("조명", "전등", "LED 조명", "불") else "를"  # 받침 있으면 '을'
    middle = random.choice([" ", " ", f"{obj} ", " 좀 "])
    return f"{word}{middle}{verb}"


def random_angle():
    r = random.random()
    if r < 0.15:
        return random.choice([0, 90, 180])
    if r < 0.7:
        return random.randrange(0, 181, 5)
    return random.randint(0, 180)


def servo_text(angle):
    if random.random() < 0.12:
        return random.choice(EN_SERVO).format(a=angle)
    return f"{random.choice(SERVO_WORDS)} {random.choice(ANGLE_PHRASES).format(a=angle)}"


def sample_led():
    on = random.random() < 0.5
    msgs = [{"role": "user", "content": led_text(on)}, call("set_led", state="on" if on else "off")]
    if random.random() < 0.3:  # 일부는 도구 결과 → 최종 보고까지 학습
        msgs += [tool("set_led", {"ok": True, "reply": "ACK ON" if on else "ACK OFF"}),
                 say("LED를 켰습니다." if on else "LED를 껐습니다.")]
    return msgs


def sample_servo():
    if random.random() < 0.15:
        angle = 90
        text = f"{random.choice(SERVO_WORDS)} {random.choice(CENTER_PHRASES).format(c=random.choice(CENTER_WORDS))}"
    else:
        angle = random_angle()
        text = servo_text(angle)
    msgs = [{"role": "user", "content": text}, call("set_servo", angle=angle)]
    if random.random() < 0.3:
        msgs += [tool("set_servo", {"ok": True, "reply": f"ACK SERVO {angle}"}),
                 say(f"서보모터를 {angle}도로 움직였습니다.")]
    return msgs


def sample_light():
    value = random.randint(20, 1000)
    dark = value < DARK_THRESHOLD
    msgs = [{"role": "user", "content": random.choice(LIGHT_PHRASES)}, call("read_light")]
    if random.random() < 0.5:
        msgs += [tool("read_light", {"value": value, "is_dark": dark}),
                 say(f"조도 값은 {value}로 {'어두운' if dark else '밝은'} 편입니다.")]
    return msgs


def sample_conditional():
    """'어두우면 LED 켜줘' → read_light → (결과에 따라) 동작 또는 그대로 두기."""
    want_dark = random.random() < 0.6
    cond = random.choice(COND_DARK if want_dark else COND_BRIGHT)
    kind = random.choice(["led_on", "led_off", "servo"])
    if kind == "servo":
        angle = random_angle()
        action_text = f"서보를 {angle}도로"
        action = call("set_servo", angle=angle)
        done = f"서보모터를 {angle}도로 움직였습니다"
        reply = f"ACK SERVO {angle}"
    else:
        on = kind == "led_on"
        action_text = f"{random.choice(LED_WORDS)} {random.choice(ON_VERBS if on else OFF_VERBS)}"
        action = call("set_led", state="on" if on else "off")
        done = "LED를 켰습니다" if on else "LED를 껐습니다"
        reply = "ACK ON" if on else "ACK OFF"
    text = f"{random.choice(COND_PREFIX)}{cond} {action_text}"
    msgs = [{"role": "user", "content": text}, call("read_light")]

    stage = random.random()
    if stage < 0.4:  # 1단계: 먼저 조도를 읽는다
        return msgs
    dark = random.random() < 0.5
    value = random.randint(20, DARK_THRESHOLD - 1) if dark else random.randint(DARK_THRESHOLD, 1000)
    msgs.append(tool("read_light", {"value": value, "is_dark": dark}))
    if dark == want_dark:  # 조건이 맞으면 동작
        msgs.append(action)
        if stage > 0.75:
            msgs += [tool(action["tool_calls"][0]["function"]["name"], {"ok": True, "reply": reply}),
                     say(f"조도 값이 {value}로 {'어두워서' if dark else '밝아서'} {done}.")]
    else:  # 조건이 안 맞으면 아무것도 하지 않는다
        msgs.append(say(f"조도 값이 {value}로 {'어두운' if dark else '밝은'} 상태라 아무것도 바꾸지 않았습니다."))
    return msgs


def sample_no_tool():
    if random.random() < 0.4:
        return [{"role": "user", "content": random.choice(GREETINGS)}, say(GREET_REPLY)]
    return [{"role": "user", "content": random.choice(UNSUPPORTED)}, say(UNSUP_REPLY)]


GENERATORS = [(sample_led, 0.25), (sample_servo, 0.25), (sample_light, 0.12),
              (sample_conditional, 0.23), (sample_no_tool, 0.15)]


def norm(s):
    return "".join(s.lower().split()).rstrip("?!.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1500)
    parser.add_argument("--out", default="train.jsonl")
    parser.add_argument("--eval", default="eval_set.jsonl")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    random.seed(args.seed)

    eval_texts = {norm(json.loads(l)["text"]) for l in open(args.eval, encoding="utf-8") if l.strip()}
    funcs, weights = zip(*GENERATORS)
    rows, skipped = [], 0
    while len(rows) < args.n:
        msgs = random.choices(funcs, weights)[0]()
        if norm(msgs[0]["content"]) in eval_texts:  # 평가 문장과 같으면 버린다
            skipped += 1
            continue
        rows.append({"messages": [{"role": "system", "content": SYSTEM_PROMPT}] + msgs})

    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    uniq = len({r["messages"][1]["content"] for r in rows})
    print(f"{args.out}: {len(rows)}개 (서로 다른 사용자 문장 {uniq}개, 평가 문장과 겹쳐 제외 {skipped}개)")


if __name__ == "__main__":
    main()
