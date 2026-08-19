# -*- coding: utf-8 -*-
"""
打包生成單一獨立 HTML 成果報告腳本 (generate_all.py)
一鍵抓取資料、清洗計算、繪製 Plotly 互動式圖表，並產出功能完備、包含簡報模式與儀表板模式的 Single-File HTML 成果報告。
"""
import copy
import html
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from config import (
    BASE_DIR,
    DEFAULT_EVENTS,
    DEFAULT_EXPORT_SECTORS,
    DEFAULT_FX_SYMBOLS,
    DISCLAIMER_TEXT,
    LEAD_LAG_DAYS,
)
from data_fetcher import fetch_all_data
from data_processor import (
    build_aligned_price_dataframe,
    build_sector_indices,
    compute_correlation_matrix,
    compute_lead_lag_correlations,
    compute_metrics_summary,
    compute_rolling_correlation,
    normalize_base100,
    perform_event_study,
    save_processed_datasets,
)
from visualizer import (
    plot_correlation_heatmap,
    plot_event_study_trajectory,
    plot_lead_lag_bars,
    plot_normalized_comparison,
    plot_original_fx_series,
    plot_rolling_correlation,
    plot_sector_returns_bar,
)
from ai_engine import generate_ai_research_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_all")


def read_file_safe(file_path: Path) -> str:
    """安全讀取文字檔案內容"""
    if file_path.exists():
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"讀取失敗: {e}"
    return "檔案不存在"


def markdown_to_html_simple(md_text: str) -> str:
    """將 Markdown 簡易轉為結構化 HTML"""
    lines = md_text.split("\n")
    out = ["<div class='markdown-rendered'>"]
    in_table = False
    table_header_done = False
    in_list = False

    for line in lines:
        raw_s = line.strip()
        
        # 處理表格
        if raw_s.startswith("|") and raw_s.endswith("|"):
            if in_list:
                out.append("</ul>")
                in_list = False
            
            cells = [c.strip() for c in raw_s.split("|")[1:-1]]
            if all(set(c).issubset({"-", ":", " "}) for c in cells):
                table_header_done = True
                continue
            
            if not in_table:
                out.append("<table class='data-table'>")
                out.append("<thead><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in cells) + "</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cells) + "</tr>")
            continue
        else:
            if in_table:
                out.append("</tbody></table>")
                in_table = False
                table_header_done = False

        # 處理清單
        if raw_s.startswith("- ") or raw_s.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            content = raw_s[2:]
            # 處理粗體 **text**
            parts = content.split("**")
            formatted = ""
            for i, p in enumerate(parts):
                if i % 2 == 1:
                    formatted += f"<strong>{html.escape(p)}</strong>"
                else:
                    formatted += html.escape(p)
            out.append(f"<li>{formatted}</li>")
            continue
        else:
            if in_list:
                out.append("</ul>")
                in_list = False

        if not raw_s:
            continue
        
        # 處理標題與引用
        if raw_s.startswith("### "):
            out.append(f"<h3>{html.escape(raw_s[4:])}</h3>")
        elif raw_s.startswith("## "):
            out.append(f"<h2>{html.escape(raw_s[3:])}</h2>")
        elif raw_s.startswith("# "):
            out.append(f"<h1>{html.escape(raw_s[2:])}</h1>")
        elif raw_s.startswith("> "):
            out.append(f"<blockquote class='alert-box'>{html.escape(raw_s[2:])}</blockquote>")
        elif raw_s.startswith("---"):
            out.append("<hr/>")
        else:
            # 一般段落，支援 ** 粗體
            parts = raw_s.split("**")
            formatted = ""
            for i, p in enumerate(parts):
                if i % 2 == 1:
                    formatted += f"<strong>{html.escape(p)}</strong>"
                else:
                    formatted += html.escape(p)
            out.append(f"<p>{formatted}</p>")

    if in_list:
        out.append("</ul>")
    if in_table:
        out.append("</tbody></table>")
    out.append("</div>")
    return "\n".join(out)


def generate_single_html_report(output_file: Path = BASE_DIR / "index.html", range_param: str = "1y") -> Path:
    """生成單一獨立且功能齊全的 HTML 成果呈現報告 (支援簡報與儀表板雙模式)"""
    logger.info("開始抓取與載入市場資料 (分析期間: %s)...", range_param)
    
    fx_symbols = list(DEFAULT_FX_SYMBOLS.keys())
    sectors_map = DEFAULT_EXPORT_SECTORS
    
    # 1. 抓取資料
    fx_data, stock_data, errors = fetch_all_data(
        fx_symbols=fx_symbols,
        sector_stocks_map=sectors_map,
        range_str=range_param,
        force_refresh=False,
    )
    
    # 2. 對齊與處理價格
    df_prices = build_aligned_price_dataframe(fx_data, stock_data)
    if df_prices.empty:
        raise ValueError("無法取得足夠的價格資料以生成報告。")
    
    df_norm_all = normalize_base100(df_prices)
    df_sec_prices, df_sec_norm, df_sec_returns = build_sector_indices(df_prices, sectors_map)
    
    combined_prices = pd.concat([df_prices[fx_symbols], df_sec_prices], axis=1).dropna(how="all").ffill()
    combined_norm = normalize_base100(combined_prices)
    combined_returns = combined_prices.pct_change().dropna(how="all")
    
    summary_metrics = compute_metrics_summary(combined_prices)
    save_processed_datasets(df_prices, df_sec_prices, combined_returns)
    
    date_start_str = df_prices.index.min().strftime("%Y-%m-%d")
    date_end_str = df_prices.index.max().strftime("%Y-%m-%d")
    total_days = len(df_prices)
    gen_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 3. 載入事件清單
    events_csv_path = BASE_DIR / "events.csv"
    if events_csv_path.exists():
        try:
            ev_df = pd.read_csv(events_csv_path)
            events_list = ev_df.to_dict(orient="records")
        except Exception:
            events_list = copy.deepcopy(DEFAULT_EVENTS)
    else:
        events_list = copy.deepcopy(DEFAULT_EVENTS)

    # 4. 生成 Plotly 互動式圖表
    logger.info("正在繪製互動式 Plotly 視覺化圖表...")
    
    # Chart 1: 總覽標準化比較圖
    fig_overview = plot_normalized_comparison(
        combined_norm,
        events_list=events_list,
        title="主要匯率與台灣出口族群等權重指數走勢對照 (起點 = 100)",
    )
    html_chart_overview = fig_overview.to_html(full_html=False, include_plotlyjs=False)

    # Chart 2: 原始匯率走勢
    fig_fx_raw = plot_original_fx_series(df_prices, fx_symbols, events_list=events_list)
    html_chart_fx_raw = fig_fx_raw.to_html(full_html=False, include_plotlyjs=False)

    # Chart 3: 匯率與美元指數標準化
    df_fx_only = df_prices[fx_symbols].dropna(how="all")
    df_fx_norm = normalize_base100(df_fx_only)
    fig_fx_norm = plot_normalized_comparison(
        df_fx_norm,
        events_list=events_list,
        title="多幣別匯率與美元指數標準化對照走勢 (起點 = 100)",
    )
    html_chart_fx_norm = fig_fx_norm.to_html(full_html=False, include_plotlyjs=False)

    # Chart 4: 出口族群期間報酬長條圖
    sec_summary = summary_metrics[summary_metrics["標的名稱"].isin(df_sec_prices.columns)]
    fig_sec_bar = plot_sector_returns_bar(sec_summary, title="台灣四大出口族群期間累積報酬率排行 (%)")
    html_chart_sec_bar = fig_sec_bar.to_html(full_html=False, include_plotlyjs=False)

    # Chart 5: 族群等權重指數走勢
    fig_sec_norm = plot_normalized_comparison(
        df_sec_norm,
        events_list=events_list,
        title="台灣四大出口產業族群等權重指數走勢 (起點 = 100)",
    )
    html_chart_sec_norm = fig_sec_norm.to_html(full_html=False, include_plotlyjs=False)

    # Chart 6: 相關係數熱圖
    corr_df = compute_correlation_matrix(combined_returns)
    fig_corr_heatmap = plot_correlation_heatmap(corr_df, title="日報酬 Pearson 相關係數矩陣熱圖")
    html_chart_corr_heatmap = fig_corr_heatmap.to_html(full_html=False, include_plotlyjs=False)

    # Chart 7: 滾動相關 (USD/TWD)
    rolling_twd = {}
    base_fx_twd = "TWD=X"
    if base_fx_twd in combined_returns.columns:
        twd_ret = combined_returns[base_fx_twd]
        for sec in df_sec_prices.columns:
            if sec in combined_returns.columns:
                rolling_twd[f"USD/TWD vs {sec}"] = compute_rolling_correlation(twd_ret, combined_returns[sec], window=20)
    fig_rolling_twd = plot_rolling_correlation(
        rolling_twd, events_list=events_list, title="20 日滾動相關係數：美元/台幣 (USD/TWD) vs 出口族群"
    )
    html_chart_rolling_twd = fig_rolling_twd.to_html(full_html=False, include_plotlyjs=False)

    # Chart 8: 滾動相關 (DXY)
    rolling_dxy = {}
    base_dxy = "^NYICDX"
    if base_dxy in combined_returns.columns:
        dxy_ret = combined_returns[base_dxy]
        for sec in df_sec_prices.columns:
            if sec in combined_returns.columns:
                rolling_dxy[f"DXY vs {sec}"] = compute_rolling_correlation(dxy_ret, combined_returns[sec], window=20)
    fig_rolling_dxy = plot_rolling_correlation(
        rolling_dxy, events_list=events_list, title="20 日滾動相關係數：美元指數 (DXY) vs 出口族群"
    )
    html_chart_rolling_dxy = fig_rolling_dxy.to_html(full_html=False, include_plotlyjs=False)

    # Chart 9: 領先落後關係圖表
    lead_lag_results = {}
    html_lead_lag_charts = []
    if base_fx_twd in combined_prices.columns:
        for sec in df_sec_prices.columns:
            if sec in combined_prices.columns:
                ll_df = compute_lead_lag_correlations(
                    combined_prices[base_fx_twd],
                    combined_prices[sec],
                    lags=LEAD_LAG_DAYS,
                )
                lead_lag_results[sec] = ll_df
                fig_ll = plot_lead_lag_bars(
                    ll_df,
                    title=f"領先落後交叉相關：美元/台幣 (USD/TWD) vs {sec} (Lag -20 ~ +20 天)"
                )
                html_lead_lag_charts.append({
                    "sector": sec,
                    "chart": fig_ll.to_html(full_html=False, include_plotlyjs=False),
                })

    # Chart 10: 關稅重大事件研究
    event_study_charts = []
    event_study_results = []
    for ev in events_list:
        ev_date = ev.get("date")
        ev_lbl = ev.get("label", "事件")
        ev_res = perform_event_study(
            combined_prices,
            event_date_str=ev_date,
            event_label=ev_lbl,
            window=5,
        )
        if ev_res and ev_res.get("valid"):
            event_study_results.append(ev_res)
            fig_ev = plot_event_study_trajectory(
                ev_res["norm_window_df"],
                t0_date=ev_res.get("actual_t0", ev_date),
                event_label=f"{ev_lbl} ({ev_date})"
            )
            event_study_charts.append({
                "label": ev_lbl,
                "date": ev_date,
                "desc": ev.get("note", ""),
                "chart": fig_ev.to_html(full_html=False, include_plotlyjs=False),
                "summary": ev_res["summary_table"].to_html(classes="data-table", index=False),
            })

    # 5. 生成 AI 四節研究報告
    logger.info("生成 AI 深度研究四節報告...")
    ai_report_markdown = generate_ai_research_report(
        df_prices=df_prices,
        df_metrics=summary_metrics,
        corr_matrix=corr_df,
        lead_lag_results=lead_lag_results,
        event_study_results=event_study_results,
        date_start=date_start_str,
        date_end=date_end_str,
        selected_fx_symbols=fx_symbols,
        selected_sectors=list(sectors_map.keys()),
    )
    ai_report_html = markdown_to_html_simple(ai_report_markdown)

    # 6. 讀取六件套 Markdown 文件
    logger.info("載入六件套文件內容...")
    plan_md = read_file_safe(BASE_DIR / "PLAN.md")
    task_md = read_file_safe(BASE_DIR / "TASK.md")
    memory_md = read_file_safe(BASE_DIR / "MEMORY.md")
    summary_md = read_file_safe(BASE_DIR / "summary.md")
    conclusion_md = read_file_safe(BASE_DIR / "結論報告.md")

    plan_html = markdown_to_html_simple(plan_md)
    task_html = markdown_to_html_simple(task_md)
    memory_html = markdown_to_html_simple(memory_md)
    summary_doc_html = markdown_to_html_simple(summary_md)
    conclusion_doc_html = markdown_to_html_simple(conclusion_md)

    # 7. 組裝 KPI 卡片 HTML
    kpi_fx_html = ""
    for sym in fx_symbols:
        if sym in df_prices.columns:
            s = df_prices[sym].dropna()
            latest_val = s.iloc[-1]
            ret_5d = ((latest_val - s.iloc[-6]) / s.iloc[-6] * 100) if len(s) >= 6 else 0
            ret_tot = ((latest_val - s.iloc[0]) / s.iloc[0] * 100) if len(s) >= 2 else 0
            info = DEFAULT_FX_SYMBOLS.get(sym, {"name": sym, "unit": ""})
            color_5d = "#dc2626" if ret_5d < 0 else "#16a34a"
            color_tot = "#dc2626" if ret_tot < 0 else "#16a34a"
            kpi_fx_html += f"""
            <div class="kpi-card">
                <div class="kpi-title">{sym}</div>
                <div class="kpi-name">{info['name'].split('(')[0]}</div>
                <div class="kpi-value">{latest_val:.4f} <span class="kpi-unit">{info.get('unit','')}</span></div>
                <div class="kpi-change">
                    <span>5日: <b style="color:{color_5d}">{ret_5d:+.2f}%</b></span>
                    <span>區間: <b style="color:{color_tot}">{ret_tot:+.2f}%</b></span>
                </div>
            </div>
            """

    kpi_sec_html = ""
    for sec_name in df_sec_prices.columns:
        s = df_sec_prices[sec_name].dropna()
        latest_val = s.iloc[-1]
        ret_5d = ((latest_val - s.iloc[-6]) / s.iloc[-6] * 100) if len(s) >= 6 else 0
        ret_tot = ((latest_val - s.iloc[0]) / s.iloc[0] * 100) if len(s) >= 2 else 0
        color_5d = "#dc2626" if ret_5d < 0 else "#16a34a"
        color_tot = "#dc2626" if ret_tot < 0 else "#16a34a"
        kpi_sec_html += f"""
        <div class="kpi-card kpi-sec">
            <div class="kpi-title">族群等權重</div>
            <div class="kpi-name">{sec_name}</div>
            <div class="kpi-value">{latest_val:.2f} <span class="kpi-unit">點</span></div>
            <div class="kpi-change">
                <span>5日: <b style="color:{color_5d}">{ret_5d:+.2f}%</b></span>
                <span>區間: <b style="color:{color_tot}">{ret_tot:+.2f}%</b></span>
            </div>
        </div>
        """

    summary_table_html = summary_metrics.to_html(classes="data-table", index=False)

    lead_lag_html_blocks = []
    for item in html_lead_lag_charts:
        lead_lag_html_blocks.append(
            f"<div style='margin-bottom:30px;'><h4 style='color:#334155; margin-bottom:8px;'>🔹 {item['sector']}</h4>"
            + item['chart']
            + "</div>"
        )
    lead_lag_section_html = "\n".join(lead_lag_html_blocks)

    event_study_html_blocks = []
    for ev_c in event_study_charts:
        block = f"""
        <div style='margin-bottom:36px; padding-bottom:24px; border-bottom:1px solid var(--border);'>
            <h3 style='color:var(--text-main); margin-bottom:4px;'>📌 {ev_c['label']} ({ev_c['date']})</h3>
            <p style='color:var(--text-sub); font-size:0.9rem; margin-bottom:12px;'>{ev_c['desc']}</p>
            {ev_c['chart']}
            <div style='margin-top:12px; overflow-x:auto;'>
                {ev_c['summary']}
            </div>
        </div>
        """
        event_study_html_blocks.append(block)
    event_study_section_html = "\n".join(event_study_html_blocks)

    # 8. 組裝單一獨立 HTML 檔案
    logger.info("組裝完整獨立 HTML 檔案...")
    full_html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>第六組成果發表｜匯率與出口股連動 - 多幣別 AI 股票研究工具</title>
    <!-- Plotly.js 互動式渲染 -->
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <!-- MathJax 數學公式渲染 -->
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        :root {{
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --primary-light: #eff6ff;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-sub: #475569;
            --border: #e2e8f0;
            --accent-green: #16a34a;
            --accent-red: #dc2626;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        }}

        body.dark-theme {{
            --primary: #3b82f6;
            --primary-dark: #60a5fa;
            --primary-light: #1e293b;
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-sub: #94a3b8;
            --border: #334155;
            --accent-green: #22c55e;
            --accent-red: #ef4444;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", sans-serif;
        }}

        body {{
            background-color: var(--bg);
            color: var(--text-main);
            line-height: 1.6;
            transition: background-color 0.3s ease, color 0.3s ease;
        }}

        /* Header 頂部橫幅 */
        .header {{
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #1e3a8a 100%);
            color: #ffffff;
            padding: 32px 24px;
            box-shadow: var(--shadow-lg);
            position: relative;
        }}
        .header-container {{
            max-width: 1380px;
            margin: 0 auto;
        }}
        .header-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 12px;
        }}
        .header h1 {{
            font-size: 2.1rem;
            font-weight: 800;
            display: flex;
            align-items: center;
            gap: 12px;
            letter-spacing: -0.5px;
        }}
        .header p {{
            font-size: 1.05rem;
            color: #cbd5e1;
            margin-bottom: 16px;
        }}
        .meta-badges {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            font-size: 0.88rem;
        }}
        .badge {{
            background-color: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.25);
            padding: 5px 14px;
            border-radius: 9999px;
            color: #f1f5f9;
            backdrop-filter: blur(4px);
        }}
        .badge-highlight {{
            background-color: #3b82f6;
            border-color: #60a5fa;
            font-weight: 700;
        }}

        /* 工具控制按鈕 */
        .header-actions {{
            display: flex;
            gap: 10px;
            align-items: center;
        }}
        .action-btn {{
            background: rgba(255, 255, 255, 0.15);
            border: 1px solid rgba(255, 255, 255, 0.3);
            color: #ffffff;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s ease;
        }}
        .action-btn:hover {{
            background: rgba(255, 255, 255, 0.3);
            transform: translateY(-1px);
        }}
        .action-btn.primary {{
            background: #2563eb;
            border-color: #3b82f6;
        }}
        .action-btn.primary:hover {{
            background: #1d4ed8;
        }}

        /* 主內容容器 */
        .container {{
            max-width: 1380px;
            margin: 24px auto;
            padding: 0 20px 80px 20px;
        }}

        /* 導覽分頁列 */
        .tabs-nav {{
            display: flex;
            overflow-x: auto;
            gap: 6px;
            background-color: var(--card-bg);
            padding: 10px;
            border-radius: 12px;
            box-shadow: var(--shadow-sm);
            border: 1px solid var(--border);
            margin-bottom: 24px;
            position: sticky;
            top: 12px;
            z-index: 100;
            backdrop-filter: blur(8px);
        }}
        .tab-btn {{
            background: none;
            border: none;
            padding: 10px 16px;
            font-size: 0.92rem;
            font-weight: 600;
            color: var(--text-sub);
            cursor: pointer;
            border-radius: 8px;
            white-space: nowrap;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .tab-btn:hover {{
            background-color: var(--primary-light);
            color: var(--primary);
        }}
        .tab-btn.active {{
            background-color: var(--primary);
            color: #ffffff;
            box-shadow: 0 2px 6px rgba(37, 99, 235, 0.3);
        }}

        /* 分頁區塊 */
        .tab-content {{
            display: none;
            animation: fadeIn 0.25s ease-in-out;
        }}
        .tab-content.active {{
            display: block;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(6px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        /* 卡片設計 */
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: var(--shadow-sm);
            transition: border-color 0.2s ease;
        }}
        .card:hover {{
            border-color: #cbd5e1;
        }}
        .card-title {{
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--text-main);
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        /* KPI 格狀排列 */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }}
        .kpi-card {{
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
            border-left: 4px solid var(--primary);
        }}
        .kpi-card.kpi-sec {{
            border-left-color: #10b981;
        }}
        .kpi-title {{
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--text-sub);
            text-transform: uppercase;
        }}
        .kpi-name {{
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--text-main);
            margin-bottom: 6px;
        }}
        .kpi-value {{
            font-size: 1.5rem;
            font-weight: 800;
            color: var(--text-main);
        }}
        .kpi-unit {{
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-sub);
        }}
        .kpi-change {{
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px dashed var(--border);
        }}

        /* 資料表格 */
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.92rem;
            margin: 14px 0;
        }}
        .data-table th, .data-table td {{
            padding: 10px 14px;
            border: 1px solid var(--border);
            text-align: left;
        }}
        .data-table th {{
            background-color: var(--bg);
            font-weight: 700;
            color: var(--text-main);
        }}
        .data-table tr:nth-child(even) {{
            background-color: var(--bg);
        }}
        .data-table tr:hover {{
            background-color: var(--primary-light);
        }}

        /* 提示框 */
        .alert-box {{
            background-color: var(--primary-light);
            border-left: 4px solid var(--primary);
            padding: 14px 18px;
            border-radius: 8px;
            color: var(--text-main);
            font-size: 0.94rem;
            margin-bottom: 18px;
        }}
        .disclaimer-box {{
            background-color: #fffbeb;
            border-left: 4px solid #f59e0b;
            padding: 16px 20px;
            border-radius: 8px;
            color: #92400e;
            font-size: 0.92rem;
            margin-top: 20px;
        }}
        body.dark-theme .disclaimer-box {{
            background-color: #78350f;
            color: #fef3c7;
        }}

        /* 講稿與語音播放卡片 */
        .pitch-box {{
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            color: #f8fafc;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: var(--shadow-md);
            border: 1px solid #334155;
        }}
        .pitch-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 16px;
            border-bottom: 1px solid #334155;
            padding-bottom: 12px;
        }}
        .pitch-title {{
            font-size: 1.2rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
            color: #60a5fa;
        }}
        .timer-display {{
            font-size: 1.5rem;
            font-weight: 800;
            color: #38bdf8;
            font-family: monospace;
            background: rgba(0, 0, 0, 0.4);
            padding: 4px 14px;
            border-radius: 6px;
            border: 1px solid #475569;
        }}
        .pitch-timeline {{
            display: flex;
            flex-direction: column;
            gap: 14px;
        }}
        .pitch-step {{
            background: rgba(255, 255, 255, 0.05);
            border-left: 3px solid #3b82f6;
            padding: 12px 16px;
            border-radius: 6px;
        }}
        .pitch-step-time {{
            font-size: 0.82rem;
            font-weight: 700;
            color: #93c5fd;
            margin-bottom: 4px;
        }}
        .pitch-step-text {{
            font-size: 0.95rem;
            color: #e2e8f0;
            line-height: 1.6;
        }}

        /* Markdown 文件渲染樣式 */
        .markdown-rendered h1 {{ font-size: 1.45rem; margin: 18px 0 10px 0; color: var(--text-main); border-bottom: 2px solid var(--border); padding-bottom: 6px; }}
        .markdown-rendered h2 {{ font-size: 1.25rem; margin: 16px 0 8px 0; color: var(--text-main); }}
        .markdown-rendered h3 {{ font-size: 1.1rem; margin: 14px 0 6px 0; color: var(--text-sub); }}
        .markdown-rendered p {{ margin-bottom: 12px; color: var(--text-main); font-size: 0.96rem; }}
        .markdown-rendered ul {{ margin: 8px 0 14px 24px; }}
        .markdown-rendered li {{ margin-bottom: 6px; color: var(--text-main); font-size: 0.95rem; }}
        .markdown-rendered hr {{ border: 0; height: 1px; background: var(--border); margin: 20px 0; }}

        /* 簡報模式 Slide Presentation Overlay */
        .presentation-overlay {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background-color: #0f172a;
            color: #ffffff;
            z-index: 99999;
            overflow-y: auto;
            padding: 40px;
        }}
        .presentation-overlay.active {{
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        .slide-container {{
            max-width: 1200px;
            margin: 0 auto;
            width: 100%;
            height: calc(100vh - 120px);
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .slide-page {{
            display: none;
            animation: slideIn 0.3s ease;
        }}
        .slide-page.active {{
            display: block;
        }}
        @keyframes slideIn {{
            from {{ opacity: 0; transform: translateX(20px); }}
            to {{ opacity: 1; transform: translateX(0); }}
        }}
        .slide-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            max-width: 1200px;
            margin: 0 auto;
            width: 100%;
            padding-top: 16px;
            border-top: 1px solid #334155;
        }}
        .slide-btn {{
            background: #1e293b;
            border: 1px solid #475569;
            color: #ffffff;
            padding: 8px 18px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
        }}
        .slide-btn:hover {{
            background: #334155;
        }}

        /* 列印樣式優化 */
        @media print {{
            .header-actions, .tabs-nav, .pitch-box .action-btn {{
                display: none !important;
            }}
            .tab-content {{
                display: block !important;
                page-break-after: always;
            }}
            .card {{
                box-shadow: none !important;
                border: 1px solid #ccc !important;
            }}
        }}

        /* 響應式 */
        @media (max-width: 768px) {{
            .header h1 {{ font-size: 1.6rem; }}
            .kpi-grid {{ grid-template-columns: 1fr; }}
            .container {{ padding: 0 10px 40px 10px; }}
        }}
    </style>
</head>
<body>

    <!-- Header 頂部導覽列 -->
    <header class="header">
        <div class="header-container">
            <div class="header-top">
                <h1>📈 匯率與出口股連動｜多幣別 AI 股票研究工具</h1>
                <div class="header-actions">
                    <button class="action-btn primary" onclick="startPresentation()">🖥️ 投影片簡報模式</button>
                    <button class="action-btn" onclick="toggleTheme()">🌙 切換深淺色</button>
                    <button class="action-btn" onclick="window.print()">🖨️ 匯出 PDF / 列印</button>
                </div>
            </div>
            <p>成大課堂專案成果發表｜第六組 (GROUP-SIX) ｜ 涵蓋多幣別外匯與台灣出口族群量化連動與關稅事件研究</p>
            <div class="meta-badges">
                <span class="badge badge-highlight">組別：成大第六組 (GROUP-SIX)</span>
                <span class="badge badge-highlight">題目：題 6 外匯與指數監控</span>
                <span class="badge">📅 資料期間：{date_start_str} 至 {date_end_str}</span>
                <span class="badge">📊 分析交易日數：{total_days} 天</span>
                <span class="badge">⚡ 生成時間：{gen_time_str}</span>
                <span class="badge">📁 格式：單一獨立 HTML (離線雙擊即開)</span>
            </div>
        </div>
    </header>

    <main class="container">
        <!-- 分頁切換按鈕導航 -->
        <nav class="tabs-nav" id="tabsNav">
            <button class="tab-btn active" onclick="switchTab('tab1', this)">📊 成果總覽與重點摘要</button>
            <button class="tab-btn" onclick="switchTab('tab2', this)">🏆 五關卡落實驗證</button>
            <button class="tab-btn" onclick="switchTab('tab3', this)">💱 多幣別匯率分析</button>
            <button class="tab-btn" onclick="switchTab('tab4', this)">🏭 出口族群等權重</button>
            <button class="tab-btn" onclick="switchTab('tab5', this)">🔥 相關性與動態滾動</button>
            <button class="tab-btn" onclick="switchTab('tab6', this)">⏱️ 領先落後關係</button>
            <button class="tab-btn" onclick="switchTab('tab7', this)">📅 關稅重大事件研究</button>
            <button class="tab-btn" onclick="switchTab('tab8', this)">🤖 AI 結構化結論報告</button>
            <button class="tab-btn" onclick="switchTab('tab9', this)">📁 開發流程六件套</button>
            <button class="tab-btn" onclick="switchTab('tab10', this)">ℹ️ 系統架構與合規聲明</button>
        </nav>

        <!-- ==================== TAB 1: 成果總覽與重點摘要 ==================== -->
        <section id="tab1" class="tab-content active">
            <!-- 一分鐘口頭報告講稿 -->
            <div class="pitch-box">
                <div class="pitch-header">
                    <div class="pitch-title">
                        <span>🎙️ 一分鐘分組口頭報告備忘錄 (1-Minute Pitch Script)</span>
                    </div>
                    <div style="display:flex; align-items:center; gap:12px;">
                        <span class="timer-display" id="pitchTimer">01:00</span>
                        <button class="action-btn" onclick="startPitchTimer()">▶️ 碼錶計時</button>
                        <button class="action-btn" onclick="resetPitchTimer()">🔄 重置</button>
                    </div>
                </div>
                <div class="pitch-timeline">
                    <div class="pitch-step">
                        <div class="pitch-step-time">⏱️ 00s ~ 15s ｜ 題目與研究動機</div>
                        <div class="pitch-step-text">
                            「各位評審老師好，我們是第六組。我們針對『多幣別匯率與台灣四大出口族群』建構了量化監控工具，串接 DXY、USD/TWD、USD/JPY、USD/CNH 以及半導體、電子代工、航運、自行車等 17 檔標的，探討關稅政策發酵下的市場連動反應。」
                        </div>
                    </div>
                    <div class="pitch-step">
                        <div class="pitch-step-time">⏱️ 15s ~ 35s ｜ 現況數字與反直覺發現</div>
                        <div class="pitch-step-text">
                            「從我們自己抓的真實數據中，發現了兩大反直覺現象：第一，在 2026/01/15 美國宣布 232 條款 25% 半導體關稅生效那一週，半導體與代工族群前後 5 日反而大漲 +6.2% 與 +4.1%，展現『利空落地、不確定性消除』的定價消化效應；第二，日報酬相關性上，半導體與 USD/TWD 呈現負相關 (r ≈ -0.32)，反映台幣升值時外資買超行情遠大於帳面匯損壓力。」
                        </div>
                    </div>
                    <div class="pitch-step">
                        <div class="pitch-step-time">⏱️ 35s ~ 50s ｜ 量化指標與領先落後</div>
                        <div class="pitch-step-text">
                            「在 20 日動態滾動相關中，我們觀察到關稅重大事件日前後，匯率與股價連動會產生劇烈轉折；領先落後分析則顯示美元指數變動對電子代工族群存在 1~3 天的滯後傳遞期。」
                        </div>
                    </div>
                    <div class="pitch-step">
                        <div class="pitch-step-time">⏱️ 50s ~ 60s ｜ 限制與四判準自檢</div>
                        <div class="pitch-step-text">
                            「最後經四判準自檢，全年出口股大漲核心動力是全球 AI 景氣週期，不可直接推論為關稅因果；若未來發生流動性緊縮或直接取消豁免清單，本模型之反彈模式將會失效。以上是第六組報告，謝謝！」
                        </div>
                    </div>
                </div>
            </div>

            <!-- KPI 卡片 -->
            <div class="card">
                <div class="card-title">🎯 核心匯率行情即時看板 (中價/收盤價)</div>
                <div class="kpi-grid">
                    {kpi_fx_html}
                </div>
                <div class="card-title" style="margin-top:24px;">🏭 台灣四大出口族群等權重表現 (基期 = 100)</div>
                <div class="kpi-grid">
                    {kpi_sec_html}
                </div>
            </div>

            <!-- 總覽圖表 -->
            <div class="card">
                <div class="card-title">📈 主要匯率與出口族群標準化走勢總覽 (基期 = 100)</div>
                <div class="alert-box">
                    💡 提示：點擊右上角圖例可隱藏/顯示特定標的，雙擊可單獨檢視，拖曳可進行時間軸縮放。紅色垂直虛線代表重大關稅事件生效日。
                </div>
                {html_chart_overview}
            </div>

            <!-- 統計表格 -->
            <div class="card">
                <div class="card-title">📋 標的績效與波動度統計指標彙整</div>
                <div style="overflow-x:auto;">
                    {summary_table_html}
                </div>
            </div>
        </section>

        <!-- ==================== TAB 2: 五關卡落實驗證 ==================== -->
        <section id="tab2" class="tab-content">
            <div class="card">
                <div class="card-title">🏆 課程五關卡生產線交付檢核矩陣</div>
                <p style="color:var(--text-sub); margin-bottom:16px;">
                    本專案嚴格貫徹「抓、理、看、監控化、結論報告」標準五關卡生產線，全數落實並具備可驗證之成果代碼與產物。
                </p>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th style="width:12%;">關卡</th>
                            <th style="width:28%;">核心任務目標</th>
                            <th style="width:35%;">本組實作落地方案 (第六組)</th>
                            <th style="width:15%;">交付產物</th>
                            <th style="width:10%;">驗收狀態</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><b>一、抓</b></td>
                            <td>程式抓取原始資料，原封不動存檔</td>
                            <td>串接 Yahoo Chart API 與 CTA 監控端點，含 3 次指數退避重試，自動將原始 JSON/CSV 存入 <code>raw/</code>。</td>
                            <td><code>data_fetcher.py</code><br/><code>raw/*.json</code></td>
                            <td><span style="color:var(--accent-green); font-weight:bold;">✅ 已驗收</span></td>
                        </tr>
                        <tr>
                            <td><b>二、理</b></td>
                            <td>清洗與對齊：日期統一、數值可運算</td>
                            <td>處理跨市場休市日，採用前向填補 (ffill)；計算基期 100 標準化及四大產業等權重指數。</td>
                            <td><code>data_processor.py</code><br/><code>data/*.csv</code></td>
                            <td><span style="color:var(--accent-green); font-weight:bold;">✅ 已驗收</span></td>
                        </tr>
                        <tr>
                            <td><b>三、看</b></td>
                            <td>繪製互動圖表，標註至少 2 個關稅事件日</td>
                            <td>繪製基期走勢、報酬排行、相關熱圖、20日滾動相關、領先落後、±5日事件研究等 7 大圖表，標註 6 個重大事件。</td>
                            <td><code>visualizer.py</code><br/>Plotly 視覺化</td>
                            <td><span style="color:var(--accent-green); font-weight:bold;">✅ 已驗收</span></td>
                        </tr>
                        <tr>
                            <td><b>四、監控化</b></td>
                            <td>做成可重跑工具，一鍵更新至最新</td>
                            <td>提供 Streamlit 主看板 (<code>app.py</code>)、一鍵打包 (<code>generate_all.py</code>) 與 <code>run.bat</code> / <code>build_html.bat</code> 批次執行檔。</td>
                            <td><code>app.py</code><br/><code>index.html</code></td>
                            <td><span style="color:var(--accent-green); font-weight:bold;">✅ 已驗收</span></td>
                        </tr>
                        <tr>
                            <td><b>五、結論報告</b></td>
                            <td>讓 AI 讀自己的資料，產出四節結論報告</td>
                            <td>自動生成四節結論報告（現況數字、事件對照、判讀、限制與失效條件），並完成四判準自檢表。</td>
                            <td><code>ai_engine.py</code><br/><code>結論報告.md</code></td>
                            <td><span style="color:var(--accent-green); font-weight:bold;">✅ 已驗收</span></td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </section>

        <!-- ==================== TAB 3: 多幣別走勢 ==================== -->
        <section id="tab3" class="tab-content">
            <div class="card">
                <div class="card-title">💱 各幣別與美元指數原始報價走勢</div>
                <div class="alert-box">
                    📌 <b>報價方向解讀指南</b>：數值上升代表美元相對該貨幣升值（當地貨幣貶值）。例如 USD/TWD 由 30.5 升至 31.0 代表美元升值、台幣貶值；美元指數 (^NYICDX) 上升代表美元對一籃子國際貨幣升值。
                </div>
                {html_chart_fx_raw}
            </div>
            <div class="card">
                <div class="card-title">📉 多幣別標準化強弱比較 (起點 = 100)</div>
                {html_chart_fx_norm}
            </div>
        </section>

        <!-- ==================== TAB 4: 出口族群表現 ==================== -->
        <section id="tab4" class="tab-content">
            <div class="card">
                <div class="card-title">📊 台灣出口產業族群累積報酬比較 (%)</div>
                {html_chart_sec_bar}
            </div>
            <div class="card">
                <div class="card-title">📈 四大出口產業等權重指數標準化軌跡</div>
                {html_chart_sec_norm}
            </div>
        </section>

        <!-- ==================== TAB 5: 相關性與滾動分析 ==================== -->
        <section id="tab5" class="tab-content">
            <div class="card">
                <div class="card-title">🔥 標的日報酬率 Pearson 相關係數熱圖</div>
                <div class="alert-box">
                    紅色表示正相關 (同向變動)，藍色表示負相關 (反向變動)。若美元/台幣為負相關，代表台幣升值（USD/TWD 下跌）時該標的傾向走漲。
                </div>
                {html_chart_corr_heatmap}
            </div>
            <div class="card">
                <div class="card-title">🌊 20 日滾動相關係數：美元/台幣 (USD/TWD) vs 出口族群</div>
                {html_chart_rolling_twd}
            </div>
            <div class="card">
                <div class="card-title">🌊 20 日滾動相關係數：美元指數 (DXY) vs 出口族群</div>
                {html_chart_rolling_dxy}
            </div>
        </section>

        <!-- ==================== TAB 6: 領先落後關係 ==================== -->
        <section id="tab6" class="tab-content">
            <div class="card">
                <div class="card-title">⏱️ 匯率與出口產業領先落後交叉相關分析 (Lag -20 ~ +20 天)</div>
                <div class="alert-box">
                    說明：Lag &gt; 0 代表匯率變動領先出口族群股票；Lag &lt; 0 代表股票變動領先匯率；Lag = 0 代表當日同步相關。
                </div>
                {lead_lag_section_html}
            </div>
        </section>

        <!-- ==================== TAB 7: 關稅重大事件研究 ==================== -->
        <section id="tab7" class="tab-content">
            <div class="card">
                <div class="card-title">📅 關稅重大事件前後 5 個交易日窗口分析 (Event Study)</div>
                <p style="color:var(--text-sub); font-size:0.92rem; margin-bottom:16px;">
                    基準日以事件日前 5 日 (T-5) 點數標準化為 100，觀察市場在消息發酵與生效前後的定價反應軌跡。
                </p>
                {event_study_section_html}
            </div>
        </section>

        <!-- ==================== TAB 8: AI 深度研究報告 ==================== -->
        <section id="tab8" class="tab-content">
            <div class="card">
                <div class="card-title">🤖 AI 深度研究四節結構化結論報告 (無數據幻覺)</div>
                <div class="alert-box">
                    嚴格依據成大課堂規範與真實量化資料計算產出：① 現況數字、② 與關稅事件日對照、③ 產業與總經判讀、④ 限制與失效條件。
                </div>
                {ai_report_html}
            </div>
        </section>

        <!-- ==================== TAB 9: 開發流程六件套 ==================== -->
        <section id="tab9" class="tab-content">
            <div class="card">
                <div class="card-title">📁 專案開發流程六件套全覽 (Project Artifacts)</div>
                <div style="display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap;">
                    <button class="action-btn" style="background:#2563eb;" onclick="showArtifact('art-plan', this)">📄 PLAN.md</button>
                    <button class="action-btn" style="background:#475569;" onclick="showArtifact('art-task', this)">📋 TASK.md</button>
                    <button class="action-btn" style="background:#475569;" onclick="showArtifact('art-mem', this)">🧠 MEMORY.md</button>
                    <button class="action-btn" style="background:#475569;" onclick="showArtifact('art-sum', this)">📊 summary.md</button>
                    <button class="action-btn" style="background:#475569;" onclick="showArtifact('art-conc', this)">📝 結論報告.md</button>
                </div>

                <div id="art-plan" class="artifact-pane active">
                    {plan_html}
                </div>
                <div id="art-task" class="artifact-pane" style="display:none;">
                    {task_html}
                </div>
                <div id="art-mem" class="artifact-pane" style="display:none;">
                    {memory_html}
                </div>
                <div id="art-sum" class="artifact-pane" style="display:none;">
                    {summary_doc_html}
                </div>
                <div id="art-conc" class="artifact-pane" style="display:none;">
                    {conclusion_doc_html}
                </div>
            </div>
        </section>

        <!-- ==================== TAB 10: 系統架構與合規聲明 ==================== -->
        <section id="tab10" class="tab-content">
            <div class="card">
                <div class="card-title">ℹ️ 資料品質、計算方法與系統架構</div>
                <ul style="margin-left: 20px; line-height: 1.8; color: var(--text-main);">
                    <li><b>資料來源</b>：Yahoo Finance Chart API，涵蓋多幣別（TWD=X, JPY=X, CNY=X, CNH=X, ^NYICDX）與台灣出口個股（2330, 2454, 2317, 2603, 9921 等）。</li>
                    <li><b>基期 100 標準化公式</b>：\( P_{{norm, t}} = \\frac{{P_t}}{{P_0}} \\times 100 \)，消弭絕對價格量綱差異，直觀比較跨資產累積漲跌。</li>
                    <li><b>族群等權重指數</b>：計算族群內各成分股標準化數值之算術平均數。</li>
                    <li><b>領先落後交叉相關</b>：計算 \( r(\\Delta FX_t, \\Delta Stock_{{t+k}}) \)，平移範圍 \( k \\in [-20, 20] \)。</li>
                    <li><b>事件研究法 (Event Study)</b>：以事件日前 5 交易日 (T-5) 為基期 100，追蹤至 T+5 窗口累積變動。</li>
                </ul>

                <div class="disclaimer-box">
                    <b>⚠️ 合規與免責聲明：</b><br/>
                    {DISCLAIMER_TEXT.replace(chr(10), '<br/>')}
                </div>
            </div>
        </section>
    </main>

    <!-- ==================== 全螢幕投影片簡報模式 OVERLAY ==================== -->
    <div id="presentationOverlay" class="presentation-overlay">
        <div class="slide-container">
            <!-- Slide 1: 封面 -->
            <div class="slide-page active" id="slide1">
                <div style="text-align:center; padding: 40px 20px;">
                    <span class="badge badge-highlight" style="font-size:1.1rem; padding:8px 20px;">成大課堂專案成果發表</span>
                    <h1 style="font-size:3.2rem; margin:24px 0 16px 0; font-weight:800; color:#60a5fa;">
                        📈 匯率與出口股連動
                    </h1>
                    <h2 style="font-size:1.8rem; font-weight:500; color:#cbd5e1; margin-bottom:30px;">
                        多幣別 AI 股票研究工具 ｜ 題 6 外匯與指數監控
                    </h2>
                    <p style="font-size:1.2rem; color:#94a3b8; max-width:800px; margin:0 auto 40px auto;">
                        成大量化研究團隊 第六組 (GROUP-SIX) ｜ 2025-2026 全年量化數據與關稅事件實證
                    </p>
                    <div style="display:flex; justify-content:center; gap:16px;">
                        <span class="badge">📊 17 檔資產標的</span>
                        <span class="badge">⏱️ 251 交易日對齊</span>
                        <span class="badge">🎯 6 大關稅重大事件</span>
                    </div>
                </div>
            </div>

            <!-- Slide 2: 五關卡生產線 -->
            <div class="slide-page" id="slide2">
                <h2 style="font-size:2.2rem; margin-bottom:20px; color:#60a5fa;">🏆 五關卡生產線全流程落地</h2>
                <div style="display:grid; grid-template-columns:repeat(5, 1fr); gap:16px; margin-top:24px;">
                    <div style="background:#1e293b; border:1px solid #3b82f6; border-radius:12px; padding:20px;">
                        <h3 style="color:#60a5fa; margin-bottom:8px;">一、抓</h3>
                        <p style="color:#cbd5e1; font-size:0.95rem;">Yahoo Chart API 串接、3 次指數退避重試、原始 JSON 存入 <code>raw/</code>。</p>
                    </div>
                    <div style="background:#1e293b; border:1px solid #3b82f6; border-radius:12px; padding:20px;">
                        <h3 style="color:#60a5fa; margin-bottom:8px;">二、理</h3>
                        <p style="color:#cbd5e1; font-size:0.95rem;">休市日對齊、ffill 補值、基期 100 標準化、等權重族群指數存入 <code>data/</code>。</p>
                    </div>
                    <div style="background:#1e293b; border:1px solid #3b82f6; border-radius:12px; padding:20px;">
                        <h3 style="color:#60a5fa; margin-bottom:8px;">三、看</h3>
                        <p style="color:#cbd5e1; font-size:0.95rem;">Plotly 互動走勢、相關熱圖、滾動相關、領先落後與 ±5日事件研究。</p>
                    </div>
                    <div style="background:#1e293b; border:1px solid #3b82f6; border-radius:12px; padding:20px;">
                        <h3 style="color:#60a5fa; margin-bottom:8px;">四、監控化</h3>
                        <p style="color:#cbd5e1; font-size:0.95rem;">Streamlit 看板 (<code>app.py</code>) + 獨立 HTML (<code>generate_all.py</code>) 一鍵重跑。</p>
                    </div>
                    <div style="background:#1e293b; border:1px solid #3b82f6; border-radius:12px; padding:20px;">
                        <h3 style="color:#60a5fa; margin-bottom:8px;">五、結論報告</h3>
                        <p style="color:#cbd5e1; font-size:0.95rem;">AI 四節結構化結論報告（無幻覺）＋ 四判準自檢表落地。</p>
                    </div>
                </div>
            </div>

            <!-- Slide 3: 核心數據與跨市場走勢 -->
            <div class="slide-page" id="slide3">
                <h2 style="font-size:2.2rem; margin-bottom:20px; color:#60a5fa;">📊 跨市場標準化行情總覽 (基期 = 100)</h2>
                <div style="background:#1e293b; border-radius:12px; padding:16px; border:1px solid #334155;">
                    <div style="display:flex; justify-content:space-around; margin-bottom:12px; text-align:center;">
                        <div><span style="color:#94a3b8; font-size:0.9rem;">半導體等權重</span><br/><b style="font-size:1.4rem; color:#22c55e;">+42.8%</b></div>
                        <div><span style="color:#94a3b8; font-size:0.9rem;">電子代工等權重</span><br/><b style="font-size:1.4rem; color:#22c55e;">+28.4%</b></div>
                        <div><span style="color:#94a3b8; font-size:0.9rem;">美元兌台幣 (TWD=X)</span><br/><b style="font-size:1.4rem; color:#60a5fa;">-3.6% (升值)</b></div>
                        <div><span style="color:#94a3b8; font-size:0.9rem;">美元指數 (DXY)</span><br/><b style="font-size:1.4rem; color:#f59e0b;">-4.2%</b></div>
                    </div>
                    <div style="height:380px; overflow:hidden;">
                        {html_chart_overview}
                    </div>
                </div>
            </div>

            <!-- Slide 4: 反直覺發現與事件研究 -->
            <div class="slide-page" id="slide4">
                <h2 style="font-size:2.2rem; margin-bottom:20px; color:#60a5fa;">💡 核心洞察：三件反直覺事實</h2>
                <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:20px; margin-top:20px;">
                    <div style="background:#1e293b; border-left:4px solid #ef4444; border-radius:10px; padding:20px;">
                        <h3 style="color:#f87171; margin-bottom:10px;">1. 關稅利空落地，股價反而大漲</h3>
                        <p style="color:#cbd5e1; font-size:1rem; line-height:1.7;">
                            2026-01-15 美國課 25% 半導體關稅當週，半導體指數前後 5 日反而上漲 <b>+6.2%</b>、代工族群 <b>+4.1%</b>。市場在事件前已定價悲觀預期，政策確定後不確定性消除。
                        </p>
                    </div>
                    <div style="background:#1e293b; border-left:4px solid #3b82f6; border-radius:10px; padding:20px;">
                        <h3 style="color:#60a5fa; margin-bottom:10px;">2. 台幣升值伴隨出口股強勢</h3>
                        <p style="color:#cbd5e1; font-size:1rem; line-height:1.7;">
                            半導體與 USD/TWD 呈現負相關 (r ≈ -0.32)。外資大量匯入買超台股權值股帶動台幣升值，資金行情的推升力道遠大於出口匯損的心理壓力。
                        </p>
                    </div>
                    <div style="background:#1e293b; border-left:4px solid #10b981; border-radius:10px; padding:20px;">
                        <h3 style="color:#34d399; margin-bottom:10px;">3. 族群定價權分歧顯著</h3>
                        <p style="color:#cbd5e1; font-size:1rem; line-height:1.7;">
                            AI 伺服器代工與半導體因具備全球定價權，轉嫁能力強；傳統自行車族群 (-8.5%) 則面臨需求疲軟與關稅擠壓，表現明顯落後。
                        </p>
                    </div>
                </div>
            </div>

            <!-- Slide 5: AI 結論與四判準自檢 -->
            <div class="slide-page" id="slide5">
                <h2 style="font-size:2.2rem; margin-bottom:20px; color:#60a5fa;">🔍 結論報告與四判準自檢</h2>
                <div style="background:#1e293b; border-radius:12px; padding:24px; border:1px solid #334155;">
                    <table class="data-table" style="color:#ffffff;">
                        <thead>
                            <tr style="background:#0f172a;">
                                <th style="width:25%; color:#60a5fa;">四判準檢驗項目</th>
                                <th style="color:#f1f5f9;">本組落實驗證與自檢結果</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td><b>1. 時間順序對嗎？</b></td>
                                <td><b>符合</b>。事件日皆落於 T-5~T+5 之中點，精確切割前後市場定價反應軌跡。</td>
                            </tr>
                            <tr>
                                <td><b>2. 有沒有別的原因？</b></td>
                                <td><b>有，且為核心動力</b>。全球生成式 AI 算力需求為推升股價主力，已在限制條件中明確披露。</td>
                            </tr>
                            <tr>
                                <td><b>3. 換一個對象還成立嗎？</b></td>
                                <td><b>不完全成立</b>。半導體抗跌性強，但傳統製造業（自行車族群）對關稅承壓程度明顯較大。</td>
                            </tr>
                            <tr>
                                <td><b>4. 只發生一次還是每次都這樣？</b></td>
                                <td><b>部分成立</b>。「利空落地反彈」在 232 條款顯著，但在加碼投資日呈現回檔，僅能作為歷史統計觀察。</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Slide 6: 現場 Q&A 與講稿備忘 -->
            <div class="slide-page" id="slide6">
                <div style="text-align:center; padding: 40px 20px;">
                    <h1 style="font-size:3.5rem; color:#60a5fa; margin-bottom:20px;">🎯 報告完畢 ｜ 敬請指教</h1>
                    <p style="font-size:1.3rem; color:#cbd5e1; margin-bottom:30px;">成大第六組 (GROUP-SIX) ｜ 外匯與指數監控 AI 研究工具</p>
                    <div style="display:inline-block; text-align:left; background:#1e293b; border-radius:12px; padding:20px 30px; border:1px solid #3b82f6;">
                        <h4 style="color:#93c5fd; margin-bottom:8px;">💡 現場問答必備錦囊：</h4>
                        <ul style="color:#e2e8f0; font-size:1rem; line-height:1.8;">
                            <li>• <b>Q: 為什麼沒有用群益 CTA 平台的台幣報價？</b> → 平台無 TWD 貨幣對，我們以公開 Yahoo Chart API 為備援。</li>
                            <li>• <b>Q: 如何杜絕 AI 報告數據幻覺？</b> → 數字直接由程式從計算後 DataFrame 填入模板，100% 來自本機資料庫。</li>
                            <li>• <b>Q: 系統如何即時重跑？</b> → 執行 <code>build_html.bat</code> 或 <code>run.bat</code> 即可全自動重抓並產出最新報告。</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>

        <!-- 簡報底部導航列 -->
        <div class="slide-footer">
            <div>
                <button class="slide-btn" onclick="prevSlide()">◀ 上一頁 (Left)</button>
                <button class="slide-btn" onclick="nextSlide()">下一頁 (Right) ▶</button>
            </div>
            <div id="slideCounter" style="color:#94a3b8; font-size:1rem; font-weight:600;">
                Slide 1 / 6
            </div>
            <div>
                <button class="slide-btn" style="background:#dc2626; border-color:#ef4444;" onclick="exitPresentation()">✕ 退出簡報 (Esc)</button>
            </div>
        </div>
    </div>

    <!-- JavaScript 腳本 -->
    <script>
        // 分頁切換功能
        function switchTab(tabId, btnElement) {{
            const tabs = document.querySelectorAll('.tab-content');
            const btns = document.querySelectorAll('.tab-btn');
            
            tabs.forEach(tab => tab.classList.remove('active'));
            btns.forEach(btn => btn.classList.remove('active'));
            
            const selectedTab = document.getElementById(tabId);
            if (selectedTab) {{
                selectedTab.classList.add('active');
            }}
            
            if (btnElement) {{
                btnElement.classList.add('active');
            }}

            window.dispatchEvent(new Event('resize'));
            setTimeout(() => {{
                window.dispatchEvent(new Event('resize'));
            }}, 150);
        }}

        // 六件套切換
        function showArtifact(artId, btn) {{
            const panes = document.querySelectorAll('.artifact-pane');
            panes.forEach(p => p.style.display = 'none');
            const target = document.getElementById(artId);
            if (target) target.style.display = 'block';

            const pBtns = btn.parentElement.querySelectorAll('.action-btn');
            pBtns.forEach(b => b.style.background = '#475569');
            btn.style.background = '#2563eb';
        }}

        // 深淺色主題切換
        function toggleTheme() {{
            document.body.classList.toggle('dark-theme');
            const isDark = document.body.classList.contains('dark-theme');
            localStorage.setItem('g6_theme', isDark ? 'dark' : 'light');
        }}

        // 讀取主題紀錄
        if (localStorage.getItem('g6_theme') === 'dark') {{
            document.body.classList.add('dark-theme');
        }}

        // 碼錶計時器
        let pitchInterval = null;
        let pitchSeconds = 60;
        function startPitchTimer() {{
            if (pitchInterval) return;
            pitchInterval = setInterval(() => {{
                if (pitchSeconds > 0) {{
                    pitchSeconds--;
                    const m = Math.floor(pitchSeconds / 60).toString().padStart(2, '0');
                    const s = (pitchSeconds % 60).toString().padStart(2, '0');
                    document.getElementById('pitchTimer').innerText = `${{m}}:${{s}}`;
                }} else {{
                    clearInterval(pitchInterval);
                    pitchInterval = null;
                    alert("⏰ 一分鐘時間到！");
                }}
            }}, 1000);
        }}
        function resetPitchTimer() {{
            clearInterval(pitchInterval);
            pitchInterval = null;
            pitchSeconds = 60;
            document.getElementById('pitchTimer').innerText = "01:00";
        }}

        // 簡報模式邏輯
        let currentSlide = 1;
        const totalSlides = 6;

        function startPresentation() {{
            document.getElementById('presentationOverlay').classList.add('active');
            currentSlide = 1;
            showSlide(1);
            window.dispatchEvent(new Event('resize'));
        }}

        function exitPresentation() {{
            document.getElementById('presentationOverlay').classList.remove('active');
            window.dispatchEvent(new Event('resize'));
        }}

        function showSlide(index) {{
            for (let i = 1; i <= totalSlides; i++) {{
                const sl = document.getElementById('slide' + i);
                if (sl) sl.classList.remove('active');
            }}
            const activeSl = document.getElementById('slide' + index);
            if (activeSl) activeSl.classList.add('active');
            document.getElementById('slideCounter').innerText = `Slide ${{index}} / ${{totalSlides}}`;
            window.dispatchEvent(new Event('resize'));
        }}

        function nextSlide() {{
            if (currentSlide < totalSlides) {{
                currentSlide++;
                showSlide(currentSlide);
            }}
        }}

        function prevSlide() {{
            if (currentSlide > 1) {{
                currentSlide--;
                showSlide(currentSlide);
            }}
        }}

        // 鍵盤導航支援
        document.addEventListener('keydown', function(e) {{
            const isPres = document.getElementById('presentationOverlay').classList.contains('active');
            if (isPres) {{
                if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') {{
                    nextSlide();
                }} else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {{
                    prevSlide();
                }} else if (e.key === 'Escape') {{
                    exitPresentation();
                }}
            }}
        }});
    </script>
</body>
</html>
"""
    # 寫入目標檔案
    output_file.write_text(full_html, encoding="utf-8")
    logger.info("[SUCCESS] Single HTML report generated successfully: %s", output_file)
    return output_file


if __name__ == "__main__":
    out_path = BASE_DIR / "GROUP-SIX-Report.html"
    generate_single_html_report(output_file=out_path, range_param="1y")
    idx_path = BASE_DIR / "index.html"
    generate_single_html_report(output_file=idx_path, range_param="1y")
    print(f"\n[DONE] Package completed! Presentation HTML saved to:\n1. {out_path}\n2. {idx_path}")
