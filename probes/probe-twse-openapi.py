# -*- coding: utf-8 -*-
"""
資料源探測：證交所 OpenAPI（題 4 用）
用途：實際 GET 兩個學生適合用的資料集端點，記錄欄位與涵蓋範圍。
用法：python -X utf8 probe-twse-openapi.py
"""
import csv
import json
import time
from pathlib import Path
from datetime import datetime

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}
TIMEOUT = 20

OUT_DIR = Path(__file__).resolve().parent
BACKUP_DIR = OUT_DIR / "output"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# 候選端點 1：個股日成交資訊（全市場當日）
URL_STOCK_DAY_ALL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
# 候選端點 2：每日收盤行情—大盤統計資訊（含加權指數等 267 檔指數）
# 註：openapi.twse.com.tw v1 目前沒有「三大法人買賣超日報」端點（無 T86），
# 改用 MI_INDEX 作為第二個端點示範（中文欄位名，格式與 STOCK_DAY_ALL 不同，適合對照教學）。
URL_MI_INDEX = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"


def fetch(url: str):
    last_err = None
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[重試 {attempt+1}] {url} -> {e}")
            time.sleep(1)
    raise RuntimeError(f"連續失敗：{url} / {last_err}")


def probe_one(name: str, url: str, sample_n: int = 20, backup_all: bool = False):
    print(f"\n=== {name} ===")
    print(f"GET {url}")
    resp = fetch(url)
    print(f"HTTP {resp.status_code}, Content-Type={resp.headers.get('Content-Type')}")
    data = resp.json()
    print(f"筆數：{len(data)}")
    if not data:
        print("(空資料)")
        return
    print("欄位名稱：", list(data[0].keys()))
    print("第 1 筆範例：")
    print(json.dumps(data[0], ensure_ascii=False, indent=2))

    fieldnames = list(data[0].keys())
    sample_path = BACKUP_DIR / f"sample-twse-openapi-{name}.csv"
    with open(sample_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in data[:sample_n]:
            writer.writerow(row)
    print(f"樣本已存：{sample_path}（前 {min(sample_n, len(data))} 筆）")

    if backup_all:
        backup_path = BACKUP_DIR / f"twse-openapi-{name}-{datetime.now():%Y-%m-%d}.csv"
        with open(backup_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                writer.writerow(row)
        print(f"備援已存：{backup_path}（全部 {len(data)} 筆＝當日全表）")


def main():
    probe_one("STOCK_DAY_ALL", URL_STOCK_DAY_ALL, backup_all=True)
    probe_one("MI_INDEX", URL_MI_INDEX, backup_all=True)


if __name__ == "__main__":
    main()
