"""Part A — tools API 없이 '프롬프트 + JSON 파싱'으로 함수 호출 흉내 내기.

LLM에게 "도구가 필요하면 JSON 한 줄만 출력하라"고 지시하고,
Python이 그 JSON을 직접 해석해 함수를 실행한 뒤 결과를 다시 LLM에게 돌려준다.
(Function calling의 내부 원리를 눈으로 확인하는 단계)

사용 예:
    python3 fc_a_prompt_json.py
    python3 fc_a_prompt_json.py --url http://localhost:8080
종료: q 또는 Ctrl+C
"""
import argparse
import glob
import json
import re

import requests


# ---------------- 도구(실제 Python 함수) ----------------
def get_jetson_temperature():
    """/sys/class/thermal 아래 센서 온도(섭씨)를 읽는다."""
    temps = {}
    for zone in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
        try:
            name = open(f"{zone}/type").read().strip()
            temps[name] = int(open(f"{zone}/temp").read()) / 1000  # 밀리도 → 도
        except (OSError, ValueError, TypeError):  # cv0~2(비전 가속기)는 꺼져 있으면 읽기 실패
            continue
    return temps or {"error": "온도 센서를 읽지 못함"}


def get_memory_usage():
    """/proc/meminfo에서 전체·사용 가능 메모리(MB)를 읽는다."""
    info = {}
    try:
        for line in open("/proc/meminfo"):
            key, value = line.split(":")
            info[key] = int(value.split()[0]) // 1024  # kB → MB
    except OSError:
        return {"error": "메모리 정보를 읽지 못함"}
    total, avail = info["MemTotal"], info["MemAvailable"]
    return {"total_mb": total, "used_mb": total - avail, "available_mb": avail}


TOOLS = {
    "get_jetson_temperature": get_jetson_temperature,
    "get_memory_usage": get_memory_usage,
}

SYSTEM_PROMPT = """너는 Jetson Orin Nano 보드의 도우미다.
다음 도구를 사용할 수 있다.
- get_jetson_temperature(): 보드 각 부분의 온도(섭씨)를 돌려준다.
- get_memory_usage(): 전체/사용 중/사용 가능 메모리(MB)를 돌려준다.

도구가 필요하면 다른 말 없이 아래 형식의 JSON 한 줄만 출력하라.
{"tool": "<도구 이름>", "arguments": {}}
도구가 필요 없으면 한국어로 짧게 답하라."""


# ---------------- LLM 호출 ----------------
def chat(url, messages):
    resp = requests.post(
        f"{url}/v1/chat/completions",
        json={"messages": messages, "temperature": 0, "max_tokens": 256},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or ""


def parse_tool_request(text):
    """LLM 출력에서 {"tool": ...} JSON을 찾는다. 없으면 None."""
    match = re.search(r"\{.*\}", text, re.DOTALL)  # ```json ... ``` 으로 감싸도 찾는다
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and "tool" in data else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080", help="llama-server 주소")
    args = parser.parse_args()

    print("질문 예: 지금 보드 온도 어때? / 메모리 얼마나 남았어? / 안녕 (q: 종료)")
    while True:
        try:
            question = input("\n질문 > ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if question.lower() == "q":
            break
        if not question:
            continue

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        first = chat(args.url, messages)
        print(f"[LLM 1차 출력] {first}")

        request = parse_tool_request(first)
        if request is None:  # 도구 없이 바로 답한 경우
            print(f"답변: {first}")
            continue

        name = request["tool"]
        if name not in TOOLS:
            print(f"알 수 없는 도구: {name}")
            continue
        result = TOOLS[name]()  # ← 실제 함수 실행은 LLM이 아니라 Python이 한다
        print(f"[도구 실행] {name}() -> {result}")

        # 도구 결과를 대화에 덧붙여 최종 답변을 받는다.
        messages.append({"role": "assistant", "content": first})
        messages.append({
            "role": "user",
            "content": f"도구 결과: {json.dumps(result, ensure_ascii=False)}\n"
                       "이 결과를 바탕으로 원래 질문에 한국어로 답하라. JSON은 출력하지 마라.",
        })
        print(f"답변: {chat(args.url, messages)}")


if __name__ == "__main__":
    main()
