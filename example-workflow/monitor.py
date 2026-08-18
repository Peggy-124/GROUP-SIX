# -*- coding: utf-8 -*-
"""
流程範例｜記憶體與整合元件：誰接單、誰買單
標的：MU（美光）、INTC（英特爾）、TXN（德州儀器）

做什麼：抓三檔近一年日線 → 統一日期 → 畫圖並標上關稅事件日 → 輸出一頁摘要。
重跑一次就會更新到最新交易日。

用法：python -X utf8 monitor.py
"""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# ── 中文字型（Windows 用微軟正黑體，找不到就換 Noto Sans TC）
_installed = {f.name for f in font_manager.fontManager.ttflist}
for _cand in ("Microsoft JhengHei", "Noto Sans TC", "PingFang TC"):
    if _cand in _installed:
        plt.rcParams["font.family"] = _cand
        break
plt.rcParams["axes.unicode_minus"] = False

# ── 這一組的設定（換一組只要改這三行）
TICKERS = {"MU": "美光", "INTC": "英特爾", "TXN": "德州儀器"}
TITLE = "記憶體與整合元件：誰接單、誰買單"
RANGE = "1y"

BASE = Path(__file__).resolve().parent
RAW_DIR = BASE / "raw"          # 關卡一：原始資料原封不動存這裡
RAW_DIR.mkdir(exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"}
API = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d"


# ── 關卡一：抓
def fetch_raw(symbol):
    """抓一檔的原始 JSON，原封不動存檔（存檔是驗收條件之一）。"""
    url = API.format(sym=symbol, rng=RANGE)
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    raw = resp.json()
    stamp = datetime.now().strftime("%Y-%m-%d")
    out = RAW_DIR / f"{symbol}-{stamp}.json"
    out.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    print(f"  [抓] {symbol} 原始檔已存：{out.name}")
    return raw


# ── 關卡二：理
def to_series(raw):
    """把 Yahoo 的巢狀 JSON 整理成 {日期: 收盤價}。
    坑：timestamp 是 UTC 秒數要轉日期；close 會有 None（停牌或尾端未收盤）要濾掉。
    """
    result = raw["chart"]["result"][0]
    ts = result["timestamp"]
    close = result["indicators"]["quote"][0]["close"]
    series = {}
    for t, c in zip(ts, close):
        if c is None:                      # 濾掉空值，不然畫圖會斷線
            continue
        d = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
        series[d] = c
    return series


def load_events():
    """讀事件日清單（講師統一提供，六組共用）。"""
    events = []
    with open(BASE / "events.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            events.append((row["date"], row["label"]))
    return events


# ── 關卡三：看
def draw(data, events, dates):
    """把三檔標準化成「起點＝100」再畫，才能比較誰漲得多。
    直接畫價格會變成比誰的股價數字大，那沒有意義。
    """
    fig, ax = plt.subplots(figsize=(12, 6.5))
    for sym, name in TICKERS.items():
        s = data[sym]
        base = s[dates[0]]
        ys = [s[d] / base * 100 for d in dates]
        ax.plot([datetime.strptime(d, "%Y-%m-%d") for d in dates], ys,
                linewidth=2, label=f"{name} {sym}")

    # 事件只在圖上標編號，文字放圖下方對照——直接把標籤寫在圖上會互相重疊看不清楚
    shown = [(d, l) for d, l in events if dates[0] <= d <= dates[-1]]
    top = ax.get_ylim()[1]
    for i, (edate, label) in enumerate(shown, 1):
        x = datetime.strptime(edate, "%Y-%m-%d")
        ax.axvline(x, color="#B50033", linestyle="--", linewidth=1, alpha=0.6)
        ax.annotate(str(i), xy=(x, top), xytext=(0, -6), textcoords="offset points",
                    fontsize=9, color="white", ha="center", va="top",
                    bbox=dict(boxstyle="circle,pad=0.22", fc="#B50033", ec="none"))
    # 事件說明太長，分兩行放，避免右邊被裁掉
    items = [f"{i}. {d} {l}" for i, (d, l) in enumerate(shown, 1)]
    half = (len(items) + 1) // 2
    fig.text(0.012, 0.032, "    ".join(items[:half]), fontsize=8.5, color="#454E5C")
    fig.text(0.012, 0.008, "    ".join(items[half:]), fontsize=8.5, color="#454E5C")

    ax.axhline(100, color="#999999", linewidth=0.8)
    ax.set_title(f"{TITLE}（起點＝100，{dates[0]} ~ {dates[-1]}）", fontsize=14)
    ax.set_ylabel("相對走勢（起點＝100）")
    ax.legend(loc="center left")
    ax.grid(alpha=0.3)
    fig.tight_layout(rect=(0, 0.075, 1, 1))
    out = BASE / "chart.png"
    fig.savefig(out, dpi=150)
    print(f"  [看] 走勢圖已存：{out.name}")


# ── 關卡四：監控化（重跑就更新）＋輸出一頁摘要
def summarize(data, events, dates):
    lines = []
    lines.append(f"# {TITLE}")
    lines.append("")
    lines.append(f"資料期間：{dates[0]} ~ {dates[-1]}（共 {len(dates)} 個交易日）")
    lines.append(f"產生時間：{datetime.now():%Y-%m-%d %H:%M}")
    lines.append("")
    lines.append("## 一、整段期間的表現")
    lines.append("")
    lines.append("| 標的 | 起點價 | 最新價 | 期間漲跌 |")
    lines.append("|---|---|---|---|")
    for sym, name in TICKERS.items():
        s = data[sym]
        first, last = s[dates[0]], s[dates[-1]]
        pct = (last / first - 1) * 100
        lines.append(f"| {name} {sym} | {first:.2f} | {last:.2f} | {pct:+.1f}% |")
    lines.append("")

    lines.append("## 二、事件日前後 5 個交易日的反應")
    lines.append("")
    lines.append("| 事件日 | 事件 | " + " | ".join(TICKERS[s] for s in TICKERS) + " |")
    lines.append("|---|---|" + "---|" * len(TICKERS))
    for edate, label in events:
        if edate < dates[0] or edate > dates[-1]:
            continue
        idx = next((i for i, d in enumerate(dates) if d >= edate), None)
        if idx is None:
            continue
        a, b = max(0, idx - 5), min(len(dates) - 1, idx + 5)
        cells = []
        for sym in TICKERS:
            s = data[sym]
            chg = (s[dates[b]] / s[dates[a]] - 1) * 100
            cells.append(f"{chg:+.1f}%")
        lines.append(f"| {edate} | {label} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("> 事件日若非交易日，取其後第一個交易日；前後各取 5 個交易日計算。")
    lines.append("> 這是價格變化的紀錄，不是因果證明——同一段期間還有其他事情在發生。")

    out = BASE / "summary.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  [監控化] 摘要已存：{out.name}")
    return "\n".join(lines)


def main():
    print(f"=== {TITLE} ===")
    data = {}
    for sym in TICKERS:
        data[sym] = to_series(fetch_raw(sym))

    # 三檔都有資料的日期才留（對齊，缺一天就整天不用）
    common = set.intersection(*(set(s) for s in data.values()))
    dates = sorted(common)
    print(f"  [理] 三檔共同交易日：{len(dates)} 天（{dates[0]} ~ {dates[-1]}）")

    events = load_events()
    draw(data, events, dates)
    summarize(data, events, dates)
    print("完成。重跑一次就會更新到最新交易日。")


if __name__ == "__main__":
    main()
