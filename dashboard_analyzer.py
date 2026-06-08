"""
分析模块 — 市场统计、板块排名、资金流向分析
"""

import pandas as pd
import logging

logger = logging.getLogger(__name__)


def analyze_sector_leaders(industry_df: pd.DataFrame, top_n: int = 5) -> dict:
    """提取行业板块涨幅/跌幅 TOP N（兼容多种列名）"""
    if industry_df.empty:
        return {"gainers": [], "losers": []}

    # 兼容列名
    name_col = "板块名称" if "板块名称" in industry_df.columns else (
        "行业" if "行业" in industry_df.columns else industry_df.columns[0])
    change_col = "涨跌幅" if "涨跌幅" in industry_df.columns else industry_df.columns[1]

    df = industry_df.sort_values(change_col, ascending=False)

    gainers = []
    for _, row in df.head(top_n).iterrows():
        gainers.append({
            "name": str(row[name_col]),
            "change_pct": round(float(row[change_col]), 2),
        })

    losers = []
    for _, row in df.tail(top_n).iterrows():
        losers.append({
            "name": str(row[name_col]),
            "change_pct": round(float(row[change_col]), 2),
        })

    return {"gainers": gainers, "losers": losers}


def analyze_market_sentiment(stats: dict) -> str:
    """判断市场情绪：乐观/中性/悲观"""
    if not stats:
        return "neutral"

    up_ratio = stats.get("up_ratio", 50)
    limit_up = stats.get("limit_up", 0)
    limit_down = stats.get("limit_down", 0)
    up = stats.get("up", 0)
    down = stats.get("down", 0)

    # 涨多跌少 + 涨停多
    if up_ratio > 65 and limit_up > 80:
        return "bullish"
    # 涨跌接近
    if 40 <= up_ratio <= 60:
        return "neutral"
    # 普跌 + 跌停多
    if up_ratio < 35 and limit_down > 30:
        return "bearish"

    if up > down:
        return "neutral_positive"
    return "neutral_negative"


def compute_index_change(indices_df: pd.DataFrame, index_name: str) -> float:
    """获取指定指数的涨跌幅"""
    if indices_df.empty:
        return 0
    row = indices_df[indices_df["名称"].str.contains(index_name)]
    if row.empty:
        return 0
    return round(float(row.iloc[0]["涨跌幅"]), 2)


def generate_market_summary(data: dict) -> dict:
    """生成市场综述"""
    indices = data.get("a_indices", pd.DataFrame())
    stats = data.get("market_stats", {})
    north = data.get("north_flow", {})
    industry = data.get("industry_boards", pd.DataFrame())

    # 指数涨跌
    sh = compute_index_change(indices, "上证")
    sz = compute_index_change(indices, "深证")
    cy = compute_index_change(indices, "创业板")

    # 涨跌统计
    up_ratio = stats.get("up_ratio", 0)
    limit_up = stats.get("limit_up", 0)
    limit_down = stats.get("limit_down", 0)
    total_amount = stats.get("total_amount_yi", 0)

    # 北向
    north_flow = north.get("net_flow_yi", 0)

    # 板块
    sector_data = analyze_sector_leaders(industry, top_n=5)

    # 情绪判断
    sentiment = analyze_market_sentiment(stats)

    # 与前一日对比（方向性判断）
    trend = "震荡"
    if sh < -1.0 or cy < -2.0:
        trend = "调整"
    elif sh > 1.0:
        trend = "上涨"

    # 成交额判断
    volume_note = ""
    if total_amount > 30000:
        volume_note = "放量"
    elif total_amount < 20000:
        volume_note = "缩量"

    return {
        "shanghai": sh,
        "shenzhen": sz,
        "chinext": cy,
        "up_ratio": up_ratio,
        "up_count": stats.get("up", 0),
        "down_count": stats.get("down", 0),
        "limit_up": limit_up,
        "limit_down": limit_down,
        "total_amount_yi": total_amount,
        "volume_note": volume_note,
        "north_flow_yi": north_flow,
        "sentiment": sentiment,
        "trend": trend,
        "sector_gainers": sector_data["gainers"],
        "sector_losers": sector_data["losers"],
    }
