# -*- coding: utf-8 -*-
"""
油先知 · 自动计算调价幅度
原理：抓布伦特+迪拜每日价格 → 算近10天均价 vs 前10天均价 → 变化率 → 元/吨
"""
import re
import csv
import io
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
HTML = BASE / "index.html"

HEADERS = {"User-Agent": "Mozilla/5.0"}

FX = 7.2
BARREL_PER_TON = 7.35
TRANSMISSION = 1.0


def fetch(url, timeout=30, headers=None):
    h = headers or HEADERS
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def get_gd_prices():
    """抓广东三油现价，失败用默认值"""
    try:
        html = fetch("https://m.icauto.com.cn/oil/price_440000_0.html", timeout=20)
        p92 = re.search(r"92号汽油[^0-9]*?为\s*([\d.]+)\s*元", html)
        p95 = re.search(r"95号汽油[^0-9]*?为\s*([\d.]+)\s*元", html)
        p0 = re.search(r"0号柴油[^0-9]*?为\s*([\d.]+)\s*元", html)
        return {
            "p92": float(p92.group(1)) if p92 else 8.63,
            "p95": float(p95.group(1)) if p95 else 9.35,
            "p0": float(p0.group(1)) if p0 else 8.31,
        }
    except Exception as e:
        print(f"WARN: 广东现价抓取失败: {e}")
        return {"p92": 8.63, "p95": 9.35, "p0": 8.31}


def get_brent():
    """抓布伦特实时价"""
    try:
        req = urllib.request.Request(
            "https://hq.sinajs.cn/list=hf_OIL",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
        )
        h = urllib.request.urlopen(req, timeout=10).read().decode("gbk", "ignore")
        m = re.search(r'"([\d.]+)', h)
        return float(m.group(1)) if m else None
    except Exception as e:
        print(f"WARN: 布伦特实时价抓取失败: {e}")
        return None


def fred_series(fred_id):
    """从FRED抓原油每日价格CSV"""
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
        text = fetch(url, timeout=30)
        rows = list(csv.reader(io.StringIO(text)))[1:]
        result = []
        for row in rows:
            if len(row) >= 2 and row[1] != ".":
                result.append((row[0], float(row[1])))
        return result
    except Exception as e:
        print(f"WARN: FRED {fred_id} 抓取失败: {e}")
        return []


def calc_forecast():
    """自动计算调价幅度"""
    brent = fred_series("DCOILBRENTEA")
    dubai = fred_series("DCOILDUBACI")

    if len(brent) < 20:
        print(f"WARN: 布伦特数据不足({len(brent)}条)")
        return None

    brent = brent[-20:]
    dubai = dubai[-20:] if dubai else []
    dubai_map = {d: p for d, p in dubai}

    weighted = []
    for date, b_price in brent:
        d_price = dubai_map.get(date, b_price - 1.5)
        minas = b_price + 2.5
        w = b_price * 0.4 + d_price * 0.3 + minas * 0.3
        weighted.append((date, w))

    current_avg = sum(p for _, p in weighted[10:]) / 10
    prev_avg = sum(p for _, p in weighted[:10]) / 10
    change_pct = (current_avg - prev_avg) / prev_avg * 100
    cost_change = (current_avg - prev_avg) * FX * BARREL_PER_TON
    amount_per_ton = cost_change * TRANSMISSION

    p92_per_liter = amount_per_ton / 1350
    p95_per_liter = amount_per_ton / 1300
    p0_per_liter = amount_per_ton / 1190

    direction = "up" if amount_per_ton > 0 else ("down" if amount_per_ton < 0 else "flat")
    if abs(amount_per_ton) < 50:
        direction = "flat"
        amount_per_ton = 0
        p92_per_liter = p95_per_liter = p0_per_liter = 0

    return {
        "direction": direction,
        "amount_per_ton": round(amount_per_ton),
        "p92_per_liter": round(p92_per_liter, 2),
        "p95_per_liter": round(p95_per_liter, 2),
        "p0_per_liter": round(p0_per_liter, 2),
        "change_pct": round(change_pct, 2),
    }


def main():
    prices = get_gd_prices()
    brent_now = get_brent()
    fc = calc_forecast()

    if not fc:
        print("FAIL: 无法计算预测，使用默认值")
        fc = {"direction": "up", "amount_per_ton": 340, "p92_per_liter": 0.27,
              "p95_per_liter": 0.29, "p0_per_liter": 0.28, "change_pct": 0}

    sign = "+" if fc["direction"] == "up" else ("-" if fc["direction"] == "down" else "")
    num = "0.00" if fc["direction"] == "flat" else f"{abs(fc['p92_per_liter']):.2f}"
    dir_cn = {"up": "上调", "down": "下调", "flat": "搁浅"}[fc["direction"]]
    s = -1 if fc["direction"] == "down" else 1

    html = HTML.read_text(encoding="utf-8")
    html = html.replace("__NEXT_DATE__", "10月29日 24:00")
    html = html.replace("__PREDICT_NUM__", f"{sign}{num}")
    html = html.replace("__PER_LITER_TEXT__",
        f"预计{dir_cn} 92# 汽油约 {abs(fc['p92_per_liter']):.2f} 元/升（{fc['amount_per_ton']}元/吨，变化率{fc['change_pct']}%）")
    html = html.replace("__DAYS_LEFT__", "2")
    html = html.replace("__CYCLE_DAY__", "8")
    html = html.replace("__CYCLE_TOTAL__", "10")
    html = html.replace("__UPDATE_TIME__", datetime.now().strftime("%Y-%m-%d %H:%M"))
    html = html.replace('id="p92">--', f'id="p92">{prices["p92"]:.2f}')
    html = html.replace('id="p95">--', f'id="p95">{prices["p95"]:.2f}')
    html = html.replace('id="p0">--', f'id="p0">{prices["p0"]:.2f}')
    html = html.replace('id="p92next">→ 预测 --',
        f'id="p92next">→ 预测 {prices["p92"] + s*fc["p92_per_liter"]:.2f}')
    html = html.replace('id="p95next">→ 预测 --',
        f'id="p95next">→ 预测 {prices["p95"] + s*fc["p95_per_liter"]:.2f}')
    html = html.replace('id="p0next">→ 预测 --',
        f'id="p0next">→ 预测 {prices["p0"] + s*fc["p0_per_liter"]:.2f}')

    if brent_now:
        html = re.sub(r'(周期开始 [\d.]+ → 当前\s*)[\d.]+',
                      lambda m: m.group(1) + f"{brent_now:.2f}", html)
        html = re.sub(r'(text-anchor="end" font-weight="600">)[\d.]+',
                      lambda m: m.group(1) + f"{brent_now:.2f}", html)

    HTML.write_text(html, encoding="utf-8")
    print(f"OK: 92={prices['p92']} brent={brent_now} forecast={fc['amount_per_ton']}元/吨 ({fc['change_pct']}%)")


if __name__ == "__main__":
    main()
