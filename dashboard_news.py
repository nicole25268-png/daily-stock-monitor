"""
新闻聚合模块 — 多源抓取 + 关键事件过滤 + 摘要生成
"""

import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================
# 关键词过滤规则 — 聚焦对资本市场有实质影响的新闻
# ============================================================

CAPITAL_MARKET_KEYWORDS = [
    # 美联储/利率
    ("美联储", 10), ("加息", 9), ("降息", 9), ("FOMC", 10), ("利率决议", 10),
    ("非农", 9), ("CPI", 9), ("PCE", 9), ("通胀", 8), ("就业", 7),
    ("美债", 7), ("收益率", 6), ("点阵图", 9),
    # 中国政策
    ("央行", 8), ("降准", 9), ("降息", 9), ("LPR", 9), ("MLF", 8),
    ("政治局", 10), ("国常会", 10), ("发改委", 9), ("财政部", 9),
    ("证监会", 9), ("注册制", 8), ("印花税", 9),
    # 产业政策
    ("电网投资", 8), ("特高压", 8), ("新能源", 7), ("半导体", 7),
    ("人工智能", 7), ("机器人", 7), ("商业航天", 7), ("房地产", 7),
    # 地缘/冲突
    ("美伊", 9), ("伊朗", 8), ("中东", 8), ("俄乌", 7),
    ("关税", 9), ("制裁", 8), ("贸易战", 9),
    # 市场事件
    ("IPO", 7), ("SpaceX", 8), ("上市", 6), ("退市", 8),
    ("财报", 7), ("业绩", 7),
    # 商品/汇率
    ("黄金", 7), ("原油", 7), ("OPEC", 8), ("铜", 6),
    ("人民币", 8), ("汇率", 8), ("美元", 7),
    # 全球
    ("美股", 7), ("港股", 7), ("欧央行", 8), ("日央行", 8),
]


def score_news(title: str) -> int:
    """根据关键词给新闻打分"""
    score = 0
    title_lower = title.lower()
    for kw, weight in CAPITAL_MARKET_KEYWORDS:
        if kw.lower() in title_lower:
            score += weight
    # 标题太短/太长扣分
    if len(title) < 8:
        score -= 3
    return score


def filter_top_news(news_list: list, top_n: int = 5) -> list:
    """从新闻列表中选出最重要的 N 条"""
    if not news_list:
        return []

    scored = []
    for item in news_list:
        title = item.get("title", "")
        s = score_news(title)
        if s > 5:  # 只保留有一定重要性的
            scored.append({**item, "score": s})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def classify_news(news_item: dict) -> str:
    """给新闻打标签"""
    title = news_item.get("title", "")
    tags_map = {
        "政策": ["政治局", "国常会", "发改委", "财政部", "证监会", "央行", "降准", "降息", "LPR", "MLF", "电网投资", "特高压"],
        "数据": ["非农", "CPI", "PCE", "PMI", "GDP", "通胀", "就业", "M2", "社融", "进出口"],
        "利率": ["美联储", "FOMC", "加息", "降息", "美债", "收益率", "点阵图", "利率决议"],
        "地缘": ["美伊", "伊朗", "中东", "俄乌", "关税", "制裁", "贸易战"],
        "公司": ["财报", "业绩", "IPO", "SpaceX", "上市", "退市"],
        "商品": ["黄金", "原油", "OPEC", "铜", "有色", "化工"],
        "外汇": ["人民币", "汇率", "美元"],
    }
    for tag, keywords in tags_map.items():
        for kw in keywords:
            if kw in title:
                return tag
    return "其他"


def generate_news_summary(news_list: list, top_n: int = 5) -> list:
    """生成今日要闻摘要（最多 N 条）"""
    filtered = filter_top_news(news_list, top_n)
    result = []
    for item in filtered:
        result.append({
            "title": item.get("title", ""),
            "time": item.get("time", ""),
            "tag": classify_news(item),
        })
    return result
