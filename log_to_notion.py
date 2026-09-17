"""
sbs-blog-generator 변경 이력을 Notion DB에 기록합니다.
- 이전 스냅샷과 현재 파일을 비교해 변경 내용을 자동 감지합니다.
- Claude Code가 파일 수정 후 자동으로 실행합니다.

수동 실행: python log_to_notion.py [--message "설명"] [--tags "태그1,태그2"]
"""
import argparse
import difflib
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent
SNAPSHOT_FILE = REPO_ROOT / ".notion_snapshot.json"
WATCH_FILES = ["index.html"]

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


def file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def load_snapshot() -> dict:
    if SNAPSHOT_FILE.exists():
        return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    return {}


def save_snapshot(snapshot: dict):
    SNAPSHOT_FILE.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def get_diff_summary(path: Path, old_content: str) -> str:
    if not path.exists():
        return "(파일 없음)"
    new_content = path.read_text(encoding="utf-8", errors="replace")
    old_lines = old_content.splitlines(keepends=True) if old_content else []
    new_lines = new_content.splitlines(keepends=True)

    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=""))
    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

    # 변경된 줄 내용 (최대 30줄)
    changed_lines = [l.rstrip() for l in diff if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
    preview = "\n".join(changed_lines[:30])
    if len(changed_lines) > 30:
        preview += f"\n… 외 {len(changed_lines) - 30}줄"

    summary = f"{path.name}: +{added} -{removed}줄\n\n{preview}"
    return summary[:1990]


def detect_tags(message: str) -> list:
    msg = message.lower()
    tags = []
    if any(w in msg for w in ["fix", "bug", "수정", "오류", "오타", "hotfix"]):
        tags.append("버그수정")
    if any(w in msg for w in ["add", "추가", "new", "신규", "기능"]):
        tags.append("기능추가")
    if any(w in msg for w in ["ui", "style", "디자인", "레이아웃", "css", "리뉴얼"]):
        tags.append("UI변경")
    if any(w in msg for w in ["과목", "course", "강의", "수업"]):
        tags.append("과목변경")
    if any(w in msg for w in ["프롬프트", "prompt", "template", "템플릿"]):
        tags.append("프롬프트")
    if any(w in msg for w in ["refactor", "리팩", "정리", "cleanup"]):
        tags.append("리팩토링")
    if not tags:
        tags.append("업데이트")
    return tags


def notion_post(payload: dict, api_key: str, db_id: str, retries: int = 5):
    payload["parent"] = {"database_id": db_id}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=data,
        method="POST",
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
                print(f"  요청 과다(429) — {wait}초 후 재시도 ({attempt+1}/{retries})")
                time.sleep(wait)
                wait = min(wait * 2, 30)
            else:
                body = e.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"HTTP {e.code}: {body}") from e
    raise RuntimeError("최대 재시도 횟수 초과")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", help="변경 요약 (없으면 자동 감지)")
    parser.add_argument("--tags", help="태그 (쉼표 구분, 없으면 자동 감지)")
    args = parser.parse_args()

    env = load_env()
    api_key = env.get("NOTION_API_KEY")
    db_id = env.get("NOTION_DATABASE_ID")
    if not api_key or not db_id:
        print("[Notion] .env에 NOTION_API_KEY / NOTION_DATABASE_ID가 없어 건너뜁니다.")
        sys.exit(0)

    snapshot = load_snapshot()
    changed_files = []
    diff_parts = []

    for fname in WATCH_FILES:
        path = REPO_ROOT / fname
        current_hash = file_hash(path)
        prev = snapshot.get(fname, {})
        prev_hash = prev.get("hash", "")

        if current_hash != prev_hash:
            changed_files.append(fname)
            old_content = prev.get("content", "")
            diff_parts.append(get_diff_summary(path, old_content))

    if not changed_files and not args.message:
        print("[Notion] 변경된 파일이 없어 건너뜁니다.")
        sys.exit(0)

    message = args.message or f"{', '.join(changed_files)} 업데이트"
    memo = "\n\n".join(diff_parts) if diff_parts else "(직접 입력)"
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else detect_tags(message)

    payload = {
        "properties": {
            "이름": {"title": [{"text": {"content": f"[sbs-blog] {message}"}}]},
            "상태": {"select": {"name": "완료"}},
            "날짜": {"date": {"start": date.today().isoformat()}},
            "메모": {"rich_text": [{"text": {"content": memo[:1990]}}]},
            "태그": {"multi_select": [{"name": t} for t in tags]},
        }
    }

    notion_post(payload, api_key, db_id)
    print(f"[Notion] 이력 저장 완료 → {message}")

    # 스냅샷 업데이트
    for fname in WATCH_FILES:
        path = REPO_ROOT / fname
        if path.exists():
            snapshot[fname] = {
                "hash": file_hash(path),
                "content": path.read_text(encoding="utf-8", errors="replace"),
            }
    save_snapshot(snapshot)
    print("[Notion] 스냅샷 갱신 완료")


if __name__ == "__main__":
    main()
