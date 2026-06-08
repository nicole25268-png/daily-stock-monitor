"""
DeepSeek AI 客户端 — 新闻摘要 + 投资建议 + 心态提醒
"""

import requests
import logging

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = "sk-12887a2b9fff4520bc4221aa97f80193"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def _call_deepseek(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """调用 DeepSeek API，返回文本"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": 2048,
    }
    try:
        resp = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=30)
        data = resp.json()
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"DeepSeek 调用失败: {e}")
    return ""


def summarize_news(news_list: list) -> str:
    """AI 摘要：选出最重要的 5 条，标签+分条+影响"""
    if not news_list:
        return ""

    news_text = "\n".join([f"- {n['title']}" for n in news_list[:20]])

    system = """你是资深金融新闻编辑。从下列财经快讯中选出对A股影响最大的5条。

每条格式：标签：摘要 — 影响：利好/利空/中性
标签用：政策/数据/利率/地缘/公司/商品
每条单独一行，不要编号，不要多余内容。"""

    return _call_deepseek(system, news_text, temperature=0.2)


def generate_advice(summary: dict, style: dict, portfolio_advice: dict) -> str:
    """AI 生成投资建议（全市场方向 + 持仓操作）"""
    context = f"""市场数据：
- 上证指数涨跌：{summary.get('shanghai', 0):+.2f}%
- 创业板指涨跌：{summary.get('chinext', 0):+.2f}%
- 上涨比例：{summary.get('up_ratio', 0)}%
- 涨停{summary.get('limit_up', 0)}家，跌停{summary.get('limit_down', 0)}家
- 成交额：{summary.get('total_amount_yi', 0):.0f}亿
- 北向资金：{summary.get('north_flow_yi', 0):+.1f}亿

涨幅前5板块：{', '.join([s['name'] for s in summary.get('sector_gainers', [])])}
跌幅前5板块：{', '.join([s['name'] for s in summary.get('sector_losers', [])])}

当前市场风格：{style.get('style', '未知')}（{style.get('desc', '')}）

持仓操作建议（规则引擎）：
买入：{portfolio_advice.get('buy', [])}
持有：{portfolio_advice.get('hold', [])}
卖出：{portfolio_advice.get('sell', [])}"""

    system = """你是一位经验丰富的A股投资顾问。请基于提供的市场数据，用简洁专业的语言输出：

1. 总体市场判断（1-2句）
2. 全市场加仓/减仓方向建议（句式：建议关注XXX板块，回避XXX板块）
3. 基于用户持仓的具体操作建议（如果数据中有持仓建议，基于它优化措辞）
4. 一句话风险提示

要求：简洁、专业、基于数据、不做具体个股推荐、不模棱两可。控制在200字以内。"""

    return _call_deepseek(system, context, temperature=0.3)


def generate_psych_tip(style: dict, daily_change: float) -> str:
    """AI 生成心态提醒（至少 3 句话）"""
    style_name = style.get("style", "中性")
    desc = style.get("desc", "")

    system = """你是一位资深投资心理教练。根据今天的市场状况，给投资者写一段心态提醒。

要求：
1. 至少 3 句话，每句之间用空行隔开
2. 第一句：共情——承认今天的市场带来的感受
3. 第二句：理性——回归到投资逻辑和长期视角
4. 第三句：行动——给一个具体的小建议（不要讲操作，讲心态）
5. 温暖但不煽情，冷静但不冷漠"""

    context = f"今天市场风格：{style_name}（{desc}）。上证指数涨跌：{daily_change:+.2f}%。"

    return _call_deepseek(system, context, temperature=0.7)
