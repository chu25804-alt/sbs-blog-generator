"""
Claude Code PostToolUse 훅.
Write/Edit 도구가 sbs-blog-generator 파일에 실행된 후 자동으로 Notion에 이력을 기록합니다.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent
TRIGGER_DIR = str(REPO_ROOT).replace("\\", "/").lower()


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    tool_input = data.get("tool_input", {})
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("path")
        or ""
    ).replace("\\", "/").lower()

    if not file_path:
        return

    if TRIGGER_DIR not in file_path:
        return

    # index.html 이 아닌 파일은 무시 (log_to_notion.py 자체 수정 등)
    tracked = ["index.html"]
    if not any(f in file_path for f in tracked):
        return

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "log_to_notion.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0 and result.stderr:
        print(f"[Notion Hook 오류] {result.stderr}", file=sys.stderr)


if __name__ == "__main__":
    main()
