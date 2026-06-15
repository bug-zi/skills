from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from env_utils import load_project_env


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent

PLACEHOLDER_API_KEYS = {
    "",
    "sk-" + "your-key-here",
    "<openai-api-key>",
    "your-api-key",
    "your_openai_api_key",
    "replace-me",
}


def has_usable_openai_api_key(value: str | None = None) -> bool:
    key = (os.getenv("OPENAI_API_KEY") if value is None else value) or ""
    normalized = key.strip()
    if normalized.lower() in PLACEHOLDER_API_KEYS:
        return False
    if normalized.startswith("<") and normalized.endswith(">"):
        return False
    return bool(re.fullmatch(r"sk-[A-Za-z0-9_-]{20,}", normalized))


def parse_feature_status(output: str) -> str:
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "image_generation":
            return "enabled" if parts[-1].lower() == "true" else "disabled"
    return "missing"


def codex_command() -> list[str]:
    if os.name == "nt":
        for name in ("codex.cmd", "codex.exe", "codex.ps1"):
            path = shutil.which(name)
            if not path:
                continue
            if path.lower().endswith(".ps1"):
                shell = shutil.which("powershell") or shutil.which("pwsh")
                if shell:
                    return [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path]
                continue
            return [path]
    path = shutil.which("codex")
    return [path or "codex"]


def read_codex_feature_status() -> tuple[str, str]:
    try:
        result = subprocess.run(
            [*codex_command(), "features", "list"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except Exception as exc:
        return "unknown", str(exc)
    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    if result.returncode != 0:
        return "unknown", output.strip()
    return parse_feature_status(output), output.strip()


def build_readiness(*, feature_status: str, api_key_configured: bool, detail: str = "") -> dict:
    if feature_status == "enabled":
        next_action = (
            "当前 Codex feature flag 已开启。若当前会话暴露内置 image_gen 工具，优先用它生成 ai-report-guide.png；"
            "若本会话仍没有可调用工具且用户坚持 AI 导读图，则要求用户提供自己的 API Key。"
        )
        return {
            "feature_status": feature_status,
            "api_key_configured": api_key_configured,
            "can_try_builtin_imagegen": True,
            "requires_user_api_key": False,
            "next_action": next_action,
            "detail": detail,
        }
    if feature_status == "disabled":
        next_action = (
            "当前 Codex image_generation feature flag 未开启。可提示执行 `codex features enable image_generation`，"
            "并重启 Codex 或新开会话；若仍需要立即生成 AI 导读图，要求用户提供自己的 API Key。"
        )
        return {
            "feature_status": feature_status,
            "api_key_configured": api_key_configured,
            "can_try_builtin_imagegen": False,
            "requires_user_api_key": True,
            "next_action": next_action,
            "detail": detail,
        }
    next_action = (
        "无法确认 Codex 内置 image_generation 能力。Skill 不能安装宿主内置工具；"
        "若用户坚持 AI 导读图，要求用户提供自己的 API Key，否则使用 HTML 图文导览交付。"
    )
    return {
        "feature_status": feature_status,
        "api_key_configured": api_key_configured,
        "can_try_builtin_imagegen": False,
        "requires_user_api_key": not api_key_configured,
        "next_action": next_action,
        "detail": detail,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Codex image generation readiness for Website Health Inspector.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable readiness JSON.")
    parser.add_argument("--no-load-env", action="store_true", help="Do not load the skill-local .env file.")
    args = parser.parse_args()

    if not args.no_load_env:
        load_project_env(ROOT)
    feature_status, detail = read_codex_feature_status()
    payload = build_readiness(
        feature_status=feature_status,
        api_key_configured=has_usable_openai_api_key(),
        detail=detail,
    )
    payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"image_generation feature: {payload['feature_status']}")
    print(f"user API key configured: {payload['api_key_configured']}")
    print(f"can try built-in image_gen: {payload['can_try_builtin_imagegen']}")
    print(f"requires user API key for immediate AI image: {payload['requires_user_api_key']}")
    print(payload["next_action"])


if __name__ == "__main__":
    main()
