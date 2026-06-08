"""
飞书卡片消息推送模块
通过飞书应用 API 发送卡片消息到指定群聊/用户

使用方式：
1. 在飞书开放平台获取 App Secret
2. 将机器人加入目标群聊，获取 Chat ID
3. 程序自动获取 token 并发送卡片消息
"""

import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================
# 飞书应用配置（从环境变量/配置文件读取）
# ============================================================

FEISHU_APP_ID = "cli_aa9eadc2cebc9cd9"
FEISHU_APP_SECRET = ""  # TODO: 从飞书开放平台获取
FEISHU_CHAT_ID = ""     # TODO: 目标群聊 ID

FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"


def get_tenant_token() -> str:
    """获取飞书 tenant_access_token"""
    resp = requests.post(FEISHU_TOKEN_URL, json={
        "app_id": FEISHU_APP_ID,
        "app_secret": FEISHU_APP_SECRET,
    }, timeout=10)
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"获取 token 失败: {data}")
    return data["tenant_access_token"]


# ============================================================
# 卡片消息构造
# ============================================================

def build_card(data: dict, dashboard_url: str = "") -> dict:
    """
    构造飞书卡片消息
    涨红跌绿，5 条要闻，行业涨幅 TOP5，行业跌幅 TOP5，操作建议
    """
    summary = data.get("summary", {})
    style = data.get("style", {})
    top_news = data.get("top_news", [])
    port_advice = data.get("port_advice", {})
    psych_tip = data.get("psych_tip", "")
    sector_gainers = data.get("sector_gainers", [])
    sector_losers = data.get("sector_losers", [])
    generated_at = data.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # 构造涨跌幅 TOP5 文本
    gainers_text = "  |  ".join(
        [f"{s['name']} <font color='red'>+{s['change_pct']:.2f}%</font>"
         for s in sector_gainers[:5]]
    ) or "暂无数据"

    losers_text = "  |  ".join(
        [f"{s['name']} <font color='green'>{s['change_pct']:.2f}%</font>"
         for s in sector_losers[:5]]
    ) or "暂无数据"

    # 构造要闻列表
    news_lines = []
    for i, n in enumerate(top_news[:5], 1):
        tag = n.get("tag_cn", "")
        news_lines.append(f"**{i}.** [{tag}] {n['title']}")
    news_text = "\n".join(news_lines) if news_lines else "暂无重大要闻"

    # 构造操作建议
    buy_lines = "\n".join([f"✅ {b['name']}：{b['action']}" for b in port_advice.get("buy", [])])
    hold_lines = "\n".join([f"⏸️ {h['name']}：{h['action']}" for h in port_advice.get("hold", [])])
    sell_lines = "\n".join([f"🔻 {s['name']}：{s['action']}" for s in port_advice.get("sell", [])])

    advice_text = ""
    if buy_lines:
        advice_text += buy_lines + "\n"
    if hold_lines:
        advice_text += hold_lines + "\n"
    if sell_lines:
        advice_text += sell_lines + "\n"

    # 风格徽标
    style_emoji = {"多": "🔴", "偏多": "🟠", "中性": "🔵", "偏空": "🟡", "空": "🟢"}
    emoji = style_emoji.get(style.get("style", "中性"), "🔵")

    # 指数涨跌
    sh = summary.get("shanghai", 0)
    cy = summary.get("chinext", 0)
    sh_color = "red" if sh > 0 else "green"
    cy_color = "red" if cy > 0 else "green"

    content = [
        {"tag": "text", "text": f"{emoji} 总体风格：{style.get('style', '中性')}　{style.get('desc', '')}"},
        {"tag": "text", "text": "\n━━━━━━━━━━━━━━━━━━━━━"},
        {"tag": "text", "text": "\n📌 今日要闻\n" + news_text},
        {"tag": "text", "text": "\n━━━━━━━━━━━━━━━━━━━━━"},
        {"tag": "text", "text": f"\n📊 上证 <font color='{sh_color}'>{sh:+.2f}%</font>　创业板 <font color='{cy_color}'>{cy:+.2f}%</font>"},
        {"tag": "text", "text": f"\n涨跌比：{summary.get('up_count', 0)}↑ / {summary.get('down_count', 0)}↓　涨停：{summary.get('limit_up', 0)}　跌停：{summary.get('limit_down', 0)}"},
        {"tag": "text", "text": f"\n成交额：{summary.get('total_amount_yi', 0):.0f} 亿　北向：{summary.get('north_flow_yi', 0):+.1f} 亿"},
        {"tag": "text", "text": "\n━━━━━━━━━━━━━━━━━━━━━"},
        {"tag": "text", "text": "\n🔥 涨幅 TOP5\n" + gainers_text},
        {"tag": "text", "text": "\n💧 跌幅 TOP5\n" + losers_text},
    ]

    if advice_text.strip():
        content.append({"tag": "text", "text": "\n━━━━━━━━━━━━━━━━━━━━━"})
        content.append({"tag": "text", "text": "\n💡 持仓操作建议\n" + advice_text.strip()})

    content.append({"tag": "text", "text": "\n━━━━━━━━━━━━━━━━━━━━━"})
    content.append({"tag": "text", "text": f"\n🧘 {psych_tip}"})

    if dashboard_url:
        content.append({"tag": "text", "text": f"\n━━━━━━━━━━━━━━━━━━━━━"})
        content.append({"tag": "text", "text": f"\n📎 [查看完整看板]({dashboard_url})"})

    return {
        "receive_id": FEISHU_CHAT_ID,
        "msg_type": "post",
        "content": json_dumps({"zh_cn": {"title": f"每日盯盘 · {generated_at[:10]}", "content": content}}),
    }


import json as json_lib

def json_dumps(obj):
    return json_lib.dumps(obj, ensure_ascii=False)


def send_card(card: dict) -> bool:
    """发送飞书卡片消息"""
    if not FEISHU_APP_SECRET:
        logger.error("未配置 FEISHU_APP_SECRET，跳过推送")
        return False
    if not FEISHU_CHAT_ID:
        logger.error("未配置 FEISHU_CHAT_ID，跳过推送")
        return False

    try:
        token = get_tenant_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        resp = requests.post(FEISHU_MESSAGE_URL, headers=headers, json=card, timeout=10)
        result = resp.json()
        if result.get("code") == 0:
            logger.info(f"OK: 飞书推送成功 — message_id={result['data']['message_id']}")
            return True
        else:
            logger.error(f"飞书推送失败: {result}")
            return False
    except Exception as e:
        logger.error(f"飞书推送异常: {e}")
        return False


def push_daily_report(data: dict, dashboard_url: str = "") -> bool:
    """推送每日盯盘报告到飞书"""
    card = build_card(data, dashboard_url)
    return send_card(card)
