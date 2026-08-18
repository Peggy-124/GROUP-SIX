# -*- coding: utf-8 -*-
"""
資料處理與計量分析模組 (Data Processor)
負責交易日對齊、基期 100 標準化、等權重族群編制、滾動相關係數、領先落後交叉相關分析與事件研究分析。
"""
from datetime import datetime, timedelta
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
from config import DATA_DIR, LEAD_LAG_DAYS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def build_aligned_price_dataframe(
    fx_dict: Dict[str, Any],
    stock_dict: Dict[str, Any]
) -> pd.DataFrame:
    """
    將所有匯率與股票的歷史收盤價對齊到同一個交易日曆上
    使用 forward-fill 處理跨國/跨市場開休市差異
    """
    series_map = {}

    for sym, data in fx_dict.items():
        if data.get("dates") and data.get("close"):
            s = pd.Series(
                data=data["close"],
                index=pd.to_datetime(data["dates"]),
                name=sym
            )
            # 去除重複索引
            s = s[~s.index.duplicated(keep="last")]
            series_map[sym] = s

    for sym, data in stock_dict.items():
        if data.get("dates") and data.get("close"):
            s = pd.Series(
                data=data["close"],
                index=pd.to_datetime(data["dates"]),
                name=sym
            )
            s = s[~s.index.duplicated(keep="last")]
            series_map[sym] = s

    if not series_map:
        return pd.DataFrame()

    df_prices = pd.DataFrame(series_map)
    df_prices.sort_index(inplace=True)

    # 假日與開盤日交錯填補 (前向填補，再後向填補開頭)
    df_prices = df_prices.ffill().bfill()
    return df_prices


def filter_by_period(
    df: pd.DataFrame,
    period_str: str = "1y",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> pd.DataFrame:
    """依據期間代碼或自訂起訖日篩選資料"""
    if df.empty:
        return df

    if period_str == "custom" and start_date and end_date:
        s_dt = pd.to_datetime(start_date)
        e_dt = pd.to_datetime(end_date)
    else:
        last_dt = df.index.max()
        days_map = {
            "1mo": 31,
            "1 個月": 31,
            "3mo": 92,
            "3 個月": 92,
            "6mo": 183,
            "6 個月": 183,
            "1y": 365,
            "1 年": 365,
            "2y": 730,
            "2 年": 730,
        }
        days = days_map.get(period_str, 365)
        s_dt = last_dt - timedelta(days=days)
        e_dt = last_dt

    filtered = df.loc[(df.index >= s_dt) & (df.index <= e_dt)].copy()
    if filtered.empty:
        # 若篩選過嚴，回傳原始資料
        return df.copy()
    return filtered


def normalize_base100(df: pd.DataFrame) -> pd.DataFrame:
    """轉換為基期 100 (Pt / P0 * 100)"""
    if df.empty:
        return df
    first_valid = df.iloc[0]
    # 避免除以 0
    first_valid = first_valid.replace(0, np.nan)
    norm = (df / first_valid) * 100.0
    return norm


def calculate_returns(df: pd.DataFrame) -> pd.DataFrame:
    """計算每日報酬率 (百分比)"""
    return df.pct_change().dropna(how="all")


def build_sector_indices(
    df_prices: pd.DataFrame,
    sectors_dict: Dict[str, Dict[str, Any]]
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    建立各出口族群的等權重指數與等權重日報酬
    回傳: (df_sector_prices, df_sector_norm, df_sector_returns)
    """
    sector_daily_returns = {}

    df_stock_returns = df_prices.pct_change()

    for sec_name, info in sectors_dict.items():
        valid_stocks = [s for s in info["stocks"].keys() if s in df_stock_returns.columns]
        if valid_stocks:
            # 族群內各成分股等權重平均日報酬
            sec_ret = df_stock_returns[valid_stocks].mean(axis=1)
            sector_daily_returns[sec_name] = sec_ret

    df_sec_returns = pd.DataFrame(sector_daily_returns)

    # 累計重構指數 (基期 100)
    df_sec_norm = (1.0 + df_sec_returns.fillna(0)).cumprod() * 100.0
    # 調整第一天為 100
    if not df_sec_norm.empty:
        first_idx = df_prices.index[0]
        if first_idx not in df_sec_norm.index:
            df_sec_norm.loc[first_idx] = 100.0
            df_sec_norm.sort_index(inplace=True)

    return df_sec_norm, df_sec_norm, df_sec_returns


def compute_metrics_summary(df_prices: pd.DataFrame) -> pd.DataFrame:
    """
    計算各標的最新值、5日報酬、20日報酬與區間總報酬率
    """
    if df_prices.empty or len(df_prices) < 2:
        return pd.DataFrame()

    summary_rows = []
    total_len = len(df_prices)

    for col in df_prices.columns:
        s = df_prices[col].dropna()
        if len(s) < 2:
            continue
        latest_val = s.iloc[-1]
        p_start = s.iloc[0]
        total_ret = ((latest_val - p_start) / p_start) * 100.0 if p_start != 0 else 0.0

        ret_5d = ((latest_val - s.iloc[-6]) / s.iloc[-6]) * 100.0 if len(s) >= 6 and s.iloc[-6] != 0 else np.nan
        ret_20d = ((latest_val - s.iloc[-21]) / s.iloc[-21]) * 100.0 if len(s) >= 21 and s.iloc[-21] != 0 else np.nan

        summary_rows.append({
            "標的名稱": col,
            "最新值": latest_val,
            "5日變化率 (%)": ret_5d,
            "20日變化率 (%)": ret_20d,
            "期間累積報酬 (%)": total_ret,
            "最高值": s.max(),
            "最低值": s.min(),
        })

    summary_df = pd.DataFrame(summary_rows)
    return summary_df


def compute_correlation_matrix(
    df_prices: pd.DataFrame,
    method: str = "returns"
) -> pd.DataFrame:
    """
    計算 Pearson 相關係數矩陣
    method: 'returns' (日報酬相關，標準量化作法) 或 'prices' (價格序列相關)
    """
    if df_prices.empty:
        return pd.DataFrame()
    if method == "returns":
        df_target = df_prices.pct_change().dropna(how="all")
    else:
        df_target = df_prices
    corr = df_target.corr(method="pearson")
    return corr.round(4)


def compute_rolling_correlation(
    s1: pd.Series,
    s2: pd.Series,
    window: int = 20
) -> pd.Series:
    """計算兩序列 20 日滾動日報酬相關係數"""
    r1 = s1.pct_change()
    r2 = s2.pct_change()
    rolling_corr = r1.rolling(window=window).corr(r2).dropna()
    return rolling_corr


def compute_lead_lag_correlations(
    fx_series: pd.Series,
    stock_series: pd.Series,
    lags: List[int] = LEAD_LAG_DAYS
) -> pd.DataFrame:
    """
    計算匯率相對於股票領先/落後的相關係數
    k > 0: 匯率領先股票 k 天 (用 FX[t-k] 與 Stock[t] 算相關)
    k < 0: 股票領先匯率 |k| 天 (用 FX[t+|k|] 與 Stock[t] 算相關)
    k = 0: 當日同步相關
    """
    fx_ret = fx_series.pct_change()
    stk_ret = stock_series.pct_change()

    results = []
    for k in lags:
        if k > 0:
            # FX 領先：將 FX 序列向下平移 k 期
            s_shifted = fx_ret.shift(k)
            c = s_shifted.corr(stk_ret)
            desc = f"匯率領先 {k} 日"
        elif k < 0:
            # Stock 領先：將 FX 序列向上平移 |k| 期
            s_shifted = fx_ret.shift(k)
            c = s_shifted.corr(stk_ret)
            desc = f"股票領先 {-k} 日"
        else:
            c = fx_ret.corr(stk_ret)
            desc = "當日同步 (Lag 0)"

        results.append({
            "Lag_Days": k,
            "關係說明": desc,
            "相關係數 (r)": round(c, 4) if pd.notnull(c) else 0.0
        })

    return pd.DataFrame(results)


def perform_event_study(
    df_prices: pd.DataFrame,
    event_date_str: str,
    event_label: str,
    window: int = 5
) -> Dict[str, Any]:
    """
    執行單一重大事件日前後 N 個交易日的報酬與走勢分析
    回傳: {
       'valid': bool,
       'event_date': str,
       't0_date': str,
       'window_df': pd.DataFrame (基期為 t0-5 = 100),
       'summary_table': pd.DataFrame (前後 5 日變化率),
       'message': str
    }
    """
    if df_prices.empty:
        return {"valid": False, "message": "無價格資料"}

    dt_target = pd.to_datetime(event_date_str)
    # 尋找最近且小於等於或最靠近事件日的交易日
    available_dates = df_prices.index
    exact_match = available_dates[available_dates == dt_target]

    if len(exact_match) > 0:
        t0_idx = df_prices.index.get_loc(exact_match[0])
    else:
        # 取大於等於事件日的第一個交易日
        future_dates = available_dates[available_dates >= dt_target]
        if len(future_dates) > 0:
            t0_idx = df_prices.index.get_loc(future_dates[0])
        else:
            t0_idx = len(df_prices) - 1

    t0_date = df_prices.index[t0_idx].strftime("%Y-%m-%d")

    start_idx = max(0, t0_idx - window)
    end_idx = min(len(df_prices) - 1, t0_idx + window)

    sub_df = df_prices.iloc[start_idx : end_idx + 1].copy()
    if len(sub_df) < 3:
        return {
            "valid": False,
            "event_date": event_date_str,
            "message": f"事件日 {event_date_str} 附近交易日不足"
        }

    # 標準化為以 t0-window 或子區間第一天為 100
    norm_sub_df = (sub_df / sub_df.iloc[0]) * 100.0

    # 建立前後 5 日報酬比較表
    summary_rows = []
    p_start = sub_df.iloc[0]
    p_t0 = df_prices.iloc[t0_idx]
    p_end = sub_df.iloc[-1]

    for col in sub_df.columns:
        val_start = p_start[col]
        val_t0 = p_t0[col]
        val_end = p_end[col]

        pre_ret = ((val_t0 - val_start) / val_start) * 100.0 if val_start != 0 else 0.0
        post_ret = ((val_end - val_t0) / val_t0) * 100.0 if val_t0 != 0 else 0.0
        total_window_ret = ((val_end - val_start) / val_start) * 100.0 if val_start != 0 else 0.0

        summary_rows.append({
            "標的名稱": col,
            "前 5 日報酬 (%)": round(pre_ret, 2),
            "後 5 日報酬 (%)": round(post_ret, 2),
            "前後 10 日總變化 (%)": round(total_window_ret, 2),
            "事件日當天值": round(val_t0, 3),
        })

    summary_df = pd.DataFrame(summary_rows)

    return {
        "valid": True,
        "event_date": event_date_str,
        "actual_t0": t0_date,
        "event_label": event_label,
        "norm_window_df": norm_sub_df,
        "summary_table": summary_df,
        "days_before": t0_idx - start_idx,
        "days_after": end_idx - t0_idx,
    }


def save_processed_datasets(
    df_aligned: pd.DataFrame,
    df_sectors: pd.DataFrame,
    df_returns: pd.DataFrame
) -> None:
    """將清洗與對齊後的資料輸出到 data/ 目錄"""
    try:
        df_aligned.to_csv(DATA_DIR / "fx_stocks_aligned.csv", encoding="utf-8-sig")
        df_sectors.to_csv(DATA_DIR / "sector_indices.csv", encoding="utf-8-sig")
        df_returns.to_csv(DATA_DIR / "daily_returns.csv", encoding="utf-8-sig")
        logger.info(f"已儲存處理後資料集至 {DATA_DIR}")
    except Exception as e:
        logger.error(f"儲存資料集至 data/ 失敗: {e}")
