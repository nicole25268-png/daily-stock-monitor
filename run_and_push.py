"""
运行大盘复盘 + 飞书推送
替代项目内置的飞书 SDK（认证有问题），用直接 REST API 推送
"""
import subprocess, sys, os, glob, requests, json

APP_ID = "cli_aa9eadc2cebc9cd9"
APP_SECRET = "YhbBcVyktVdrzsF17Z5twctoidp4IAy1"
RECEIVE_ID = "ou_14ba26e2ec73e7f0c0e202e8a73d0634"

def get_token():
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10
    )
    return r.json()["tenant_access_token"]

def push_report(filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Truncate if too long (Feishu card limit ~30KB)
    if len(content) > 8000:
        content = content[:8000] + "\n\n...\n[报告过长，已截断。完整报告见日志]"

    # Convert markdown to Feishu-compatible format
    # Remove emojis that might cause issues, keep basic markdown
    title = content.split("\n")[0].replace("# ", "").strip() if content else "大盘复盘"

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title[:50]},
            "template": "indigo"
        },
        "elements": [{
            "tag": "markdown",
            "content": content[:6000]
        }]
    }

    token = get_token()
    msg = {
        "receive_id": RECEIVE_ID,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False)
    }
    r = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=msg, timeout=10
    )
    return r.json()

if __name__ == "__main__":
    # Step 1: Run market review
    print("[1/2] Running market review...")
    subprocess.run([
        sys.executable, "main.py",
        "--market-review", "--force-run", "--no-notify"
    ], check=True)

    # Step 2: Find latest report and push
    print("[2/2] Pushing to Feishu...")
    reports = sorted(glob.glob("reports/market_review_*.md"), reverse=True)
    if reports:
        result = push_report(reports[0])
        if result.get("code") == 0:
            print(f"[OK] Pushed: {reports[0]}")
        else:
            print(f"[FAIL] {result.get('code')}: {result.get('msg')}")
            sys.exit(1)
    else:
        print("[FAIL] No report found")
        sys.exit(1)
