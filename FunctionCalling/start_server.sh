#!/bin/bash
# Function Calling Lab.3 — llama-server(LLM 서버)를 켜고 끄는 스크립트
#
# 사용법:
#   ./start_server.sh qwen3-1.7b          Qwen3 1.7B (큰 범용 모델)
#   ./start_server.sh qwen3-0.6b          Qwen3 0.6B (작은 범용 모델)
#   ./start_server.sh functiongemma       FunctionGemma 270M (작은 전용 모델)
#   ./start_server.sh ft-functiongemma    파인튜닝한 FunctionGemma (~/models/functiongemma-arduino-Q8_0.gguf 필요)
#   ./start_server.sh ft-qwen3-0.6b       파인튜닝한 Qwen3 0.6B   (~/models/qwen3-0.6b-arduino-Q8_0.gguf 필요)
#   ./start_server.sh stop                서버 끄기
#
# 서버는 백그라운드(Docker 컨테이너 이름: fc_llm)에서 돈다. 로그 보기: docker logs -f fc_llm

IMAGE=ghcr.io/nvidia-ai-iot/llama_cpp:r36.4-tegra-aarch64-cu126-22.04   # JetPack 6(CUDA 12.6)용
NO_THINK="--reasoning-budget 0"   # Qwen3의 '생각하기' 단계를 끈다

case "$1" in
  qwen3-1.7b|qwen3)    ARGS="-hf Qwen/Qwen3-1.7B-GGUF:Q8_0 $NO_THINK" ;;
  qwen3-0.6b)          ARGS="-hf Qwen/Qwen3-0.6B-GGUF:Q8_0 $NO_THINK" ;;
  functiongemma)       ARGS="-hf unsloth/functiongemma-270m-it-GGUF:Q8_0" ;;
  ft-functiongemma|ft) FT_FILE="functiongemma-arduino-Q8_0.gguf"; ARGS="-m /models/$FT_FILE" ;;
  ft-qwen3-0.6b)       FT_FILE="qwen3-0.6b-arduino-Q8_0.gguf";    ARGS="-m /models/$FT_FILE $NO_THINK" ;;
  stop)                docker rm -f fc_llm > /dev/null 2>&1; echo "서버를 껐습니다."; exit 0 ;;
  *)  echo "사용법: $0 qwen3-1.7b | qwen3-0.6b | functiongemma | ft-functiongemma | ft-qwen3-0.6b | stop"; exit 1 ;;
esac

if [ -n "$FT_FILE" ] && [ ! -f "$HOME/models/$FT_FILE" ]; then
  echo "~/models/$FT_FILE 파일이 없습니다. 실습 문서 8장(Part E)을 먼저 진행하세요."; exit 1
fi

docker rm -f fc_llm > /dev/null 2>&1          # 이미 켜져 있는 서버가 있으면 끈다 (8080 포트는 하나만 쓸 수 있다)
mkdir -p "$HOME/.cache/huggingface" "$HOME/models"

docker run -d --name fc_llm \
  --runtime=nvidia \
  --network host \
  -v "$HOME/.cache/huggingface:/data/models/huggingface" \
  -v "$HOME/models:/models" \
  "$IMAGE" \
  llama-server $ARGS --jinja -c 4096 -ngl 99 --port 8080 > /dev/null || exit 1

echo "서버를 시작합니다: $1  (처음 실행할 때는 모델을 내려받느라 몇 분 걸릴 수 있습니다)"
for i in $(seq 1 120); do
  if curl -s localhost:8080/health | grep -q '"ok"'; then
    echo
    docker logs fc_llm 2>&1 | grep -E "offloaded"
    echo "준비 완료 → http://localhost:8080"
    exit 0
  fi
  if [ -z "$(docker ps -q -f name=fc_llm)" ]; then   # 컨테이너가 죽었으면 원인을 보여 준다
    echo
    echo "서버가 시작 중에 종료되었습니다. 마지막 로그:"
    docker logs fc_llm 2>&1 | tail -20
    exit 1
  fi
  sleep 3
  printf "."
done
echo
echo "6분 안에 준비되지 않았습니다. 'docker logs fc_llm'으로 확인하세요."
exit 1
