"""Part D 결과 파일에서 한국어 문항과 영어 문항의 정확도를 따로 계산한다.

fc_eval.py가 만든 results_<tag>.json은 {"tag", "accuracy", "counts", "avg_sec", "items"} 형식이며,
문항별 결과는 "items" 리스트에 들어 있다.

사용 예:
    python3 ko_score.py results_qwen3-1.7b_s3456.json
    for f in results_*_s3456.json; do echo $f; python3 ko_score.py $f; done
"""
import json
import re
import sys

r = json.load(open(sys.argv[1], encoding="utf-8"))["items"]
ko = [x for x in r if re.search("[가-힣]", x["text"])]
en = [x for x in r if x not in ko]
ok = lambda a: sum(x["verdict"] == "ok" for x in a)
print(f"한국어 {ok(ko)}/{len(ko)}   영어 {ok(en)}/{len(en)}")
