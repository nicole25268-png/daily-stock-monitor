"""
飞书推送脚本 — 通过飞书应用 API 发送卡片消息
接收用户：张三（open_id），通过 Ticino 机器人推送
"""
import requests
import os
import sys
import json

APP_ID = "cli_aa9eadc2cebc9cd9"
APP_SECRET = "YhbBcVyktVdrzsF17Z5twctoidp4IAy1"
RECEIVE_ID = "ou_14ba26e2ec73e7f0c0e202e8a73d0634"

def get_token():
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10
    )
    return resp.json()["tenant_access_token"]

def send_text(text: str):
    token = get_token()
    msg = {
        "receive_id": RECEIVE_ID,
        "msg_type": "text",
        "content": json.dumps({"text": text})
    }
    resp = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=msg, timeout=10
    )
    return resp.json()

def send_card(title: str, content_md: str):
    """发送飞书卡片消息"""
    token = get_token()
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "indigo"
        },
        "elements": [{
            "tag": "markdown",
            "content": content_md
        }]
    }
    msg = {
        "receive_id": RECEIVE_ID,
        "msg_type": "interactive",
        "content": json.dumps(card)
    }
    resp = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=msg, timeout=10
    )
    return resp.json()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        text = sys.argv[1]
        result = send_text(text)
    else:
        result = send_card(
            "Ticino 每日盯盘 · 推送测试",
            "飞书推送通道已配置成功！\n\n每日 **14:30** 你将收到市场日报。\n\n**配置项**：\n- AI 模型：DeepSeek ✅\n- 数据源：AkShare ✅\n- 推送通道：飞书 Ticino ✅"
        )
    if result.get("code") == 0:
        print(f"[OK] Message sent, msg_id={result['data']['message_id']}")
    else:
        print(f"[FAIL] code={result.get('code')} msg={result.get('msg')}")
