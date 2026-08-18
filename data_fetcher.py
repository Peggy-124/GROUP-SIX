# -*- coding: utf-8 -*-
"""
資料抓取模組 (Data Fetcher)
支援 Yahoo Finance Chart API 抓取匯率、美元指數與台股歷史日線，
具備逾時重試、非官方端點異常防護、原始資料 raw/ 自動存檔與本機快取備援機制。
"""
import csv
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import requests
from config import CACHE_DIR, DEFAULT_FX_SYMBOLS, RAW_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
TIMEOUT = 15


def sanitize_filename(symbol: str) -> str:
    """轉換代號為合法檔名"""
    return re.sub(r'[\\/*?:"<>|^=]', "", symbol).replace(".", "_")


def normalize_stock_symbol(symbol: str) -> str:
    """標準化台股代號，若無後綴則自動補上 .TW"""
    s = symbol.strip().upper()
    if re.match(r"^\d{4,5}$", s):
        return f"{s}.TW"
    return s


def fetch_yahoo_chart(
    symbol: str,
    range_str: str = "2y",
    interval: str = "1d",
    max_retries: int = 3,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    抓取 Yahoo Finance Chart API 資料
    若抓取失敗，自動回退使用本機 raw/ 快取檔
    """
    sanitized = sanitize_filename(symbol)
    raw_json_path = RAW_DIR / f"{sanitized}.json"
    raw_csv_path = RAW_DIR / f"{sanitized}.csv"

    # 若非強制更新且快取檔案夠新（今天抓過），可直接讀取快取
    # 這裡預設每次嘗試聯網，失敗時 fallback 到本機
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": range_str, "interval": interval}

    last_error = None
    data = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"正在抓取 {symbol} (嘗試 {attempt}/{max_retries})...")
            resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
            if resp.status_code == 200:
                json_data = resp.json()
                chart = json_data.get("chart", {})
                if chart.get("error") is None and chart.get("result"):
                    data = chart["result"][0]
                    # 儲存原始 JSON
                    with open(raw_json_path, "w", encoding="utf-8") as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=2)
                    break
                else:
                    last_error = chart.get("error", "未知錯誤")
            else:
                last_error = f"HTTP {resp.status_code}: {resp.text[:100]}"
        except Exception as e:
            last_error = str(e)
            logger.warning(f"{symbol} 抓取異常: {e}")

        if attempt < max_retries:
            time.sleep(1.0 * attempt)

    # 如果抓取成功，解析並輸出
    if data:
        parsed = _parse_yahoo_result(symbol, data, is_cached=False)
        _save_raw_csv(raw_csv_path, parsed)
        return parsed

    # 聯網失敗：嘗試讀取本機快取
    logger.warning(f"無法從網路獲取 {symbol} 最新資料 ({last_error})，嘗試載入本機快取...")
    if raw_json_path.exists():
        try:
            with open(raw_json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
                result = json_data["chart"]["result"][0]
                parsed = _parse_yahoo_result(symbol, result, is_cached=True)
                logger.info(f"成功載入 {symbol} 本機快取 JSON 資料 ({len(parsed['dates'])} 筆)")
                return parsed
        except Exception as e:
            logger.error(f"讀取本機 JSON 快取失敗: {e}")

    if raw_csv_path.exists():
        try:
            parsed = _load_raw_csv(symbol, raw_csv_path)
            logger.info(f"成功載入 {symbol} 本機快取 CSV 資料 ({len(parsed['dates'])} 筆)")
            return parsed
        except Exception as e:
            logger.error(f"讀取本機 CSV 快取失敗: {e}")

    raise RuntimeError(f"無法取得 {symbol} 資料（網路失敗且無可用本機快取）：{last_error}")


def _parse_yahoo_result(symbol: str, result: Dict[str, Any], is_cached: bool) -> Dict[str, Any]:
    """解析 Yahoo Chart API 回傳資料"""
    meta = result.get("meta", {})
    timestamps = result.get("timestamp", [])
    indicators = result.get("indicators", {})
    quotes = indicators.get("quote", [{}])[0]

    opens = quotes.get("open", [])
    highs = quotes.get("high", [])
    lows = quotes.get("low", [])
    closes = quotes.get("close", [])
    volumes = quotes.get("volume", [])

    dates = []
    clean_timestamps = []
    clean_open = []
    clean_high = []
    clean_low = []
    clean_close = []
    clean_volume = []

    for i, ts in enumerate(timestamps):
        if ts is None:
            continue
        c = closes[i] if i < len(closes) else None
        # 如果收盤價為 None 則跳過該交易點
        if c is None:
            continue

        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")

        dates.append(date_str)
        clean_timestamps.append(ts)
        clean_open.append(opens[i] if i < len(opens) and opens[i] is not None else c)
        clean_high.append(highs[i] if i < len(highs) and highs[i] is not None else c)
        clean_low.append(lows[i] if i < len(lows) and lows[i] is not None else c)
        clean_close.append(c)
        clean_volume.append(volumes[i] if i < len(volumes) and volumes[i] is not None else 0)

    is_fx = ("=X" in symbol) or ("^" in symbol)
    long_name = meta.get("longName") or meta.get("shortName") or DEFAULT_FX_SYMBOLS.get(symbol, {}).get("name", symbol)

    return {
        "symbol": symbol,
        "name": long_name,
        "timestamps": clean_timestamps,
        "dates": dates,
        "open": clean_open,
        "high": clean_high,
        "low": clean_low,
        "close": clean_close,
        "volume": clean_volume,
        "is_cached": is_cached,
        "source": "Yahoo Finance Chart API",
        "is_mid_price": is_fx,
        "currency": meta.get("currency", "USD"),
        "timezone": meta.get("exchangeTimezoneName", "UTC"),
        "last_fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _save_raw_csv(csv_path: Path, parsed: Dict[str, Any]) -> None:
    """將解析後的資料存檔為 raw CSV"""
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["date", "timestamp", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for i in range(len(parsed["dates"])):
            writer.writerow({
                "date": parsed["dates"][i],
                "timestamp": parsed["timestamps"][i],
                "open": parsed["open"][i],
                "high": parsed["high"][i],
                "low": parsed["low"][i],
                "close": parsed["close"][i],
                "volume": parsed["volume"][i],
            })


def _load_raw_csv(symbol: str, csv_path: Path) -> Dict[str, Any]:
    """從 raw CSV 載入快取"""
    dates, timestamps, opens, highs, lows, closes, volumes = [], [], [], [], [], [], []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dates.append(row["date"])
            timestamps.append(int(row["timestamp"]))
            opens.append(float(row["open"]))
            highs.append(float(row["high"]))
            lows.append(float(row["low"]))
            closes.append(float(row["close"]))
            volumes.append(float(row.get("volume", 0) or 0))

    is_fx = ("=X" in symbol) or ("^" in symbol)
    name = DEFAULT_FX_SYMBOLS.get(symbol, {}).get("name", symbol)

    return {
        "symbol": symbol,
        "name": name,
        "timestamps": timestamps,
        "dates": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "is_cached": True,
        "source": "本機快取 CSV",
        "is_mid_price": is_fx,
        "currency": "USD" if is_fx else "TWD",
        "timezone": "UTC",
        "last_fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S (快取)"),
    }


def fetch_all_data(
    fx_symbols: List[str],
    sector_stocks_map: Dict[str, Dict[str, str]],
    range_str: str = "2y",
    force_refresh: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """
    批次抓取所有匯率與股票資料
    回傳: (fx_data_dict, stock_data_dict, error_list)
    """
    fx_data = {}
    stock_data = {}
    errors = []

    # 1. 抓取匯率與美元指數
    for sym in fx_symbols:
        try:
            res = fetch_yahoo_chart(sym, range_str=range_str, force_refresh=force_refresh)
            fx_data[sym] = res
        except Exception as e:
            errors.append(f"匯率 {sym} 抓取失敗: {e}")
            logger.error(f"匯率 {sym} 抓取失敗: {e}")

    # 2. 抓取所有族群股票
    all_stocks = {}
    for sector_name, info in sector_stocks_map.items():
        for sym, name in info["stocks"].items():
            all_stocks[sym] = name

    for sym, name in all_stocks.items():
        norm_sym = normalize_stock_symbol(sym)
        try:
            res = fetch_yahoo_chart(norm_sym, range_str=range_str, force_refresh=force_refresh)
            # 覆蓋自訂名稱
            res["name"] = f"{sym.replace('.TW', '')} {name}"
            stock_data[sym] = res
        except Exception as e:
            errors.append(f"股票 {sym} ({name}) 抓取失敗: {e}")
            logger.error(f"股票 {sym} ({name}) 抓取失敗: {e}")

    return fx_data, stock_data, errors
