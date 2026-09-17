"""
Notion DB 항목을 완료로 표시합니다.
사용: python notion_done.py --id <페이지ID>
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent
ENV_CANDIDATES = [
    REPO_ROOT / ".env",
    Path("C:/Users/user/OneDrive/바탕 화면/AI작업폴더/notion_agent/.env"),
]


def load_env():
    env = {}
    for path in ENV_CANDIDATES:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip())
    return env


def notion_patch(page_id, payload, api_key, retries=5):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.notion.com/v1/pages/{page_id}",
        data=data,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    wait = 1
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(wait); wait = min(wait * 2, 30)
            else:
                raise RuntimeError(f"HTTP {e.code}: {e.read().decode()}") from e
    raise RuntimeError("최대 재시도 초과")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Notion 페이지 ID")
    args = parser.parse_args()

    env = load_env()
    api_key = env.get("NOTION_API_KEY")
    if not api_key:
        print("[오류] .env에 NOTION_API_KEY가 없습니다.")
        sys.exit(1)

    notion_patch(args.id, {"properties": {"상태": {"select": {"name": "완료"}}}}, api_key)
    print(f"[Notion] {args.id} → 완료 처리됨")


if __name__ == "__main__":
    main()
