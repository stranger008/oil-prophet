# -*- coding: utf-8 -*-
"""抓广东油价，更新 index.html"""
import re
import json
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
HTML = BASE / "index.html"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ===== 手动配置（调价日改这里）=====
CONFIG = {
    "next_date": "10月29日 24:00",
    "cycle_day": 8,
    "cycle_total": 10,
    "days_left": 2,
    "direction": "up",       # up / down / flat
    "per_liter_92": 0.27,
    "per_liter_95": 0.29,
    "per_liter_0": 0.28,
}
# ====================================


def fetch(url, timeout=10):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def get_prices():
    html = fetch("https://m.icauto.com.cn/oil/price_440000_0.html")
    p92 = re.search(r"92号汽油[^0-9]*?为\s*([\d.]+)\s*元", html)
    p95 = re.search(r"95号汽油[^0-9]*?为\s*([\d.]+)\s*元", html)
    p0 = re.search(r"0号柴油[^0-9]*?为\s*([\d.]+)\s*元", html)
    return {
        "p92": float(p92.group(1)) if p92 else 8.63,
        "p95": float(p95.group(1)) if p95 else 9.35,
        "p0": float(p0.group(1)) if p0 else 8.31,
    }


def main():
    prices = get_prices()
    c = CONFIG
    sign = "+" if c["direction"] == "up" else ("-" if c["direction"] == "down" else "")
    num = "0.00" if c["direction"] == "flat" else f"{abs(c['per_liter_92']):.2f}"
    dir_cn = {"up": "上调", "down": "下调", "flat": "搁浅"}[c["direction"]]
    s = -1 if c["direction"] == "down" else 1

    html = HTML.read_text(encoding="utf-8")
    html = html.replace("__NEXT_DATE__", c["next_date"])
    html = html.replace("__PREDICT_NUM__", f"{sign}{num}")
    html = html.replace("__PREDICT_CLASS__", c["direction"])
    html = html.replace("__PER_LITER_TEXT__",
        f"预计{dir_cn} 92# 汽油约 {abs(c['per_liter_92']):.2f} 元/升")
    html = html.replace("__DAYS_LEFT__", str(c["days_left"]))
    html = html.replace("__CYCLE_DAY__", str(c["cycle_day"]))
    html = html.replace("__CYCLE_TOTAL__", str(c["cycle_total"]))
    html = html.replace("__UPDATE_TIME__", datetime.now().strftime("%Y-%m-%d %H:%M"))
    html = html.replace('id="p92">--', f'id="p92">{prices["p92"]:.2f}')
    html = html.replace('id="p95">--', f'id="p95">{prices["p95"]:.2f}')
    html = html.replace('id="p0">--', f'id="p0">{prices["p0"]:.2f}')
    html = html.replace('id="p92next">→ 预测 --',
        f'id="p92next">→ 预测 {prices["p92"] + s*c["per_liter_92"]:.2f}')
    html = html.replace('id="p95next">→ 预测 --',
        f'id="p95next">→ 预测 {prices["p95"] + s*c["per_liter_95"]:.2f}')
    html = html.replace('id="p0next">→ 预测 --',
        f'id="p0next">→ 预测 {prices["p0"] + s*c["per_liter_0"]:.2f}')

    HTML.write_text(html, encoding="utf-8")
    print(f"OK: 92={prices['p92']} 95={prices['p95']} 0={prices['p0']}")


if __name__ == "__main__":
    main()
