"""
从 daily_stock_analysis 数据管道生成 Kami 风格 HTML 看板
数据与飞书推送完全同源，确保一致性
"""
import sys, os, json, logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config import get_config
from src.market_analyzer import MarketAnalyzer
from src.storage import get_storage
from jinja2 import Template


def generate_dashboard():
    """生成 Kami 风格 HTML 看板"""
    logger.info("=== 生成 Kami HTML 看板 ===")

    config = get_config()
    storage = get_storage(config)
    analyzer = MarketAnalyzer(config, storage)

    # 1. 获取大盘数据
    try:
        market_data = analyzer._fetch_market_snapshot()
        logger.info(f"大盘快照: {len(market_data) if market_data else 0} 条")
    except Exception as e:
        logger.warning(f"大盘快照获取失败: {e}")
        market_data = {}

    # 2. 获取申万行业数据
    try:
        sector_df = analyzer._fetch_sector_performance()
        if sector_df is not None and not sector_df.empty:
            sectors = sector_df.to_dict(orient="records")
            logger.info(f"行业数据: {len(sectors)} 条")
        else:
            sectors = []
    except Exception as e:
        logger.warning(f"行业数据获取失败: {e}")
        sectors = []

    # 3. 从 AkShare 补充数据
    a_indices = []
    global_indices = []
    commodities_list = []
    try:
        from data_provider.akshare_fetcher import AkShareDataFetcher
        fetcher = AkShareDataFetcher()

        # A股指数
        try:
            idx_raw = fetcher.fetch_index_data()
            if idx_raw:
                for name, data in idx_raw.items():
                    a_indices.append({
                        "name": name,
                        "price": data.get("close", 0),
                        "change_pct": data.get("pct_change", 0),
                        "code": data.get("code", ""),
                    })
        except Exception:
            pass

        # 全球指数
        try:
            hk = fetcher.fetch_hk_index() or {}
            for name, data in hk.items():
                global_indices.append({
                    "name": name,
                    "price": data.get("close", 0),
                    "change_pct": data.get("pct_change", 0),
                })
        except Exception:
            pass

        # 商品
        try:
            comm = fetcher.fetch_commodities() or {}
            for name, data in comm.items():
                commodities_list.append({
                    "name": name,
                    "price": data.get("price", 0),
                    "change_pct": data.get("change_pct", 0),
                })
        except Exception:
            pass

    except ImportError:
        logger.warning("AkShare fetcher not available, using minimal data")

    # 4. 使用 Jinja2 渲染（用项目内置的简单模板，保证 Kami 风格）
    html = _render_html(a_indices, global_indices, commodities_list, sectors, market_data)

    # 5. 保存
    output_path = ROOT / "dashboard" / "index.html"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"OK: HTML saved to {output_path}")

    # Also save to docs/ for GitHub Pages
    docs_path = ROOT / "docs" / "index.html"
    docs_path.parent.mkdir(exist_ok=True)
    with open(docs_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"OK: Pages saved to {docs_path}")

    return str(output_path)


def _render_html(a_indices, global_indices, commodities, sectors, market_data):
    """生成 Kami 风格 HTML"""
    today = datetime.now().strftime("%Y-%m-%d")

    # Use the Kami template from our dashboard directory
    kami_template = ROOT.parent / "investment-research" / "dashboard" / "template.html"
    if kami_template.exists():
        with open(kami_template, "r", encoding="utf-8") as f:
            template_str = f.read()
    else:
        template_str = _fallback_template()

    template = Template(template_str)
    return template.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        weekday_cn=["周一","周二","周三","周四","周五","周六","周日"][datetime.now().weekday()],
        a_indices=a_indices or [],
        global_indices=global_indices or [],
        commodities=commodities or [],
        summary=market_data or {},
        sector_gainers=[s for s in sectors if s.get("pct_change", 0) > 0][:5],
        sector_losers=[s for s in sectors if s.get("pct_change", 0) < 0][-5:],
        top_news=[],
        ai_summary="",
        style={"style": "中性", "desc": "数据载入中", "color": "neutral"},
        market_advice={"add": [], "reduce": []},
        port_advice={"buy": [], "hold": [], "sell": []},
        psych_tip="市场短期是投票机，长期是称重机。",
        broker_views={},
        fund_flow={"inflow": [], "outflow": []},
        dollar={},
        event_calendar=[],
    )


def _fallback_template():
    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>每日盯盘</title>
<style>:root{--parchment:#f5f4ed;--brand:#1B365D;--up:#B22234;--down:#2E7D32}
body{max-width:960px;margin:0 auto;padding:20px;background:var(--parchment);font-family:"Microsoft YaHei",sans-serif}
h2{color:var(--brand);border-left:3px solid var(--brand);padding-left:8px}
.up{color:var(--up)}.down{color:var(--down)}
.card{background:#faf9f5;border:1px solid #e8e6dc;border-radius:4px;padding:14px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}
.item{background:var(--parchment);border:1px solid #e5e3d8;border-radius:4px;padding:10px;text-align:center}
.item .label{font-size:.75rem;color:#6b6a64}.item .price{font-size:1rem;font-weight:500}
</style></head><body>
<h1>每日盯盘 · {{ generated_at[:10] }}</h1>
<h2>A股指数</h2><div class="card"><div class="grid">
{% for idx in a_indices %}<div class="item"><div class="label">{{ idx.name }}</div>
<div class="price">{{ "%.2f"|format(idx.price|float) }}</div>
<div class="{% if idx.change_pct|float>0 %}up{% else %}down{% endif %}">{{ "%+.2f"|format(idx.change_pct|float) }}%</div></div>{% endfor %}
</div></div>
<h2>行业板块</h2><div class="card"><p style="font-size:.85rem">申万一级行业排名（数据同飞书推送）</p></div>
<p style="font-size:.75rem;color:#6b6a64;text-align:center">数据与 Ticino 飞书推送一致 · {{ generated_at }}</p>
</body></html>"""


if __name__ == "__main__":
    generate_dashboard()
