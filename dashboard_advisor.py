"""
规则引擎 — 投资建议 + 心态提醒
无 AI API 依赖，基于市场数据和持仓结构生成建议
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================
# 市场风格判断
# ============================================================

def determine_style(summary: dict, commodities_change: float = 0) -> dict:
    """
    判断总体风格：多/空/中性
    返回 style 字典
    """
    sh = summary.get("shanghai", 0)
    cy = summary.get("chinext", 0)
    up_ratio = summary.get("up_ratio", 50)
    sentiment = summary.get("sentiment", "neutral")
    sector_losers = summary.get("sector_losers", [])

    # 跌的板块中是否有资源/科技（风险资产）
    loser_names = [s["name"] for s in sector_losers]
    risk_assets_hit = any(k in "".join(loser_names) for k in ["有色", "化工", "电子", "计算机", "半导体"])

    # 综合判断
    score = 0
    if sh < -0.5:
        score -= 1
    if cy < -1.5:
        score -= 1
    if up_ratio < 40:
        score -= 1
    if risk_assets_hit:
        score -= 1
    if sentiment == "bearish":
        score -= 2

    if score <= -3:
        style = "空"
        color = "bearish"
        desc = "市场风险偏好收缩，以防御为主"
    elif score <= -1:
        style = "偏空"
        color = "cautious"
        desc = "市场偏谨慎，控制仓位，精选防御品种"
    elif score >= 3:
        style = "多"
        color = "bullish"
        desc = "市场情绪乐观，可适度进攻"
    elif score >= 1:
        style = "偏多"
        color = "positive"
        desc = "市场偏乐观，维持持仓，关注轮动"
    else:
        style = "中性"
        color = "neutral"
        desc = "市场方向不明，观望为主"

    return {"style": style, "color": color, "desc": desc, "score": score}


# ============================================================
# 全市场加减仓建议（行业方向）
# ============================================================

def market_sector_advice(summary: dict) -> dict:
    """基于当日行业表现给出全市场加减仓方向"""
    gainers = summary.get("sector_gainers", [])
    losers = summary.get("sector_losers", [])
    sentiment = summary.get("sentiment", "neutral")

    g_names = [g["name"] for g in gainers]
    l_names = [l["name"] for l in losers]

    add_sectors = []
    hold_sectors = []
    reduce_sectors = []

    # 防御品种（防御风格下优先推荐）
    defensive = ["银行", "煤炭", "公用事业", "交通运输", "电力"]
    # 进攻品种（风险偏好高时推荐）
    offensive = ["电子", "计算机", "半导体", "通信", "传媒"]
    # 周期品种（宏观不确定性下谨慎）
    cyclical = ["有色金属", "化工", "钢铁", "建筑材料"]
    # 稳健消费
    consumer = ["食品饮料", "医药生物", "家用电器"]

    if sentiment in ("bearish", "neutral_negative"):
        # 偏空：推荐防御，减仓周期和进攻
        for s in defensive:
            if s in l_names:
                add_sectors.append({"name": s, "reason": "防御品种被错杀，逢低布局"})
            elif s in g_names:
                add_sectors.append({"name": s, "reason": "资金避险方向，顺势持有"})
        for s in cyclical:
            if s in l_names:
                reduce_sectors.append({"name": s, "reason": "宏观承压，反弹减仓"})
    elif sentiment in ("bullish", "neutral_positive"):
        for s in offensive:
            if s in g_names:
                add_sectors.append({"name": s, "reason": "进攻方向强势，顺势而为"})
        for s in defensive:
            if s in g_names:
                reduce_sectors.append({"name": s, "reason": "防御涨多，可分批止盈"})
    else:
        # 中性
        for s in consumer:
            if s in l_names:
                add_sectors.append({"name": s, "reason": "消费防御属性，逢低关注"})

    return {
        "add": add_sectors[:5],
        "hold": hold_sectors[:3],
        "reduce": reduce_sectors[:5],
    }


# ============================================================
# 持仓操作建议（基于你的 21 只基金）
# ============================================================

# 持仓分类
PORTFOLIO = {
    "defensive": {
        "华夏电网设备": {"pct": 9.64, "pnl": 4.58},
        "绿色电力": {"pct": 3.52, "pnl": 9.58},
        "红利低波": {"pct": 1.93, "pnl": -2.42},
    },
    "growth": {
        "数字经济": {"pct": 4.40, "pnl": 16.94},
        "科创板芯片": {"pct": 3.07, "pnl": -3.22},
        "创业板": {"pct": 2.82, "pnl": 7.09},
        "人工智能": {"pct": 1.78, "pnl": -9.99},
    },
    "cyclical_risk": {
        "金银珠宝": {"pct": 9.50, "pnl": -19.11},
        "工业有色": {"pct": 7.99, "pnl": -9.06},
        "中欧化工": {"pct": 7.42, "pnl": -6.15},
        "天弘化工": {"pct": 5.39, "pnl": -9.06},
        "黄金ETF": {"pct": 3.96, "pnl": 0.27},
    },
    "special_situations": {
        "A500增强": {"pct": 8.22, "pnl": 3.96},
        "港股通成长": {"pct": 7.42, "pnl": 2.36},
        "港股创新药": {"pct": 6.38, "pnl": -21.15},
        "战略转型": {"pct": 4.26, "pnl": -19.07},
        "恒生互联网": {"pct": 3.92, "pnl": -25.77},
        "自由现金流": {"pct": 2.93, "pnl": -11.04},
        "证券ETF": {"pct": 2.10, "pnl": -20.24},
        "光伏": {"pct": 1.99, "pnl": 0.70},
        "碳中和": {"pct": 1.38, "pnl": 4.38},
    },
}

def portfolio_advice(summary: dict, style: dict) -> dict:
    """基于市场风格给出你的持仓操作建议"""
    sentiment = summary.get("sentiment", "neutral")
    sector_losers = summary.get("sector_losers", [])

    buy_list = []
    hold_list = []
    sell_list = []

    # 防御风格：买防御、卖周期
    if sentiment in ("bearish", "neutral_negative"):
        buy_list.append({
            "name": "红利低波",
            "action": "加仓 1000",
            "reason": "防御底仓，降低组合波动"
        })
        buy_list.append({
            "name": "华夏电网设备",
            "action": "跌≥2% 加 1000",
            "reason": "政策驱动，与利率无关"
        })
        hold_list.append({
            "name": "金银珠宝/工业有色/化工",
            "action": "不动等反弹减仓",
            "reason": "资源品承压，不加仓，反弹换马"
        })
        hold_list.append({
            "name": "恒生互联/创新药/证券",
            "action": "不动等回本",
            "reason": "仓位小，时间换空间"
        })
        sell_list.append({
            "name": "战略转型（房地产）",
            "action": "反弹至-10%以内清仓",
            "reason": "房地产逻辑坏了，趁反弹换到红利"
        })

    elif sentiment in ("bullish", "neutral_positive"):
        buy_list.append({
            "name": "科创板芯片/人工智能",
            "action": "回调 3% 轻仓参与",
            "reason": "进攻方向顺势"
        })
        hold_list.append({
            "name": "数字经济/创业板",
            "action": "持有不动",
            "reason": "盈利趋势良好"
        })
        sell_list.append({
            "name": "红利低波",
            "action": "涨超 5% 减半仓",
            "reason": "防御涨多了止盈"
        })

    else:
        hold_list.append({
            "name": "所有持仓",
            "action": "观望不动",
            "reason": "市场方向不明，等 FOMC 后再决策"
        })

    return {"buy": buy_list, "hold": hold_list, "sell": sell_list}


# ============================================================
# 心态提醒
# ============================================================

PSYCH_TIPS = {
    "bearish": [
        "市场短期是投票机，长期是称重机。电网 4 万亿投资不会因为非农超预期就取消。",
        "历史上每次恐慌性抛售，回头看都是机会。前提是你没有在恐慌中割肉。",
        "黄金的央行购金趋势没有逆转，金矿股的回调是暂时的。耐心等 FOMC 靴子落地。",
    ],
    "cautious": [
        "防御不是逃跑，是为了在风暴中活下来，风暴过后才有弹药进攻。",
        "你现在做的事——调整结构而不是恐慌割肉——本身就是正确的。",
        "记好每一笔操作的理由，三个月后回看，你会发现今天的冷静多值钱。",
    ],
    "neutral": [
        "方向不明时，什么都不做往往是最好的操作。",
        "手上有弹药、持仓有逻辑，就没什么好慌的。",
    ],
    "positive": [
        "涨了不要飘。按计划止盈，不要因为一根阳线就改变交易纪律。",
        "反弹不是反转。利用每一个反弹窗口把最弱的品种换出来。",
    ],
    "bullish": [
        "牛市里最重要的是拿住。不要频繁调仓。",
        "涨得好的品种不要急着卖。让利润奔跑。",
    ],
}

def get_psych_tip(style: dict) -> str:
    """返回当日心态提醒"""
    import random
    color = style.get("color", "neutral")
    tips = PSYCH_TIPS.get(color, PSYCH_TIPS["neutral"])
    return random.choice(tips)
