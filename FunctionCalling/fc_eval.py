"""Function calling 정확도(에러율) 측정.

eval_set.jsonl의 명령을 하나씩 llama-server에 보내고, 모델이 돌려준 '첫 번째 도구 호출'을
정답과 비교한다. Part C(Arduino 에이전트)와 같은 도구 목록과 시스템 프롬프트를 쓴다.
실제 장치는 움직이지 않는다 (도구를 실행하지 않고 호출 내용만 채점).

채점 기준
    expect가 있는 문항: 첫 tool_call의 이름과 인자가 모두 같아야 정답
    expect가 []인 문항: tool_call이 없어야 정답 (없는 기능, 인사 등)

사용 예:
    python3 fc_eval.py --tag qwen3-1.7b
    python3 fc_eval.py --tag functiongemma --verbose
결과: results_<tag>.json 에 문항별 결과 저장
"""
import argparse
import json
import time

import requests

from fc_b_tools_api import chat
from fc_c_arduino_agent import SYSTEM_PROMPT, TOOLS


def first_call(msg):
    """assistant 메시지에서 첫 도구 호출을 (이름, 인자 dict)로 꺼낸다. 없으면 None."""
    calls = msg.get("tool_calls") or []
    if not calls:
        return None
    fn = calls[0]["function"]
    args = fn.get("arguments") or "{}"
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:  # 예: 같은 인자를 두 번 쓴 출력 → 오답 처리
            args = {"_raw": args}
    return fn["name"], args


def normalize(args):
    """'45'와 45, 'ON'과 'on'을 같은 값으로 본다."""
    out = {}
    for k, v in (args or {}).items():
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            v = int(v)
        elif isinstance(v, float) and v.is_integer():
            v = int(v)
        elif isinstance(v, str):
            v = v.strip().lower()
        out[k] = v
    return out


def grade(expect, got):
    """오류 종류를 돌려준다. 정답이면 'ok'."""
    if not expect:
        return "ok" if got is None else "unwanted_call"
    if got is None:
        return "no_call"
    name, args = got
    if name != expect[0]["name"]:
        return "wrong_tool"
    if normalize(args) != normalize(expect[0]["arguments"]):
        return "wrong_args"
    return "ok"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--data", default="eval_set.jsonl")
    parser.add_argument("--tag", default="model", help="결과 파일 이름에 붙일 모델 이름")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    items = [json.loads(line) for line in open(args.data, encoding="utf-8") if line.strip()]
    results, counts = [], {}
    total_sec = 0.0
    for i, item in enumerate(items, 1):
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": item["text"]}]
        t0 = time.time()
        try:
            msg, _ = chat(args.url, messages, TOOLS)  # Part B·C와 같은 요청 함수
        except (requests.RequestException, KeyError, ValueError) as e:
            msg = {"content": f"(요청 실패: {e})"}
        sec = time.time() - t0
        total_sec += sec

        got = first_call(msg)
        verdict = grade(item["expect"], got)
        counts[verdict] = counts.get(verdict, 0) + 1
        results.append({"text": item["text"], "expect": item["expect"], "got": got,
                        "content": msg.get("content"), "verdict": verdict, "sec": round(sec, 2)})
        mark = "O" if verdict == "ok" else "X"
        line = f"[{i:2d}/{len(items)}] {mark} {verdict:13s} {sec:5.1f}s  {item['text']}"
        if args.verbose or verdict != "ok":
            line += f"\n        정답: {item['expect'][:1]}  출력: {got}"
            if got is None and msg.get("content"):
                line += f"  content: {msg['content'][:80]!r}"
        print(line)

    n = len(items)
    ok = counts.get("ok", 0)
    print("\n===== 결과:", args.tag, "=====")
    print(f"정확도 {ok}/{n} = {ok / n * 100:.1f}%   에러율 {(n - ok) / n * 100:.1f}%")
    for k in ("no_call", "wrong_tool", "wrong_args", "unwanted_call"):
        print(f"  {k:13s}: {counts.get(k, 0)}")
    print(f"평균 응답 시간 {total_sec / n:.2f}s")

    with open(f"results_{args.tag}.json", "w", encoding="utf-8") as f:
        json.dump({"tag": args.tag, "accuracy": ok / n, "counts": counts,
                   "avg_sec": total_sec / n, "items": results}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
