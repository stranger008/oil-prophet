# -*- coding: utf-8 -*-
"""
油先知 · 自动计算调价幅度
每次运行直接替换HTML里的实际值，不依赖占位符
"""
import re
import csv
import io
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
HTML = BASE / "index.html"

FX = 7.2
BARREL_PER_TON = 7.35
TRANSMISSION = 1.0


def fetch(url, timeout=30, headers=None):
    h = headers or {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def get_gd_prices():
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
    try:
        req = urllib.request.Request(
            "https://hq.sinajs.cn/list=hf_OIL",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
        )
        h = urllib.request.urlopen(req, timeout=10).read().decode("gbk", "ignore")
        m = re.search(r'"([\d.]+)', h)
        return float(m.group(1)) if m else None
    except Exception as e:
        print(f"WARN: 布伦特实时价失败: {e}")
        return None


def fred_series(fred_id):
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
        print(f"WARN: FRED {fred_id} 失败: {e}")
        return []


def calc_forecast():
    brent = fred_series("DCOILBRENTEA")
    dubai = fred_series("DCOILDUBACI")
    if len(brent) < 20:
        print(f"WARN: 布伦特数据不足({len(brent)}条)")
        return None

    brent = brent[-20:]
    dubai_map = {d: p for d, p in dubai[-20:]} if dubai else {}

    weighted = []
    for date, b_price in brent:
        d_price = dubai_map.get(date, b_price - 1.5)
        minas = b_price + 2.5
        w = b_price * 0.4 + d_price * 0.3 + minas * 0.3
        weighted.append(w)

    current_avg = sum(weighted[10:]) / 10
    prev_avg = sum(weighted[:10]) / 10
    change_pct = (current_avg - prev_avg) / prev_avg * 100
    amount = (current_avg - prev_avg) * FX * BARREL_PER_TON * TRANSMISSION

    direction = "up" if amount > 50 else ("down" if amount < -50 else "flat")
    if direction == "flat":
        amount = 0

    return {
        "direction": direction,
        "amount_per_ton": round(amount),
        "p92": round(amount / 1350, 2),
        "p95": round(amount / 1300, 2),
        "p0": round(amount / 1190, 2),
        "change_pct": round(change_pct, 2),
    }


def main():
    prices = get_gd_prices()
    brent_now = get_brent()
    fc = calc_forecast()

    if not fc:
        fc = {"direction": "up", "amount_per_ton": 340, "p92": 0.27, "p95": 0.29, "p0": 0.28, "change_pct": 0}

    sign = "+" if fc["direction"] == "up" else ("-" if fc["direction"] == "down" else "")
    big_num = "0.00" if fc["direction"] == "flat" else f"{abs(fc['p92']):.2f}"
    dir_cn = {"up": "上调", "down": "下调", "flat": "搁浅"}[fc["direction"]]
    s = -1 if fc["direction"] == "down" else 1

    html = HTML.read_text(encoding="utf-8")

    # 替换大数字（+0.27那个）
    html = re.sub(r'(class="big-num[^"]*"[^>]*>)[+\-\d.]+',
                  lambda m: m.group(1) + f"{sign}{big_num}", html)

    # 替换说明文字
    desc = f"预计{dir_cn} 92# 汽油约 {abs(fc['p92']):.2f} 元/升（{fc['amount_per_ton']}元/吨，变化率{fc['change_pct']}%）"
    html = re.sub(r'预计(上调|下调|搁浅)[^<]*', desc, html)

    # 替换更新时间
    html = re.sub(r'更新时间：[^<]+', f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", html)

    # 替换三油现价
    html = re.sub(r'(id="p92">)[\d.]+', lambda m: m.group(1) + f"{prices['p92']:.2f}", html)
    html = re.sub(r'(id="p95">)[\d.]+', lambda m: m.group(1) + f"{prices['p95']:.2f}", html)
    html = re.sub(r'(id="p0">)[\d.]+', lambda m: m.group(1) + f"{prices['p0']:.2f}", html)

    # 替换预测价
    html = re.sub(r'(id="p92next">→ 预测 )[\d.]+',
                  lambda m: m.group(1) + f"{prices['p92'] + s*fc['p92']:.2f}", html)
    html = re.sub(r'(id="p95next">→ 预测 )[\d.]+',
                  lambda m: m.group(1) + f"{prices['p95'] + s*fc['p95']:.2f}", html)
    html = re.sub(r'(id="p0next">→ 预测 )[\d.]+',
                  lambda m: m.group(1) + f"{prices['p0'] + s*fc['p0']:.2f}", html)

    # 替换布伦特当前价
    if brent_now:
        html = re.sub(r'(周期开始 [\d.]+ → 当前\s*)[\d.]+',
                      lambda m: m.group(1) + f"{brent_now:.2f}", html)
        html = re.sub(r'(text-anchor="end" font-weight="600">)[\d.]+',
                      lambda m: m.group(1) + f"{brent_now:.2f}", html)

    HTML.write_text(html, encoding="utf-8")
    print(f"OK: 92={prices['p92']} brent={brent_now} forecast={fc['amount_per_ton']}元/吨 ({fc['change_pct']}%)")


if __name__ == "__main__":
    main()
