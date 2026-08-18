# -*- coding: utf-8 -*-
"""
資料源探測：新台幣匯率與美元指數（公開資料源）

用途：課程的外匯與指數題目走群益 CTA 平台，但 CTA 沒有新台幣貨幣對、
也沒有美元指數。要看這兩個，就用這支腳本抓公開資料源。

抓什麼（皆為 Yahoo chart 端點，2026-08-17 實測可用）：
  TWD=X     美元兌新台幣（近一年 263 筆）
  ^NYICDX   ICE 美元指數（近一年 251 筆，無空值，優先用這個代號）
  JPY=X     美元兌日圓（對照用）
  KRW=X     美元兌韓元（對照用）

已知的坑：
  1. Yahoo 只給中價，沒有買入／賣出雙向報價——報告要寫明用的是中價。
  2. 這是非官方端點，格式可能隨時被改，不要假設永遠可用。
  3. 最後一筆常是「當下即時快照」而非完整交易日，畫圖前先判斷要不要剔除。
  4. 美元指數另有代號 DX-Y.NYB，指的是同一個指數，但實測有 52 個空值，
     所以優先用 ^NYICDX。
  5. 台灣銀行牌告匯率（rate.bot.com.tw）會被機器人偵測攔下，需要瀏覽器執行
     JavaScript 才能通過，本課程不繞過這類保護，因此不列為可用路徑。

用法：python -X utf8 probe-fx.py
"""
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
TIMEOUT = 20

OUT_DIR = Path(__file__).resolve().parent
BACKUP_DIR = OUT_DIR / "output"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = {
    "TWD=X": "USD/TWD 美元兌新台幣",
    "^NYICDX": "ICE 美元指數",
    "JPY=X": "USD/JPY 美元兌日圓",
    "KRW=X": "USD/KRW 美元兌韓元",
}


def fetch_with_retry(url, params):
    last_err = None
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[重試 {attempt+1}] {url} -> {e}")
            time.sleep(1)
    raise RuntimeError(f"連續失敗：{url} / {last_err}")


def probe_yahoo(symbol: str, name: str):
    print(f"\n=== (a) Yahoo chart: {symbol} ({name}) ===")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    resp = fetch_with_retry(url, {"range": "1y", "interval": "1d"})
    data = resp.json()
    result = data["chart"]["result"][0]
    meta = result["meta"]
    ts = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    print(f"代號有效：是。longName={meta.get('longName')}, 時區={meta.get('exchangeTimezoneName')} "
          f"(gmtoffset={meta.get('gmtoffset')})")
    print(f"筆數：{len(ts)}")
    first_dt = datetime.fromtimestamp(ts[0], tz=timezone.utc)
    last_dt = datetime.fromtimestamp(ts[-1], tz=timezone.utc)
    print(f"日期範圍（UTC）：{first_dt.date()} ~ {last_dt.date()}")
    print("欄位：", list(quote.keys()), "（只有 open/high/low/close，無獨立買入/賣出價——這是中價/收盤價，非牌告買賣價）")

    rows = []
    for i, t in enumerate(ts):
        dt = datetime.fromtimestamp(t, tz=timezone.utc)
        rows.append(
            {
                "date_utc": dt.strftime("%Y-%m-%d"),
                "timestamp": t,
                "open": quote["open"][i],
                "high": quote["high"][i],
                "low": quote["low"][i],
                "close": quote["close"][i],
            }
        )

    sample_path = BACKUP_DIR / f"sample-fx-yahoo-{symbol.replace('=', '').replace('^', '')}.csv"
    with open(sample_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["date_utc", "timestamp", "open", "high", "low", "close"])
        writer.writeheader()
        for row in rows[:20]:
            writer.writerow(row)
    print(f"樣本已存：{sample_path}")

    backup_path = BACKUP_DIR / f"fx-yahoo-{symbol.replace('=', '').replace('^', '')}-{datetime.now():%Y-%m-%d}.csv"
    with open(backup_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["date_utc", "timestamp", "open", "high", "low", "close"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"備援已存：{backup_path}（近一年，{len(rows)} 筆）")


def probe_bot_history():
    print("\n=== (b) 台灣銀行牌告匯率歷史 CSV ===")
    url = "https://rate.bot.com.tw/xrt?Lang=zh-TW"
    resp = fetch_with_retry(url, {})
    text = resp.text
    if "Challenge Validation" in text or "sec-container" in text:
        print("狀態：被機器人偵測攔下（回傳 JS/加密挑戰頁面，非真實牌告內容）。")
        print("依規範不嘗試繞過 CAPTCHA／機器人偵測，此路徑判定為 ❌ 失敗。")
        print(f"回應片段：{text[:200]}")
    else:
        print(f"回應長度：{len(text)}，未偵測到攔截頁，可能可用（需人工再確認歷史下載連結）。")


def main():
    for symbol, name in SYMBOLS.items():
        probe_yahoo(symbol, name)
    probe_bot_history()


if __name__ == "__main__":
    main()
