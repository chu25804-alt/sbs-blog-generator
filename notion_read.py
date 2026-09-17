"""
Notion DB에서 sbs-blog 관련 진행중 항목을 조회합니다.
Claude가 홈페이지 수정 전에 이 스크립트를 실행해 반영할 내용을 확인합니다.

사용: python notion_read.py
"""
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


def notion_request(url, method, payload, api_key, retries=5):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json; charset=utf-8",
    })
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


def extract_text(prop):
    if not prop:
        return ""
    t = prop.get("type", "")
    if t == "title":
        return "".join(r["plain_text"] for r in prop.get("title", []))
    if t == "rich_text":
        return "".join(r["plain_text"] for r in prop.get("rich_text", []))
    if t == "select":
        s = prop.get("select"); return s["name"] if s else ""
    if t == "multi_select":
        return ", ".join(s["name"] for s in prop.get("multi_select", []))
    if t == "date":
        d = prop.get("date"); return d["start"] if d else ""
    return ""


def main():
    env = load_env()
    api_key = env.get("NOTION_API_KEY")
    db_id = env.get("NOTION_DATABASE_ID")
    if not api_key or not db_id:
        print("[오류] .env에 NOTION_API_KEY / NOTION_DATABASE_ID가 없습니다.")
        sys.exit(1)

    payload = {
        "filter": {
            "property": "상태",
            "select": {"equals": "진행중"},
        },
        "sorts": [{"property": "날짜", "direction": "ascending"}],
    }

    results = []
    while True:
        resp = notion_request(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            "POST", payload, api_key
        )
        results.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        payload["start_cursor"] = resp["next_cursor"]

    if not results:
        print("진행중인 작업 항목이 없습니다.")
        return

    print(f"=== 진행중 항목 ({len(results)}건) ===\n")
    for page in results:
        props = page.get("properties", {})
        page_id = page["id"]
        name   = extract_text(props.get("이름", {}))
        date_  = extract_text(props.get("날짜", {}))
        tags   = extract_text(props.get("태그", {}))
        memo   = extract_text(props.get("메모", {}))

        print(f"ID: {page_id}")
        print(f"제목: {name}")
        if date_: print(f"날짜: {date_}")
        if tags:  print(f"태그: {tags}")
        if memo:  print(f"메모: {memo}")
        print("-" * 40)


if __name__ == "__main__":
    main()
