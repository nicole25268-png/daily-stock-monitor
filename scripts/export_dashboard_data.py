"""
从 AkShare 直接导出大盘数据 JSON，供前端看板渲染
与 daily_stock_analysis 推送数据同源（同数据源，同时间戳）
"""
import json, os, sys, time
from datetime import datetime
from pathlib import Path

def safe_fetch(fn, name, **kw):
    for attempt in range(2):
        try:
            result = fn(**kw)
            if result is not None and (not hasattr(result, 'empty') or not result.empty):
                print(f"  OK {name}: {len(result) if hasattr(result, '__len__') else 'ok'}")
                return result
        except Exception as e:
            print(f"  Retry {attempt+1}/2 {name}: {type(e).__name__}")
            time.sleep(2)
    print(f"  SKIP {name}")
    return None

def export():
    import akshare as ak
    import pandas as pd

    data = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    # 1. A股指数 (Sina - works)
    indices = safe_fetch(ak.stock_zh_index_spot_sina, "A股指数")
    TARGET = {"sh000001":"上证指数","sh000300":"沪深300","sh000688":"科创50",
              "sh000510":"中证A500","sz399006":"创业板指","sz399001":"深证成指"}
    a_idx = []
    if indices is not None:
        for _, r in indices.iterrows():
            code = str(r.iloc[0])
            if code in TARGET:
                a_idx.append({
                    "name": TARGET[code], "code": code,
                    "price": round(float(r.iloc[2]), 2),
                    "change_pct": round(float(r.iloc[4]), 2)
                })
    data["a_indices"] = a_idx

    # 2. 申万行业 (SW index_realtime_sw)
    SW_L1 = {'801010','801030','801040','801050','801080','801110','801120','801130',
             '801140','801150','801160','801170','801180','801200','801210','801230',
             '801710','801720','801730','801740','801750','801760','801770','801780',
             '801790','801880','801890','801950','801960','801970','801980'}
    SW_NAMES = {"801010":"农林牧渔","801030":"基础化工","801040":"钢铁","801050":"有色金属",
        "801080":"电子","801110":"家用电器","801120":"食品饮料","801130":"纺织服饰",
        "801140":"轻工制造","801150":"医药生物","801160":"公用事业","801170":"交通运输",
        "801180":"房地产","801200":"商贸零售","801210":"社会服务","801230":"综合",
        "801710":"建筑材料","801720":"建筑装饰","801730":"电力设备","801740":"国防军工",
        "801750":"计算机","801760":"传媒","801770":"通信","801780":"银行",
        "801790":"非银金融","801880":"汽车","801890":"机械设备",
        "801950":"煤炭","801960":"石油石化","801970":"环保","801980":"美容护理"}

    sw = safe_fetch(ak.index_realtime_sw, "申万行业")
    sectors = []
    if sw is not None:
        for _, r in sw.iterrows():
            code = str(r.iloc[0])
            l1_parent = code[:5]+"0"
            if l1_parent in SW_L1:
                price = float(r.iloc[3])
                prev = float(r.iloc[4])
                chg = round((price-prev)/prev*100, 2) if prev else 0
                sectors.append({
                    "code": code, "name": str(r.iloc[1]),
                    "l1_code": l1_parent,
                    "change_pct": chg,
                    "price": price
                })
    data["sectors"] = sectors

    # 3. 全市场统计 (Sina)
    stocks = safe_fetch(ak.stock_zh_a_spot, "全市场个股")
    if stocks is not None and not stocks.empty:
        changes = stocks.iloc[:, 3].astype(float)
        total = len(stocks)
        up = int((changes > 0).sum())
        down = int((changes < 0).sum())
        data["market_stats"] = {
            "total": total, "up": up, "down": down,
            "up_ratio": round(up/total*100,1) if total else 0,
            "limit_up": int((changes >= 9.9).sum()),
            "limit_down": int((changes <= -9.9).sum()),
        }
        if len(stocks.columns) > 5:
            data["market_stats"]["total_amount_yi"] = round(stocks.iloc[:,5].astype(float).sum()/1e8, 0)
    else:
        data["market_stats"] = {}

    # 4. 港股指数 (Sina)
    hk = safe_fetch(ak.stock_hk_index_spot_sina, "港股指数")
    HK_TARGET = {"HSI":"恒生指数","HSTECH":"恒生科技"}
    global_idx = []
    if hk is not None:
        for _, r in hk.iterrows():
            code = str(r.iloc[0])
            if code in HK_TARGET:
                global_idx.append({
                    "name": HK_TARGET[code],
                    "price": round(float(r.iloc[2]), 2),
                    "change_pct": round(float(r.iloc[4]), 2)
                })
    # 美股 via Sina
    try:
        us = ak.index_us_stock_sina(symbol=".IXIC")
        if not us.empty:
            latest = us.iloc[-1]; prev = us.iloc[-2]
            close = float(latest.iloc[4]); prev_c = float(prev.iloc[4])
            global_idx.append({"name": "纳斯达克(昨收)", "price": round(close,0),
                              "change_pct": round((close-prev_c)/prev_c*100,2)})
    except Exception:
        pass
    try:
        us2 = ak.index_us_stock_sina(symbol=".INX")
        if not us2.empty:
            latest = us2.iloc[-1]; prev = us2.iloc[-2]
            close = float(latest.iloc[4]); prev_c = float(prev.iloc[4])
            global_idx.append({"name": "标普500(昨收)", "price": round(close,0),
                              "change_pct": round((close-prev_c)/prev_c*100,2)})
    except Exception:
        pass
    data["global_indices"] = global_idx

    # 5. 商品期货
    comms = []
    for sym, name in [("GC","COMEX黄金"),("SI","COMEX白银"),("CL","NYMEX原油"),("HG","COMEX铜")]:
        try:
            df = ak.futures_foreign_commodity_realtime(symbol=sym)
            if not df.empty:
                r = df.iloc[0]
                comms.append({"name": name, "price": round(float(r.iloc[1]),2),
                             "change_pct": round(float(r.iloc[3]),2)})
        except Exception:
            pass
    data["commodities"] = comms

    # 6. 同花顺新闻
    news_list = []
    try:
        nf = ak.stock_info_global_ths()
        if nf is not None and not nf.empty:
            for _, r in nf.head(12).iterrows():
                title = str(r.iloc[1]) if len(r) > 1 else str(r.iloc[0])
                if len(title) > 5:
                    news_list.append({"title": title.strip()})
    except Exception:
        pass
    data["news"] = news_list[:8]

    # 保存
    docs_dir = Path(__file__).resolve().parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    output = docs_dir / "data.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nOK: {output} ({os.path.getsize(output)} bytes, {len(a_idx)} indices, {len(sectors)} sectors)")
    return str(output)

if __name__ == "__main__":
    export()
