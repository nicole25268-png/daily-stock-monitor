"""
数据获取模块 — 已验证数据源
主力：Sina（A 股指数/个股/HK 指数）+ CLS 财联社（新闻）
备选：EastMoney（需海外网络，自动降级）
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime
import time
import logging

logger = logging.getLogger(__name__)


def _safe_fetch(fn, name: str, **kwargs):
    """带重试的安全数据拉取"""
    for attempt in range(3):
        try:
            df = fn(**kwargs)
            if df is not None and not df.empty:
                logger.info(f"OK: {name} — {len(df)} rows")
                return df
        except Exception as e:
            logger.warning(f"Retry {attempt+1}/3: {name} — {type(e).__name__}")
            time.sleep(2)
    logger.warning(f"SKIP: {name} (3次重试失败)")
    return pd.DataFrame()


# ============================================================
# 1. A 股主要指数（Sina 源，已验证 ✓）
# ============================================================

SINA_CODE_MAP = {
    "sh000001": "上证指数",  "sh000300": "沪深300",
    "sh000688": "科创50",    "sh000905": "中证500",
    "sh000510": "中证A500",  "sz399001": "深证成指",
    "sz399006": "创业板指",
}

def fetch_a_indices() -> pd.DataFrame:
    """A 股主要指数实时行情"""
    df = _safe_fetch(ak.stock_zh_index_spot_sina, "A股指数(Sina)")
    if df.empty:
        # 降级 EM
        df = _safe_fetch(ak.stock_zh_index_spot_em, "A股指数(EM)")
    if df.empty:
        return df

    target = list(SINA_CODE_MAP.keys())
    df = df[df["代码"].isin(target)].copy()
    df["名称"] = df["代码"].map(SINA_CODE_MAP)
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df["最新价"] = pd.to_numeric(df["最新价"], errors="coerce")
    return df[["代码", "名称", "最新价", "涨跌幅", "涨跌额", "成交量", "成交额"]]


# ============================================================
# 2. 全市场个股行情（Sina 源，已验证 ✓，5524 只）
# ============================================================

def fetch_all_stocks() -> pd.DataFrame:
    """全市场 A 股个股行情"""
    df = _safe_fetch(ak.stock_zh_a_spot, "全市场个股(Sina)")
    if df.empty:
        df = _safe_fetch(ak.stock_zh_a_spot_em, "全市场个股(EM)")
    if not df.empty:
        df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
        df["成交额"] = pd.to_numeric(df["成交额"], errors="coerce")
        df["最新价"] = pd.to_numeric(df["最新价"], errors="coerce")
    return df


def fetch_market_stats(stock_df: pd.DataFrame = None) -> dict:
    """从全市场个股数据计算涨跌统计"""
    if stock_df is None:
        stock_df = fetch_all_stocks()
    empty = {"total": 0, "up": 0, "down": 0, "flat": 0,
             "up_ratio": 0, "limit_up": 0, "limit_down": 0, "total_amount_yi": 0}

    if stock_df.empty:
        return empty

    total = len(stock_df)
    changes = stock_df["涨跌幅"]
    up = int((changes > 0).sum())
    down = int((changes < 0).sum())
    flat = total - up - down

    limit_up = int((changes >= 9.9).sum())
    limit_down = int((changes <= -9.9).sum())
    total_amount = stock_df["成交额"].sum() if "成交额" in stock_df.columns else 0

    return {
        "total": total, "up": up, "down": down, "flat": flat,
        "up_ratio": round(up / total * 100, 1) if total else 0,
        "limit_up": limit_up, "limit_down": limit_down,
        "total_amount_yi": round(total_amount / 1e8, 0) if total_amount else 0,
    }


# ============================================================
# 3. 行业板块（申万二级→一级聚合，31 个标准行业）
# ============================================================

SW_L2_TO_L1 = {}  # 二级代码 → 一级代码
for c in range(801010, 802000):
    SW_L2_TO_L1[str(c)] = str(c)[:5] + "0"

SW_L1_NAMES = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁", "801050": "有色金属",
    "801080": "电子", "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服饰",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务", "801230": "综合",
    "801710": "建筑材料", "801720": "建筑装饰", "801730": "电力设备", "801740": "国防军工",
    "801750": "计算机", "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备",
    "801950": "煤炭", "801960": "石油石化", "801970": "环保", "801980": "美容护理",
}

def fetch_industry_boards() -> pd.DataFrame:
    """获取申万二级→一级聚合涨跌排名"""
    df = _safe_fetch(ak.index_realtime_sw, "申万行业")
    if df.empty:
        return df
    code_col = df.columns[0]
    price_col = df.columns[3]
    prev_col = df.columns[4]

    df["code"] = df[code_col].astype(str)
    df["price"] = df[price_col].astype(float)
    df["prev"] = df[prev_col].astype(float)
    df["chg"] = ((df["price"] - df["prev"]) / df["prev"] * 100).round(2)
    df["L1"] = df["code"].map(SW_L2_TO_L1)

    # 聚合到一级（中位数涨跌幅）
    grouped = df.groupby("L1")["chg"].median().reset_index()
    grouped["板块名称"] = grouped["L1"].map(SW_L1_NAMES)
    grouped = grouped.dropna(subset=["板块名称"])
    grouped = grouped.rename(columns={"chg": "涨跌幅"})
    result = grouped[["板块名称", "涨跌幅"]].sort_values("涨跌幅", ascending=False)
    return result


# ============================================================
# 4. 全球关键指数（HK Sina + US Sina daily）
# ============================================================

TARGET_HK_INDICES = {
    "HSTECH": "恒生科技",
    "HSI": "恒生指数",
    "HSCCI": "恒生红筹",
    "HSCEI": "恒生国企",
}

TARGET_US_INDICES = {
    ".IXIC": "纳斯达克",
    ".INX": "标普500",
}

def fetch_global_indices() -> pd.DataFrame:
    """获取港股+美股关键指数"""
    rows = []

    # HK indices (Sina real-time)
    hk = _safe_fetch(ak.stock_hk_index_spot_sina, "港股指数(Sina)")
    if not hk.empty:
        code_col = hk.columns[0]
        for _, r in hk.iterrows():
            code = str(r[code_col])
            if code in TARGET_HK_INDICES:
                rows.append({
                    "名称": TARGET_HK_INDICES[code],
                    "最新价": float(r.iloc[2]),
                    "涨跌幅": float(r.iloc[4]),
                })

    # US indices (Sina daily snapshot — latest close as reference)
    for sym, name in TARGET_US_INDICES.items():
        try:
            us = ak.index_us_stock_sina(symbol=sym)
            if not us.empty:
                latest = us.iloc[-1]
                prev = us.iloc[-2]
                close = float(latest.iloc[4])
                prev_close = float(prev.iloc[4])
                change_pct = round((close - prev_close) / prev_close * 100, 2)
                rows.append({
                    "名称": f"{name} (昨收)",
                    "最新价": close,
                    "涨跌幅": change_pct,
                })
        except Exception:
            pass

    if rows:
        df = pd.DataFrame(rows)
        df["最新价"] = df["最新价"].astype(float)
        df["涨跌幅"] = df["涨跌幅"].astype(float)
        return df
    return pd.DataFrame()


# ============================================================
# 5. 商品期货（COMEX 实时，已验证 ✓）
# ============================================================

COMMODITY_SYMBOLS = {
    "GC": "COMEX黄金",
    "SI": "COMEX白银",
    "CL": "NYMEX原油",
    "HG": "COMEX铜",
}

def fetch_commodities() -> pd.DataFrame:
    """商品期货实时行情"""
    rows = []
    for sym, name in COMMODITY_SYMBOLS.items():
        try:
            df = ak.futures_foreign_commodity_realtime(symbol=sym)
            if not df.empty:
                r = df.iloc[0]
                rows.append({
                    "名称": name,
                    "最新价": float(r.iloc[1]),
                    "涨跌幅": float(r.iloc[3]),
                })
        except Exception as e:
            logger.warning(f"商品 {name} 获取失败: {type(e).__name__}")
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def fetch_dollar_index() -> dict:
    """美元指数（从 Sina US index .DXY 获取）"""
    try:
        df = ak.index_us_stock_sina(symbol=".DXY")
        if not df.empty:
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            close = float(latest.iloc[4])
            prev_close = float(prev.iloc[4])
            change_pct = round((close - prev_close) / prev_close * 100, 2)
            return {"name": "美元指数", "price": close, "change_pct": change_pct}
    except Exception:
        pass
    return {"name": "美元指数", "price": None, "change_pct": None}


# ============================================================
# 6. 财经新闻（CLS 财联社，已验证 ✓）
# ============================================================

def fetch_financial_news() -> list:
    """获取财经快讯（同花顺 THS 主力）"""
    # 主力：同花顺
    try:
        df = ak.stock_info_global_ths()
        if df is not None and not df.empty:
            news = []
            for _, row in df.head(30).iterrows():
                title = str(row.iloc[1]) if len(row) > 1 else str(row.iloc[0])
                t = str(row.iloc[2]) if len(row) > 2 else ""
                if len(title) > 5:
                    news.append({"title": title.strip(), "time": t.strip()})
            return news
    except Exception as e:
        logger.warning(f"THS 新闻失败: {type(e).__name__}")

    # 降级 CLS
    try:
        df = ak.stock_info_global_cls()
        if df is not None and not df.empty:
            news = []
            for _, row in df.head(20).iterrows():
                news.append({"title": str(row.iloc[0]).strip(), "time": ""})
            return news
    except Exception:
        pass

    return []


# ============================================================
# 7. 北向资金
# ============================================================

def fetch_north_flow() -> dict:
    """北向资金"""
    # 尝试多个 API 名称
    for fname in ["stock_hsgt_north_net_flow_in_em", "stock_hsgt_north_flow_em"]:
        fn = getattr(ak, fname, None)
        if fn:
            try:
                df = fn(symbol="北上")
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    return {
                        "date": str(latest.iloc[0]) if len(latest) > 0 else "",
                        "net_flow_yi": float(latest.iloc[-1]) if len(latest) > 1 else 0,
                    }
            except Exception:
                continue
    return {"date": "", "net_flow_yi": 0}


# ============================================================
# 交易日历
# ============================================================

def is_trading_day() -> bool:
    """判断今天是否为交易日"""
    today = datetime.now()
    if today.weekday() >= 5:
        return False
    try:
        df = ak.tool_trade_date_hist_sina()
        today_str = today.strftime("%Y-%m-%d")
        return today_str in df["trade_date"].values
    except Exception:
        return today.weekday() < 5


# ============================================================
# 聚合数据（主入口）
# ============================================================

def fetch_all() -> dict:
    """拉取所有数据"""
    logger.info("=== 全量数据拉取 ===")

    # 全市场个股（核心数据，其他聚合依赖它）
    stocks = fetch_all_stocks()

    # 南向资金 + 行业资金流
    hsgt = pd.DataFrame()
    sector_flow = pd.DataFrame()
    try:
        hsgt = ak.stock_hsgt_fund_flow_summary_em()
    except Exception:
        pass
    try:
        sector_flow = ak.stock_sector_fund_flow_rank(indicator="10日", sector_type="行业资金流")
    except Exception:
        pass

    data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_trading_day": is_trading_day(),
        "a_indices": fetch_a_indices(),
        "global_indices": fetch_global_indices(),
        "commodities": fetch_commodities(),
        "dollar": fetch_dollar_index(),
        "industry_boards": fetch_industry_boards(),
        "market_stats": fetch_market_stats(stocks),
        "news": fetch_financial_news(),
        "hsgt_summary": hsgt,
        "sector_flow": sector_flow,
    }

    logger.info("=== 数据拉取完成 ===")
    return data
