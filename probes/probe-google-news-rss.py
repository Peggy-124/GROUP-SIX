# -*- coding: utf-8 -*-
"""
資料源探測：Google News RSS（題 1、2 用）
用途：用關鍵字查詢 Google News RSS，解析出 標題／日期／連結。
用法：python -X utf8 probe-google-news-rss.py
"""
import csv
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
TIMEOUT = 20

# 學生實際會用到的關鍵字（題1、2：關稅×半導體）
QUERY = "關稅 半導體"
URL = (
    f"https://news.google.com/rss/search?q={quote(QUERY)}"
    "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
)

OUT_DIR = Path(__file__).resolve().parent
BACKUP_DIR = OUT_DIR / "output"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_CSV = BACKUP_DIR / "sample-google-news-rss.csv"


def fetch(url: str) -> requests.Response:
    last_err = None
    for attempt in range(2):  # 失敗重試 1 次
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[重試 {attempt+1}] {e}")
            time.sleep(1)
    raise RuntimeError(f"連續失敗：{last_err}")


def parse_rss(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        pub_date = item.findtext("pubDate", default="").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""
        items.append(
            {"title": title, "link": link, "pubDate": pub_date, "source": source}
        )
    return items


def main():
    print(f"GET {URL}")
    resp = fetch(URL)
    print(f"HTTP {resp.status_code}, 編碼={resp.encoding}, 內容長度={len(resp.content)} bytes")

    items = parse_rss(resp.content)
    print(f"筆數：{len(items)}")

    # 檢查重複標題
    titles = [it["title"] for it in items]
    dup_count = len(titles) - len(set(titles))
    print(f"重複標題數：{dup_count}")

    # 顯示前 5 筆檢查日期格式
    for it in items[:5]:
        print(f"  - [{it['pubDate']}] {it['title'][:40]} ({it['source']})")

    # 存樣本檔（前 20 筆）
    with open(SAMPLE_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["pubDate", "source", "title", "link"])
        writer.writeheader()
        for it in items[:20]:
            writer.writerow(
                {
                    "pubDate": it["pubDate"],
                    "source": it["source"],
                    "title": it["title"],
                    "link": it["link"],
                }
            )
    print(f"樣本已存：{SAMPLE_CSV}")

    # 備援檔：近 50 則（學生上課直接可用）
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"google-news-rss-{datetime.now():%Y-%m-%d}.csv"
    with open(backup_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["pubDate", "source", "title", "link"])
        writer.writeheader()
        for it in items[:50]:
            writer.writerow(
                {
                    "pubDate": it["pubDate"],
                    "source": it["source"],
                    "title": it["title"],
                    "link": it["link"],
                }
            )
    print(f"備援已存：{backup_path}（{min(50, len(items))} 筆）")


if __name__ == "__main__":
    main()
