"""Part B — OpenAI 호환 tools API로 함수 호출하기.

도구 목록을 JSON Schema로 llama-server에 알려 주면, 모델이 호출할 함수와 인자를
`tool_calls` 필드로 돌려준다. Python이 함수를 실행하고 결과를 role="tool" 메시지로
돌려주면, 모델이 최종 답변을 만든다.

    사용자 질문 → LLM ─tool_calls→ Python 함수 실행 ─role:tool→ LLM → 최종 답변

llama-server는 --jinja 옵션으로 실행해야 한다.

사용 예:
    python3 fc_b_tools_api.py
    python3 fc_b_tools_api.py --show-json      # 주고받는 JSON 원문 보기
종료: q 또는 Ctrl+C
"""
import argparse
import json
import re
import time

import requests

from fc_a_prompt_json import get_jetson_temperature, get_memory_usage

MAX_STEPS = 5  # 한 질문에서 도구를 호출할 수 있는 최대 횟수 (무한 반복 방지)

# 모델에게 보여 줄 도구 설명서 (JSON Schema)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_jetson_temperature",
            "description": "Jetson 보드 각 부분(CPU, GPU 등)의 현재 온도를 섭씨로 돌려준다.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_memory_usage",
            "description": "Jetson의 전체, 사용 중, 사용 가능 메모리를 MB 단위로 돌려준다.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

# 도구 이름 → 실제 Python 함수
FUNCTIONS = {
    "get_jetson_temperature": get_jetson_temperature,
    "get_memory_usage": get_memory_usage,
}

SYSTEM_PROMPT = "너는 Jetson Orin Nano 보드의 도우미다. 필요하면 도구를 사용하고, 한국어로 짧게 답하라."


# FunctionGemma 호출 형식: <start_function_call>call:set_led{state:<escape>on<escape>}<end_function_call>
FG_CALL = re.compile(r"<start_function_call>\s*call:(\w+)\{(.*?)\}?\s*(?:<end_function_call>|$)", re.S)
FG_ARG = re.compile(r"(\w+):(?:<escape>(.*?)<escape>|([^,}]*))", re.S)


def parse_functiongemma(content):
    """서버가 tool_calls로 바꿔 주지 못한 FunctionGemma 출력을 직접 해석한다 (Part A와 같은 원리)."""
    m = FG_CALL.search(content or "")
    if not m:
        return []
    args = {}
    for key, text, raw in FG_ARG.findall(m.group(2)):
        if key in args:  # 같은 인자를 두 번 쓴 출력은 잘못된 호출로 본다
            return [{"id": "fg0", "type": "function",
                     "function": {"name": m.group(1), "arguments": "INVALID: " + m.group(2)}}]
        value = text if text else raw.strip()
        args[key] = int(value) if value.lstrip("-").isdigit() else value
    return [{"id": "fg0", "type": "function",
             "function": {"name": m.group(1), "arguments": json.dumps(args, ensure_ascii=False)}}]


def chat(url, messages, tools, show_json=False):
    """llama-server에 요청하고 (assistant 메시지, 걸린 시간)을 돌려준다."""
    body = {"messages": messages, "tools": tools, "temperature": 0, "max_tokens": 256,
            # FunctionGemma는 호출 뒤에도 멈추지 않는 경우가 있어 호출 끝 표시에서 멈춘다.
            "stop": ["<end_function_call>"]}
    t0 = time.time()
    resp = requests.post(f"{url}/v1/chat/completions", json=body, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    if show_json:
        print("   [응답 JSON]", json.dumps(data["choices"][0], ensure_ascii=False, indent=2))
    msg = data["choices"][0]["message"]
    if not msg.get("tool_calls"):
        calls = parse_functiongemma(msg.get("content"))
        if calls:
            msg = {"role": "assistant", "content": "", "tool_calls": calls}
    return msg, time.time() - t0


def run_tool_call(call, functions):
    """tool_call 하나를 실행하고 결과(dict)를 돌려준다. 오류도 결과로 돌려준다."""
    name = call["function"]["name"]
    try:
        arguments = json.loads(call["function"].get("arguments") or "{}")
    except json.JSONDecodeError:
        return {"error": "arguments가 올바른 JSON이 아님"}
    if name not in functions:
        return {"error": f"알 수 없는 도구: {name}"}
    try:
        return functions[name](**arguments)
    except Exception as e:  # 잘못된 인자 등 — 프로그램을 멈추지 않고 모델에게 알린다
        return {"error": str(e)}


def answer(url, messages, tools, functions, show_json=False):
    """도구 호출이 끝날 때까지 LLM ↔ Python을 반복하고 최종 답변을 돌려준다."""
    for step in range(1, MAX_STEPS + 1):
        msg, sec = chat(url, messages, tools, show_json)
        calls = msg.get("tool_calls") or []
        print(f"   [LLM {step}회차, {sec:.1f}s] tool_calls {len(calls)}개")

        if not calls:  # 도구 호출이 없으면 최종 답변
            messages.append({"role": "assistant", "content": msg.get("content") or ""})
            return msg.get("content") or ""

        # 모델의 호출 요청을 대화 기록에 남긴다 (다음 요청에 꼭 필요).
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": calls})
        for call in calls:
            result = run_tool_call(call, functions)
            print(f"   [도구] {call['function']['name']}"
                  f"({call['function'].get('arguments') or ''}) -> {result}")
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "name": call["function"]["name"],  # FunctionGemma 템플릿은 name이 꼭 필요하다
                "content": json.dumps(result, ensure_ascii=False),
            })
    return "(도구 호출 횟수 제한에 걸려 중단했습니다)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080", help="llama-server 주소")
    parser.add_argument("--show-json", action="store_true", help="LLM 응답 JSON 원문 출력")
    args = parser.parse_args()

    print("질문 예: 지금 보드 온도 어때? / 메모리랑 온도 둘 다 알려줘 (q: 종료)")
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
        print(f"답변: {answer(args.url, messages, TOOLS, FUNCTIONS, args.show_json)}")


if __name__ == "__main__":
    main()
