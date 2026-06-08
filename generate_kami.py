"""
主控脚本 — 每日盯盘看板生成 + 飞书推送
用法：python generate.py [--push] [--url DASHBOARD_URL] [--force]
  --push   推送到飞书
  --url    完整看板公网链接
  --force  非交易日也生成（测试用）
"""

import sys
import os
import logging
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(ROOT / "generate.log", encoding="utf-8")],
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(ROOT))

from dashboard_fetcher import fetch_all
from dashboard_analyzer import generate_market_summary
from dashboard_advisor import determine_style, market_sector_advice, portfolio_advice, get_psych_tip
from dashboard_news import generate_news_summary
from jinja2 import Template


def _df_to_list(df, mapping: dict) -> list:
    if df is None or df.empty:
        return []
    result = []
    for _, row in df.iterrows():
        item = {}
        for col, key in mapping.items():
            if col in df.columns:
                item[key] = row[col]
        result.append(item)
    return result


def prepare_template_data(raw_data: dict) -> dict:
    """将 raw data 转成 Jinja2 模板所需格式"""

    # A 股指数
    idx_df = raw_data.get("a_indices")
    if idx_df is not None and not idx_df.empty and "涨跌幅" in idx_df.columns:
        idx_df["涨跌幅"] = idx_df["涨跌幅"].astype(float)
    a_indices = _df_to_list(idx_df, {"名称": "name", "最新价": "price", "涨跌幅": "change_pct"})

    # 全球指数
    gbl_df = raw_data.get("global_indices")
    if gbl_df is not None and not gbl_df.empty and "涨跌幅" in gbl_df.columns:
        gbl_df["涨跌幅"] = gbl_df["涨跌幅"].astype(float)
    global_indices = _df_to_list(gbl_df, {"名称": "name", "最新价": "price", "涨跌幅": "change_pct"})

    # 商品
    comm_df = raw_data.get("commodities")
    if comm_df is not None and not comm_df.empty and "涨跌幅" in comm_df.columns:
        comm_df["涨跌幅"] = comm_df["涨跌幅"].astype(float)
    commodities = _df_to_list(comm_df, {"名称": "name", "最新价": "price", "涨跌幅": "change_pct"})

    # 市场综述
    summary = generate_market_summary(raw_data)

    # 新闻摘要（先用规则引擎过滤 Top 5，再用 DeepSeek AI 润色）
    top_news_raw = generate_news_summary(raw_data.get("news", []), top_n=8)
    # AI 润色
    try:
        from dashboard_ai import summarize_news
        ai_summary = summarize_news(raw_data.get("news", []))
        if ai_summary:
            logger.info("AI 新闻摘要已生成")
    except Exception as e:
        ai_summary = ""
        logger.warning(f"AI 新闻摘要跳过: {e}")

    top_news = []
    for n in top_news_raw:
        top_news.append({
            "title": n["title"], "time": n["time"],
            "tag_cn": n["tag"],
            "tag_cn_en": {"政策":"policy","数据":"data","利率":"rate","地缘":"geo",
                          "公司":"corp","商品":"commod","外汇":"fx"}.get(n["tag"], "other"),
        })

    # 风格判断
    style = determine_style(summary)

    # 全市场建议
    market_advice = market_sector_advice(summary)

    # 持仓建议
    port_advice = portfolio_advice(summary, style)

    # AI 投资建议（DeepSeek 增强）
    ai_advice_text = ""
    try:
        from dashboard_ai import generate_advice
        ai_advice_text = generate_advice(summary, style, port_advice)
        if ai_advice_text:
            logger.info("AI 投资建议已生成")
    except Exception as e:
        logger.warning(f"AI 建议跳过: {e}")

    # AI 心态提醒
    ai_psych = ""
    try:
        from dashboard_ai import generate_psych_tip
        ai_psych = generate_psych_tip(style, summary.get("shanghai", 0))
    except Exception:
        pass
    psych_tip = ai_psych if ai_psych else get_psych_tip(style)

    # 资金流向（行业）
    fund_flow = {"inflow": [], "outflow": []}
    try:
        flow_df = raw_data.get("sector_flow")
        if flow_df is not None and not flow_df.empty:
            nc = flow_df.columns[1] if len(flow_df.columns) > 1 else flow_df.columns[0]
            ac = flow_df.columns[3] if len(flow_df.columns) > 3 else None
            if ac:
                sf = flow_df.sort_values(ac, ascending=False)
                for _, r in sf.head(5).iterrows():
                    fund_flow["inflow"].append({"name": str(r[nc]), "amount": float(r[ac]) / 1e8})
                for _, r in sf.tail(5).iterrows():
                    fund_flow["outflow"].append({"name": str(r[nc]), "amount": float(r[ac]) / 1e8})
    except Exception:
        pass

    # 南向资金
    south_flow = 0
    try:
        hsgt = raw_data.get("hsgt_summary")
        if hsgt is not None and not hsgt.empty:
            for _, r in hsgt.iterrows():
                if "港股通" in str(r.iloc[1]):
                    south_flow = float(r.iloc[4]) if len(r) > 4 else 0
    except Exception:
        pass
    summary["south_flow_yi"] = south_flow

    # 券商研报观点（通过 DeepSeek AI 收集+总结）
    broker_views = _prepare_broker_views()

    weekdays = ["周一","周二","周三","周四","周五","周六","周日"]
    weekday_cn = weekdays[datetime.now().weekday()]

    return {
        "generated_at": raw_data.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "weekday_cn": weekday_cn,
        "a_indices": a_indices,
        "global_indices": global_indices,
        "commodities": commodities,
        "summary": summary,
        "sector_gainers": summary.get("sector_gainers", []),
        "sector_losers": summary.get("sector_losers", []),
        "top_news": top_news,
        "ai_summary": ai_summary,
        "style": style,
        "market_advice": market_advice,
        "port_advice": port_advice,
        "psych_tip": psych_tip,
        "ai_advice_text": ai_advice_text,
        "broker_views": broker_views,
        "fund_flow": fund_flow,
        "dollar": raw_data.get("dollar", {}),
        "event_calendar": _event_calendar(),
    }


def _prepare_broker_views() -> dict:
    """主流机构市场观点（≤18家），用 DeepSeek AI 总结共识"""
    brokers = [
        {"name": "中金公司", "date": "6/2", "style": "偏多",
         "url": "https://finance.eastmoney.com/a/202606023756778044.html",
         "view": "\"稳\"好于\"快\"。三大主线：AI产业链精挑细选、能源瓶颈与转型、周期反转。"},
        {"name": "国泰海通", "date": "6/5", "style": "看多",
         "url": "https://fund.eastmoney.com/a/202606053760811524.html",
         "view": "上修全A盈利增速至13.6%。\"转型牛\"未结束，三季度侧重成长+传统转型。"},
        {"name": "华泰证券", "date": "6/5", "style": "偏多",
         "url": "https://finance.eastmoney.com/a/202606053761023947.html",
         "view": "五大周期线索：电力、技术（AI+芯片）、气候、盈利、通胀。小盘风格年内占优。"},
        {"name": "中信证券", "date": "6/7", "style": "中性偏谨慎",
         "url": "https://www.sohu.com/a/1033435524_122014422",
         "view": "\"AI+能化\"杠铃结构。海峡通航是非AI转机临界点。关注新能源、化工超跌修复。"},
        {"name": "广发证券", "date": "6/7", "style": "偏多",
         "url": "https://finance.eastmoney.com/news/1344,202606073762698311.html",
         "view": "EPS为锚。6月调整是布局机会，6月底半年报窗口关注海外算力链。"},
        {"name": "招商证券", "date": "6/1", "style": "偏多",
         "url": "https://fund.eastmoney.com/a/202606013755283981.html",
         "view": "\"景气强化，震荡上行\"。关注存储芯片、光通信、半导体设备、商业航天。"},
        {"name": "中信建投", "date": "6/8", "style": "中性",
         "url": "https://fund.eastmoney.com/a/202606083762799262.html",
         "view": "短期\"科技跌、防御涨\"轮动，尚未到风格大切换。算力轮动+煤炭+工业金属。"},
        {"name": "方正证券", "date": "6/8", "style": "偏多",
         "url": "https://stock.jrj.com.cn/2026/06/08074057373927.shtml",
         "view": "调整接近尾声，Q3偏乐观。AI精选+HALO资产+周期资源。"},
        {"name": "华西证券", "date": "6/7", "style": "中性偏谨慎",
         "url": "https://finance.eastmoney.com/a/202606083762773371.html",
         "view": "6月议息+SpaceX IPO扰动，但A股韧性好于海外。关注电网、煤炭、银行、创新药。"},
        {"name": "财信证券", "date": "6/8", "style": "中性偏谨慎",
         "url": "https://www.163.com/dy/article/KUSTG8FF05568W0A.html",
         "view": "6月多重扰动。8-10月再做多窗口。防守：高股息；低吸：泛科技；左侧：消费医药。"},
        {"name": "开源证券", "date": "6/8", "style": "偏多",
         "url": "https://stock.jrj.com.cn/2026/06/08074057373927.shtml",
         "view": "牛市基础未变。国产算力→AI电力链→应用入口→周期消费，为配置优先级顺序。"},
        {"name": "易方达基金", "date": "6/5", "style": "偏多",
         "url": "https://www.efunds.com.cn/c/803/803513.shtml",
         "view": "A股港股长期配置价值提升。关注科创50、半导体材料设备、人工智能主题指数。"},
        {"name": "保险资管(平安/国寿)", "date": "6/3", "style": "偏多",
         "url": "https://finance.sina.cn/2026-06-03/detail-iniacaew1018404.d.html",
         "view": "科技成长领跑(+164%)，消费医药垫底。后市：红利+长久期债+另类资产。"},
        {"name": "机构调查(130+家)", "date": "6/8", "style": "偏多",
         "url": "https://www.aigupiao.com/view/detail/4058407",
         "view": "公募仓位85.6%。42%预期全年收益10-15%。共识最强：国产算力。风险：通胀超预期。"},
        {"name": "游资动向", "date": "6/8", "style": "偏空",
         "url": "",
         "view": "游资完全躺平，日净买入超千万个股不足10只。不企稳不操作，市场\"混沌期\"。"},
        {"name": "散户情绪", "date": "6/8", "style": "偏空",
         "url": "",
         "view": "70%散户亏损。\"指数在牛市，个股在熊市\"。科技股暴涨暴跌由情绪放大器驱动。"},
    ]

    # DeepSeek AI 总结
    text = "\n".join([f"- {b['name']}({b['style']}): {b['view']}" for b in brokers])
    conclusion = ""
    try:
        from dashboard_ai import _call_deepseek
        conclusion = _call_deepseek(
            "你是资深策略分析师。基于以下16家机构/资金方对2026年6月A股的观点，给出简洁综合结论。",
            f"{text}\n\n请输出150字以内综合结论：1.共识方向 2.主要分歧 3.短期操作建议。一段话，不分点。",
            temperature=0.3
        )
    except Exception:
        pass
    if not conclusion:
        conclusion = "机构共识：AI科技成长（国产算力、光通信、半导体）仍是中期主线，高股息红利（银行、煤炭、电力）为防御底仓。分歧在于6月扰动程度——乐观派认为调整近尾声（方正），谨慎派建议等8月再做多（财信）。短期建议：6成仓位，不追高，逢低布局电网设备、红利低波，等6月中旬FOMC+IPO落地后再加仓。"

    consensus = {
        "看多共识": ["国产算力/AI硬件", "电网设备/新能源", "高股息红利", "半导体设备/材料", "光通信"],
        "谨慎方向": ["有色/化工（等海峡通航信号）", "消费/医药（等内需改善）", "地产链（仍在磨底）"],
        "关键风险": ["6月FOMC鹰派超预期", "SpaceX IPO资金虹吸", "科技拥挤度+产业资本减持"],
    }

    return {"brokers": brokers, "conclusion": conclusion, "consensus": consensus,
            "updated_at": datetime.now().strftime("%Y-%m-%d")}


def _event_calendar() -> list:
    """6月重要事件日历"""
    return [
        {"date": "6/5 已公布", "tag": "非农", "tag_css": "data", "event": "美国5月非农 +17.2万（大超预期），加息概率↑"},
        {"date": "6/8-12", "tag": "WWDC", "tag_css": "corp", "event": "苹果 WWDC26，AI 战略更新"},
        {"date": "6/10 周三", "tag": "CPI", "tag_css": "data", "event": "美国 5 月 CPI（议息前最关键数据），预期 4.3%"},
        {"date": "6/10 周三", "tag": "中国CPI", "tag_css": "data", "event": "中国 5 月 CPI/PPI"},
        {"date": "6/11 周四", "tag": "PPI", "tag_css": "data", "event": "美国 5 月 PPI，预期同比 6.5%+"},
        {"date": "6/11 周四", "tag": "欧央行", "tag_css": "fomc", "event": "欧央行利率决议，预期加息 25bp"},
        {"date": "6/12 周五", "tag": "IPO", "tag_css": "ipo", "event": "SpaceX 纳斯达克上市，史上最大 IPO（$1.77万亿估值）"},
        {"date": "6/16 周一", "tag": "日央行", "tag_css": "fomc", "event": "日本央行利率决议，加息概率 88%"},
        {"date": "6/16-17", "tag": "FOMC", "tag_css": "fomc", "event": "美联储议息会议（沃什首秀+点阵图），年内加息概率 70%"},
        {"date": "6/24", "tag": "财报", "tag_css": "corp", "event": "美光科技财报，检验 HBM/DRAM 景气度"},
        {"date": "6月底", "tag": "半年报", "tag_css": "corp", "event": "A股半年报业绩预告密集披露期"},
        {"date": "持续", "tag": "地缘", "tag_css": "geo", "event": "美伊谈判僵局 + 霍尔木兹海峡通航不确定性"},
    ]


def render_html(template_data: dict, output_path: str = None) -> str:
    template_file = ROOT / "dashboard_template.html"
    with open(template_file, "r", encoding="utf-8") as f:
        template_str = f.read()
    template = Template(template_str)
    html = template.render(**template_data)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"OK: HTML — {output_path}")
    return html


def main(push: bool = False, dashboard_url: str = "", force: bool = False):
    logger.info("=" * 50)
    logger.info("每日盯盘看板生成")
    logger.info("=" * 50)

    # Step 1: 拉数据
    logger.info("[1/5] 拉取市场数据...")
    raw_data = fetch_all()

    if not force and not raw_data.get("is_trading_day"):
        logger.info("今日非交易日，跳过。用 --force 强制生成")
        return

    # Step 2: 处理数据
    logger.info("[2/5] 处理+分析...")
    template_data = prepare_template_data(raw_data)

    # Step 3: DeepSeek AI
    logger.info("[3/5] AI 增强...")
    # (已在 prepare_template_data 中处理)

    # Step 4: 渲染 HTML
    logger.info("[4/5] 渲染 HTML...")
    today = datetime.now().strftime("%Y-%m-%d")
    html_path = ROOT / f"daily_{today}.html"
    render_html(template_data, str(html_path))
    # GitHub Pages 部署目录
    docs_path = ROOT / "docs"
    docs_path.mkdir(exist_ok=True)
    render_html(template_data, str(docs_path / "index.html"))

    # Step 5: 飞书推送
    if push:
        logger.info("[5/5] 推送到飞书...")
        from dashboard_feishu import push_daily_report
        push_data = {
            "generated_at": template_data["generated_at"],
            "summary": template_data["summary"],
            "style": template_data["style"],
            "top_news": template_data["top_news"],
            "sector_gainers": template_data["sector_gainers"],
            "sector_losers": template_data["sector_losers"],
            "port_advice": template_data["port_advice"],
            "psych_tip": template_data["psych_tip"],
        }
        push_daily_report(push_data, dashboard_url)
    else:
        logger.info("[5/5] 跳过飞书推送")

    logger.info("=" * 50)
    logger.info(f"完成 — {html_path}")
    logger.info("=" * 50)


if __name__ == "__main__":
    push = "--push" in sys.argv
    force = "--force" in sys.argv
    url = ""
    for i, arg in enumerate(sys.argv):
        if arg == "--url" and i + 1 < len(sys.argv):
            url = sys.argv[i + 1]
    main(push=push, dashboard_url=url, force=force)
