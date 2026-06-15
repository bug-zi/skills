#!/usr/bin/env bash
set -u

echo "===HOST==="
hostname 2>/dev/null || true
uname -a 2>/dev/null || true
cat /etc/os-release 2>/dev/null | sed -n '1,6p' || true

echo "===GPU==="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi
else
  echo "no_nvidia_smi"
fi

echo "===CONTAINERS==="
if command -v docker >/dev/null 2>&1; then
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
else
  echo "no_docker"
fi
if command -v podman >/dev/null 2>&1; then
  podman ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
else
  echo "no_podman"
fi

echo "===PROCESSES_LLM==="
ps -eo pid,ppid,comm,args --sort=comm \
  | grep -Ei 'ollama|vllm|sglang|lmdeploy|xinference|llama|llamacpp|text-generation|tgi|open-webui|litellm|one-api|chatglm|qwen|baichuan|modelscope|transformers|torchrun|fastchat|deepseek' \
  | grep -v grep || true

echo "===PORTS_COMMON==="
(ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null || true) \
  | grep -E ':(3000|5000|6006|7000|7860|8000|8001|8080|8081|8088|8888|9000|11434|1234)\b' || true

echo "===SERVICE_UNITS==="
if command -v systemctl >/dev/null 2>&1; then
  systemctl list-units --type=service --all --no-pager 2>/dev/null \
    | grep -Ei 'ollama|vllm|sglang|lmdeploy|xinference|llama|open-webui|litellm|one-api|tgi|text-generation|fastchat|model' || true
else
  echo "no_systemctl"
fi

echo "===MODEL_DIRS==="
for d in \
  /root/.ollama /home/*/.ollama \
  /root/.cache/huggingface /home/*/.cache/huggingface \
  /data/models /data/model /models /model /opt/models /srv/models \
  /root/models /home/*/models \
  /mnt/data/models /workspace/models; do
  if [ -e "$d" ]; then
    du -sh "$d" 2>/dev/null || true
    find "$d" -maxdepth 2 -type f \( -name '*.safetensors' -o -name '*.bin' -o -name '*.gguf' -o -name 'config.json' \) 2>/dev/null | head -30
  fi
done

echo "===PYTHON_PACKAGES_HINT==="
python3 - <<'PY' 2>/dev/null || true
import importlib.util
mods = ["torch", "transformers", "vllm", "sglang", "lmdeploy", "xinference", "llama_cpp", "modelscope", "openai", "litellm"]
for m in mods:
    print(f"{m}={'yes' if importlib.util.find_spec(m) else 'no'}")
PY

echo "===ENV_NAMES_ONLY==="
env | cut -d= -f1 \
  | grep -Ei 'OPENAI|ANTHROPIC|DASHSCOPE|QWEN|MODEL|OLLAMA|VLLM|CUDA|HF_|HUGGING|SILICON|DEEPSEEK|ZHIPU|ARK|VOLC|API_KEY|BASE_URL' \
  | sort || true
