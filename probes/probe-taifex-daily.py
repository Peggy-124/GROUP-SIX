# -*- coding: utf-8 -*-
"""
資料源探測：期交所盤後資訊（題 5 用）— 台指期（TX）每日行情
用途：實際 POST 抓近 5 個交易日的台指期每日行情，記錄請求方式、格式、假日處理。
用法：python -X utf8 probe-taifex-daily.py

已知：期交所「期貨每日交易行情查詢」頁面是表單 POST 查詢，沒有直接的 CSV 下載連結，
回傳的是 HTML 表格（近月契約在最上面一列）。本探測腳本用 re 解析表格列，
不依賴 pandas / bs4，符合「requests＋標準庫即可」的教學規範。
"""
import csv
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

URL = "https://www.taifex.com.tw/cht/3/futDailyMarketReport"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
TIMEOUT = 20

OUT_DIR = Path(__file__).resolve().parent
BACKUP_DIR = OUT_DIR / "output"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# 表格欄位（依網頁實際欄位順序，近月契約列）
FIELDS = [
    "契約", "到期月份(週別)", "開盤價", "最高價", "最低價", "最後成交價",
    "漲跌價", "漲跌%", "成交量", "結算價", "未沖銷契約量",
    "最佳買價", "最佳賣價", "歷史最高價", "歷史最低價",
]


def fetch_one_day(date_str: str, commodity_id: str = "TX"):
    """POST 查詢單一交易日的台指期每日行情。date_str 格式 YYYY/MM/DD。"""
    data = {
        "queryType": "2",
        "marketCode": "1",
        "MarketCode": "1",
        "commodity_id": commodity_id,
        "commodity_idt": commodity_id,
        "queryDate": date_str,
    }
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.post(URL, headers=HEADERS, data=data, timeout=TIMEOUT)
            if resp.status_code == 429:
                # 期交所有限速保護：短時間內請求太多次就會回 429。
                # 課堂上多組同時抓很容易踩到，這裡採「愈退愈久」的等待再重試。
                wait = 10 * (attempt + 1)
                print(f"[限速] {date_str} 被期交所擋下（429），等 {wait} 秒再試……")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.text
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[重試 {attempt+1}] {date_str} -> {e}")
            time.sleep(3)
    raise RuntimeError(
        f"連續失敗：{date_str} / {last_err}\n"
        "如果訊息是 429 Too Many Requests，代表被期交所限速了。做法：\n"
        "  1. 等 5–10 分鐘再跑，或把 TARGET_DAYS 調小（例如 5）。\n"
        "  2. 課堂上請改用講師提供的備援資料檔先繼續做，課後再自己抓。\n"
        "  3. 不要用縮短 SLEEP_SEC 的方式硬打，只會被擋更久。"
    )


def parse_rows(html: str):
    """從回傳 HTML 抓第一個資料表格（一般行情表），逐列解析成 dict list。
    坑：期交所網頁的 <td>／<TD> 大小寫混用，regex 一定要用 re.IGNORECASE，
    否則會漏掉大寫的 <TD>，造成後面欄位全部錯位（曾實測到成交量被錯位成「-」）。
    """
    tables = re.findall(r"<table[\s\S]*?</table>", html, re.IGNORECASE)
    if not tables:
        return []
    # 第一個含資料的表格通常就是一般行情表
    target = None
    for t in tables:
        if "契約" in t and "開盤價" in t:
            target = t
            break
    if target is None:
        return []

    rows = re.findall(r"<tr[\s\S]*?</tr>", target, re.IGNORECASE)
    records = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", row, re.IGNORECASE)
        if not cells:
            continue
        cleaned = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        cleaned = [re.sub(r"\s+", "", c) for c in cleaned]
        if len(cleaned) < 14:
            continue
        # 第一欄應為契約代碼（如 TX）
        if not re.match(r"^[A-Z0-9]+$", cleaned[0]):
            continue
        records.append(cleaned)
    return records


def trading_days_back(n: int, from_date: datetime):
    """回推 n 個「非週末」日期（不含國定假日判斷，假日會在查詢時發現無資料）。"""
    days = []
    d = from_date
    while len(days) < n:
        if d.weekday() < 5:  # 0=Mon .. 4=Fri
            days.append(d)
        d -= timedelta(days=1)
    return days


TARGET_DAYS = 20   # 要抓幾個交易日（調大就抓更久；每天一個請求，抓越多越慢）
SLEEP_SEC = 1.5    # 每次請求之間的禮貌延遲，調太小會被期交所限速擋下（429）
SAMPLE_DAYS = 5    # 樣本檔只留前幾筆，給學生看格式用


def main():
    today = datetime.now()  # 動態取當天，開課前重跑會自動抓到最新交易日
    # 多抓一些日曆日，扣掉週末與國定假日後留下 TARGET_DAYS 個有資料的
    candidates = trading_days_back(int(TARGET_DAYS * 1.6) + 10, today)

    all_records = []
    ok_days = 0
    for d in candidates:
        date_str = d.strftime("%Y/%m/%d")
        print(f"\n查詢 {date_str} ...")
        html = fetch_one_day(date_str)
        records = parse_rows(html)
        if not records:
            print(f"  -> 無資料（可能為假日或非交易日）")
            continue
        near_month = records[0]  # 近月契約在第一列
        print(f"  -> 近月契約：{near_month[:6]} ...")
        all_records.append([date_str] + near_month)
        ok_days += 1
        if ok_days >= TARGET_DAYS:
            break
        time.sleep(SLEEP_SEC)  # 禮貌延遲，別調小

    if not all_records:
        print("全部查詢失敗，無法產生樣本/備援檔")
        return

    header = ["查詢日期"] + FIELDS
    sample_path = BACKUP_DIR / "sample-taifex-daily.csv"
    with open(sample_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(all_records[:SAMPLE_DAYS])
    print(f"\n樣本已存：{sample_path}（前 {min(SAMPLE_DAYS, len(all_records))} 個交易日 x TX 近月契約）")

    backup_path = BACKUP_DIR / f"taifex-daily-TX-{datetime.now():%Y-%m-%d}.csv"
    with open(backup_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(all_records)
    print(f"備援已存：{backup_path}")


if __name__ == "__main__":
    main()
