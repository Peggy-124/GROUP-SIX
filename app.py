# -*- coding: utf-8 -*-
"""
「匯率與出口股連動｜多幣別」AI 股票研究工具
Streamlit 主應用程式
"""
import copy
import io
import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from config import (
    BASE_DIR,
    CACHE_DIR,
    DATA_DIR,
    DEFAULT_EVENTS,
    DEFAULT_EXPORT_SECTORS,
    DEFAULT_FX_SYMBOLS,
    DISCLAIMER_TEXT,
    LEAD_LAG_DAYS,
    PERIOD_MAP,
    RAW_DIR,
)
from data_fetcher import fetch_all_data, fetch_yahoo_chart, normalize_stock_symbol
from data_processor import (
    build_aligned_price_dataframe,
    build_sector_indices,
    compute_correlation_matrix,
    compute_lead_lag_correlations,
    compute_metrics_summary,
    compute_rolling_correlation,
    filter_by_period,
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Streamlit 頁面基礎設定 ---
st.set_page_config(
    page_title="匯率與出口股連動｜多幣別 AI 股票研究工具",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自訂 CSS 美化
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 10px;
    }
    .direction-alert {
        background-color: #EFF6FF;
        border-left: 4px solid #3B82F6;
        padding: 10px 14px;
        border-radius: 4px;
        color: #1E40AF;
        font-size: 0.92rem;
        margin-bottom: 15px;
    }
    .disclaimer-box {
        background-color: #FFFBEB;
        border-left: 4px solid #F59E0B;
        padding: 12px 16px;
        border-radius: 4px;
        color: #92400E;
        font-size: 0.9rem;
        margin-top: 25px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- 初始化 Session State ---
if "sectors_config" not in st.session_state:
    st.session_state.sectors_config = copy.deepcopy(DEFAULT_EXPORT_SECTORS)

if "events_list" not in st.session_state:
    # 嘗試從 events.csv 載入或使用預設
    events_csv_path = BASE_DIR / "events.csv"
    if events_csv_path.exists():
        try:
            ev_df = pd.read_csv(events_csv_path)
            st.session_state.events_list = ev_df.to_dict(orient="records")
        except Exception:
            st.session_state.events_list = copy.deepcopy(DEFAULT_EVENTS)
    else:
        st.session_state.events_list = copy.deepcopy(DEFAULT_EVENTS)


# --- 側邊欄：控制面板 ---
st.sidebar.title("⚙️ 研究參數設定")

# 1. 期間選擇
period_option = st.sidebar.selectbox(
    "📅 分析期間",
    options=["1 個月", "3 個月", "6 個月", "1 年", "2 年", "自訂日期"],
    index=3,
)

start_date_val = None
end_date_val = None
if period_option == "自訂日期":
    col_d1, col_d2 = st.sidebar.columns(2)
    start_date_val = col_d1.date_input("開始日期", value=date.today() - timedelta(days=365))
    end_date_val = col_d2.date_input("結束日期", value=date.today())

# 2. 匯率與指數勾選
st.sidebar.subheader("💱 匯率與指數標的")
available_fx = list(DEFAULT_FX_SYMBOLS.keys())
selected_fx = st.sidebar.multiselect(
    "選擇要分析的幣別/指數",
    options=available_fx,
    default=["^NYICDX", "TWD=X", "JPY=X", "CNY=X"],
    format_func=lambda x: f"{x} ({DEFAULT_FX_SYMBOLS[x]['name']})",
)

# 3. 報價方向解讀提醒
st.sidebar.markdown(
    """
    <div class="direction-alert">
    💡 <b>報價方向提醒</b><br>
    本工具採用 <code>USD/XXX</code> 標價：<br>
    • <b>數值上升</b> ➔ 美元升值、當地貨幣貶值<br>
    • <b>數值下降</b> ➔ 美元貶值、當地貨幣升值
    </div>
    """,
    unsafe_allow_html=True,
)

# 4. 族群與股票管理
with st.sidebar.expander("🛠️ 管理出口族群與成分股", expanded=False):
    sector_names = list(st.session_state.sectors_config.keys())
    selected_sec_for_edit = st.selectbox("選擇要編輯的族群", options=sector_names)

    if selected_sec_for_edit:
        st.caption(f"族群說明：{st.session_state.sectors_config[selected_sec_for_edit]['description']}")
        curr_stocks = st.session_state.sectors_config[selected_sec_for_edit]["stocks"]
        st.write("目前成分股：", ", ".join([f"{k} ({v})" for k, v in curr_stocks.items()]))

        # 新增股票
        col_s1, col_s2 = st.columns(2)
        new_stk_code = col_s1.text_input("股票代號 (例 2308 或 2308.TW)", key="new_stk_c")
        new_stk_name = col_s2.text_input("股票名稱 (例 台達電)", key="new_stk_n")
        if st.button("➕ 新增個股到此族群", use_container_width=True):
            if new_stk_code and new_stk_name:
                norm_c = normalize_stock_symbol(new_stk_code)
                st.session_state.sectors_config[selected_sec_for_edit]["stocks"][norm_c] = new_stk_name
                st.success(f"已新增 {norm_c} ({new_stk_name})")
                st.rerun()

        # 刪除股票
        if curr_stocks:
            del_target = st.selectbox("選擇要移除的個股", options=list(curr_stocks.keys()), format_func=lambda x: f"{x} ({curr_stocks[x]})")
            if st.button("🗑️ 移除此個股", use_container_width=True):
                del st.session_state.sectors_config[selected_sec_for_edit]["stocks"][del_target]
                st.warning(f"已移除 {del_target}")
                st.rerun()

    # 新增自訂族群
    st.markdown("---")
    st.markdown("<b>新增自訂族群</b>", unsafe_allow_html=True)
    new_sec_name = st.text_input("自訂族群名稱 (例 網通/AI伺服器)", key="new_sec_n")
    new_sec_desc = st.text_input("族群簡介說明", key="new_sec_d")
    if st.button("➕ 建立新族群", use_container_width=True):
        if new_sec_name and new_sec_name not in st.session_state.sectors_config:
            st.session_state.sectors_config[new_sec_name] = {
                "description": new_sec_desc or "自訂出口族群",
                "stocks": {},
            }
            st.success(f"已建立族群「{new_sec_name}」")
            st.rerun()

# 5. 重大事件管理
with st.sidebar.expander("📅 管理關稅與重大事件日", expanded=False):
    st.write(f"目前共 {len(st.session_state.events_list)} 個事件標記：")
    for ev in st.session_state.events_list:
        st.caption(f"• `{ev['date']}`: {ev['label']} ({ev.get('category', '一般')})")

    new_ev_date = st.date_input("新增事件日期", value=date(2026, 1, 15), key="new_ev_d")
    new_ev_label = st.text_input("事件簡述", value="", placeholder="例：美對台課徵 20% 關稅", key="new_ev_l")
    new_ev_cat = st.text_input("事件分類", value="關稅政策", key="new_ev_c")
    if st.button("➕ 新增事件日", use_container_width=True):
        if new_ev_label:
            st.session_state.events_list.append({
                "date": new_ev_date.strftime("%Y-%m-%d"),
                "label": new_ev_label,
                "category": new_ev_cat,
                "note": "使用者手動新增事件",
            })
            st.success("已新增事件！")
            st.rerun()

    if st.button("🔄 重設為預設事件清單", use_container_width=True):
        st.session_state.events_list = copy.deepcopy(DEFAULT_EVENTS)
        st.rerun()

# 6. 強制重新整理資料按鈕
st.sidebar.markdown("---")
btn_refresh = st.sidebar.button("🔄 重新抓取最新資料", use_container_width=True, type="primary")


# --- 核心資料抓取與快取 ---
@st.cache_data(ttl=3600, show_spinner=False)
def load_market_data(
    fx_list: List[str],
    sectors_map: dict,
    range_param: str,
    force_ref: bool = False
):
    """載入市場資料並以 Streamlit cache 加速"""
    fx_data, stock_data, errors = fetch_all_data(
        fx_symbols=fx_list,
        sector_stocks_map=sectors_map,
        range_str=range_param,
        force_refresh=force_ref,
    )
    return fx_data, stock_data, errors


# 執行抓取
range_api_param = PERIOD_MAP.get(period_option, "2y")
if period_option == "自訂日期":
    range_api_param = "2y"

if btn_refresh:
    st.cache_data.clear()

with st.spinner("正在連線抓取各幣別匯率、美元指數與台股出口族群歷史報價..."):
    fx_dict, stock_dict, fetch_errors = load_market_data(
        fx_list=selected_fx,
        sectors_map=st.session_state.sectors_config,
        range_param=range_api_param,
        force_ref=btn_refresh,
    )

if fetch_errors:
    with st.expander("⚠️ 部分標的載入警告 (已啟動本機快取備援)", expanded=False):
        for err in fetch_errors:
            st.warning(err)


# --- 數據處理與指標計算 ---
df_aligned_all = build_aligned_price_dataframe(fx_dict, stock_dict)

if df_aligned_all.empty:
    st.error("❌ 無法取得足夠的行情數據，請確認網路連線或本機快取檔案！")
    st.stop()

# 期間過濾
df_prices = filter_by_period(
    df_aligned_all,
    period_str=period_option,
    start_date=start_date_val.strftime("%Y-%m-%d") if start_date_val else None,
    end_date=end_date_val.strftime("%Y-%m-%d") if end_date_val else None,
)

if df_prices.empty or len(df_prices) < 2:
    st.warning("⚠️ 所選日期區間資料筆數不足，自動擴大為全部可用資料。")
    df_prices = df_aligned_all.copy()

# 基期 100 標準化
df_norm_all = normalize_base100(df_prices)

# 族群等權重指數計算
df_sec_prices, df_sec_norm, df_sec_returns = build_sector_indices(
    df_prices, st.session_state.sectors_config
)

# 合併匯率與族群等權重指數為一個綜合 DataFrame
combined_prices = pd.concat([df_prices[selected_fx], df_sec_prices], axis=1).dropna(how="all").ffill()
combined_norm = normalize_base100(combined_prices)
combined_returns = combined_prices.pct_change().dropna(how="all")

# 績效摘要表
summary_metrics = compute_metrics_summary(combined_prices)

# 儲存處理後資料
save_processed_datasets(df_prices, df_sec_prices, combined_returns)

# 日期區間文字
date_start_str = df_prices.index.min().strftime("%Y-%m-%d")
date_end_str = df_prices.index.max().strftime("%Y-%m-%d")


# --- 主介面標題 ---
st.markdown('<div class="main-header">📈 匯率與出口股連動｜多幣別 AI 股票研究工具</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="sub-header">多幣別匯率（USD/TWD, USD/JPY, USD/CNY, DXY）與台灣出口產業族群連動分析與事件研究 ｜ 資料期間：<code>{date_start_str}</code> 至 <code>{date_end_str}</code>（共 {len(df_prices)} 個交易日）</div>',
    unsafe_allow_html=True,
)


# --- 導覽分頁 (Tabs) ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📊 總覽儀表板",
    "💱 多幣別與指數走勢",
    "🏭 出口族群與個股表現",
    "🔥 相關性熱圖與滾動分析",
    "⏱️ 領先落後關係",
    "📅 關稅重大事件研究",
    "🤖 AI 深度研究摘要",
    "ℹ️ 資料品質與來源說明",
])


# ==========================================
# TAB 1: 總覽儀表板
# ==========================================
with tab1:
    st.subheader("🎯 核心指標與即時行情看板")

    # 頂部 KPI 卡片：匯率
    st.markdown("##### 💱 匯率與美元指數概況 (中價／收盤價)")
    fx_cols_display = st.columns(max(1, len(selected_fx)))
    for idx, sym in enumerate(selected_fx):
        if sym in df_prices.columns:
            s_series = df_prices[sym].dropna()
            latest_v = s_series.iloc[-1]
            ret_5d = ((latest_v - s_series.iloc[-6]) / s_series.iloc[-6] * 100) if len(s_series) >= 6 else 0
            ret_tot = ((latest_v - s_series.iloc[0]) / s_series.iloc[0] * 100) if len(s_series) >= 2 else 0

            fx_info = DEFAULT_FX_SYMBOLS.get(sym, {"name": sym, "unit": ""})
            with fx_cols_display[idx]:
                st.metric(
                    label=f"{sym} {fx_info['name'].split('(')[0].strip()}",
                    value=f"{latest_v:.3f} {fx_info.get('unit', '')}",
                    delta=f"5日: {ret_5d:+.2f}% | 區間: {ret_tot:+.2f}%",
                    delta_color="normal",
                )

    st.markdown("---")

    # 頂部 KPI 卡片：出口族群等權重
    st.markdown("##### 🏭 台灣出口族群等權重表現 (基期 = 100)")
    sec_cols_display = st.columns(max(1, len(df_sec_prices.columns)))
    for idx, sec_name in enumerate(df_sec_prices.columns):
        s_series = df_sec_prices[sec_name].dropna()
        latest_v = s_series.iloc[-1]
        ret_5d = ((latest_v - s_series.iloc[-6]) / s_series.iloc[-6] * 100) if len(s_series) >= 6 else 0
        ret_tot = ((latest_v - s_series.iloc[0]) / s_series.iloc[0] * 100) if len(s_series) >= 2 else 0

        with sec_cols_display[idx]:
            st.metric(
                label=f"族群：{sec_name}",
                value=f"{latest_v:.2f} 點",
                delta=f"5日: {ret_5d:+.2f}% | 區間: {ret_tot:+.2f}%",
                delta_color="normal",
            )

    st.markdown("---")

    # 核心大圖：匯率 vs 出口族群標準化走勢
    st.subheader("📈 匯率與出口族群標準化走勢總覽 (基期 100)")
    fig_overview = plot_normalized_comparison(
        combined_norm,
        events_list=st.session_state.events_list,
        title="主要匯率與台灣出口族群等權重指數走勢對照 (起點 = 100)",
    )
    st.plotly_chart(fig_overview, use_container_width=True)

    # 數據表
    with st.expander("📋 檢視各標的完整數值與變化率清單", expanded=False):
        st.dataframe(
            summary_metrics.style.format({
                "最新值": "{:.4f}",
                "5日變化率 (%)": "{:+.2f}%",
                "20日變化率 (%)": "{:+.2f}%",
                "期間累積報酬 (%)": "{:+.2f}%",
                "最高值": "{:.4f}",
                "最低值": "{:.4f}",
            }),
            use_container_width=True,
        )


# ==========================================
# TAB 2: 多幣別與指數走勢
# ==========================================
with tab2:
    st.subheader("💱 多幣別匯率與美元指數深度走勢")
    st.caption("分析美元指數 (^NYICDX)、USD/TWD、USD/JPY、USD/CNY 之獨立與交叉表現")

    show_events_fx = st.checkbox("在圖表上顯示重大關稅與政策事件垂直標記", value=True, key="chk_ev_fx")

    # 匯率標準化走勢
    fx_norm_df = df_norm_all[selected_fx] if all(c in df_norm_all.columns for c in selected_fx) else df_norm_all
    fig_fx_norm = plot_normalized_comparison(
        fx_norm_df,
        events_list=st.session_state.events_list if show_events_fx else None,
        title="各幣別與美元指數相對升貶走勢比較 (基期 100，數值上升代表美元升值/當地幣貶值)",
    )
    st.plotly_chart(fig_fx_norm, use_container_width=True)

    st.markdown("---")

    # 原始獨立報價
    st.subheader("📊 各幣別原始牌告收盤行情 (中價)")
    fig_fx_raw = plot_original_fx_series(
        df_prices,
        selected_fx,
        events_list=st.session_state.events_list if show_events_fx else None,
    )
    st.plotly_chart(fig_fx_raw, use_container_width=True)


# ==========================================
# TAB 3: 出口族群與個股表現
# ==========================================
with tab3:
    st.subheader("🏭 台灣出口族群與成分股績效對照")

    # 族群累積報酬長條圖
    sec_metrics = summary_metrics[summary_metrics["標的名稱"].isin(df_sec_prices.columns)]
    fig_sec_bar = plot_sector_returns_bar(
        sec_metrics,
        title=f"各出口族群區間等權重累積報酬率排行 ({date_start_str} ~ {date_end_str})"
    )
    st.plotly_chart(fig_sec_bar, use_container_width=True)

    st.markdown("---")

    # 個別族群細部拆解
    st.subheader("🔍 個別族群成分股走勢細部拆解")
    chosen_sec = st.selectbox("選擇要檢視的族群", options=list(st.session_state.sectors_config.keys()))

    if chosen_sec in st.session_state.sectors_config:
        stk_map = st.session_state.sectors_config[chosen_sec]["stocks"]
        valid_stk_cols = [c for c in stk_map.keys() if c in df_norm_all.columns]

        if valid_stk_cols:
            col_chart, col_tbl = st.columns([3, 2])

            with col_chart:
                sub_norm = df_norm_all[valid_stk_cols].copy()
                # 重新命名欄位以便閱讀
                sub_norm.columns = [f"{c.replace('.TW','')} {stk_map.get(c, '')}" for c in valid_stk_cols]
                fig_sub = plot_normalized_comparison(
                    sub_norm,
                    events_list=st.session_state.events_list,
                    title=f"「{chosen_sec}」族群成分股標準化走勢比較",
                )
                st.plotly_chart(fig_sub, use_container_width=True)

            with col_tbl:
                st.markdown(f"##### 📊 {chosen_sec}成分股績效明細")
                stk_summary = compute_metrics_summary(df_prices[valid_stk_cols])
                stk_summary["標的名稱"] = stk_summary["標的名稱"].apply(lambda x: f"{x.replace('.TW','')} {stk_map.get(x, '')}")
                st.dataframe(
                    stk_summary.style.format({
                        "最新值": "{:.2f}",
                        "5日變化率 (%)": "{:+.2f}%",
                        "20日變化率 (%)": "{:+.2f}%",
                        "期間累積報酬 (%)": "{:+.2f}%",
                        "最高值": "{:.2f}",
                        "最低值": "{:.2f}",
                    }),
                    use_container_width=True,
                )


# ==========================================
# TAB 4: 相關性熱圖與滾動分析
# ==========================================
with tab4:
    st.subheader("🔥 匯率與出口股相關係數分析")

    col_opt1, col_opt2 = st.columns(2)
    corr_method = col_opt1.radio(
        "相關係數計算基礎",
        options=["每日報酬率 (Daily Returns，標準量化作法)", "累積價格水準 (Price Level)"],
        index=0,
    )
    method_key = "returns" if "Daily" in corr_method else "prices"

    # 計算全矩陣
    corr_df = compute_correlation_matrix(combined_prices, method=method_key)

    fig_corr = plot_correlation_heatmap(
        corr_df,
        title=f"Pearson 相關係數熱圖 ({corr_method.split('（')[0].strip()})"
    )
    st.plotly_chart(fig_corr, use_container_width=True)

    st.markdown("---")

    # 20 日滾動相關分析
    st.subheader("🔄 20 日動態滾動相關係數走勢")
    st.caption("觀察匯率與出口族群連動關係是否隨時間、關稅事件或匯率急升貶而產生結構性轉變")

    col_r1, col_r2 = st.columns(2)
    rolling_fx_target = col_r1.selectbox(
        "選擇基準匯率",
        options=selected_fx,
        index=selected_fx.index("TWD=X") if "TWD=X" in selected_fx else 0,
        format_func=lambda x: f"{x} ({DEFAULT_FX_SYMBOLS.get(x, {}).get('name', x)})",
    )

    rolling_assets = col_r2.multiselect(
        "選擇對照族群或個股",
        options=list(df_sec_prices.columns),
        default=list(df_sec_prices.columns)[:3],
    )

    if rolling_fx_target and rolling_assets:
        rolling_series_map = {}
        for a in rolling_assets:
            if a in combined_prices.columns and rolling_fx_target in combined_prices.columns:
                s_roll = compute_rolling_correlation(
                    combined_prices[rolling_fx_target],
                    combined_prices[a],
                    window=20,
                )
                rolling_series_map[f"{rolling_fx_target} vs {a}"] = s_roll

        fig_rolling = plot_rolling_correlation(
            rolling_series_map,
            events_list=st.session_state.events_list,
            title=f"20 日滾動相關係數走勢 ({rolling_fx_target} 對 各出口族群)",
        )
        st.plotly_chart(fig_rolling, use_container_width=True)


# ==========================================
# TAB 5: 領先落後關係
# ==========================================
with tab5:
    st.subheader("⏱️ 匯率與出口股領先落後交叉相關分析")
    st.caption("檢定匯率變化是否領先出口股反映（如外匯市場先行吸收總經關稅訊息），或股票領先匯率調整")

    col_ll1, col_ll2 = st.columns(2)
    lead_fx = col_ll1.selectbox(
        "選擇匯率標的",
        options=selected_fx,
        index=selected_fx.index("TWD=X") if "TWD=X" in selected_fx else 0,
        format_func=lambda x: f"{x} ({DEFAULT_FX_SYMBOLS.get(x, {}).get('name', x)})",
        key="sb_ll_fx"
    )
    lead_target = col_ll2.selectbox(
        "選擇對照族群/個股",
        options=list(combined_prices.columns),
        index=len(selected_fx),
        key="sb_ll_target"
    )

    if lead_fx in combined_prices.columns and lead_target in combined_prices.columns:
        lead_lag_df = compute_lead_lag_correlations(
            combined_prices[lead_fx],
            combined_prices[lead_target],
            lags=LEAD_LAG_DAYS,
        )

        col_ll_chart, col_ll_tbl = st.columns([3, 2])

        with col_ll_chart:
            fig_ll = plot_lead_lag_bars(
                lead_lag_df,
                title=f"【{lead_fx}】相對於【{lead_target}】領先落後交叉相關係數"
            )
            st.plotly_chart(fig_ll, use_container_width=True)

        with col_ll_tbl:
            st.markdown("##### 📋 平移期數與相關係數矩陣")
            st.dataframe(
                lead_lag_df.style.format({"相關係數 (r)": "{:+.4f}"}),
                use_container_width=True,
            )

            # 結論提示卡
            best_idx = lead_lag_df["相關係數 (r)"].abs().idxmax()
            best_row = lead_lag_df.loc[best_idx]
            st.info(
                f"💡 **判讀發現**：最高連動強度出現在 **{best_row['關係說明']}**（r = `{best_row['相關係數 (r)']:+.4f}`）。"
            )


# ==========================================
# TAB 6: 關稅重大事件研究
# ==========================================
with tab6:
    st.subheader("📅 重大關稅與匯率政策事件研究 (Event Study ±5 交易日)")
    st.caption("分析事件日前後 5 個交易日（合計 11 日窗口）各幣別匯率與出口族群之波動與報酬傳遞")

    event_options = [f"{ev['date']} | {ev['label']}" for ev in st.session_state.events_list]
    selected_ev_str = st.selectbox("選擇要檢視的重大事件", options=event_options, index=0)

    selected_ev_obj = None
    for ev in st.session_state.events_list:
        if f"{ev['date']} | {ev['label']}" == selected_ev_str:
            selected_ev_obj = ev
            break

    if selected_ev_obj:
        st.markdown(
            f"""
            > **事件說明**：`{selected_ev_obj['label']}`  
            > **分類**：`{selected_ev_obj.get('category', '關稅/政策')}` ｜ **日期**：`{selected_ev_obj['date']}`  
            > **背景備註**：{selected_ev_obj.get('note', '無')}
            """
        )

        ev_result = perform_event_study(
            combined_prices,
            event_date_str=selected_ev_obj["date"],
            event_label=selected_ev_obj["label"],
            window=5,
        )

        if ev_result.get("valid"):
            # 走勢軌跡圖
            fig_ev_traj = plot_event_study_trajectory(
                ev_result["norm_window_df"],
                t0_date=ev_result["actual_t0"],
                event_label=selected_ev_obj["label"],
            )
            st.plotly_chart(fig_ev_traj, use_container_width=True)

            # 前後 5 日報酬比較表
            st.markdown(f"##### 📊 事件日前後報酬統計表 (基準交易日：`{ev_result['actual_t0']}`)")
            st.dataframe(
                ev_result["summary_table"].style.format({
                    "前 5 日報酬 (%)": "{:+.2f}%",
                    "後 5 日報酬 (%)": "{:+.2f}%",
                    "前後 10 日總變化 (%)": "{:+.2f}%",
                    "事件日當天值": "{:.3f}",
                }),
                use_container_width=True,
            )
        else:
            st.warning(f"⚠️ {ev_result.get('message', '事件日資料不足以建構前後 5 日窗口')}")


# ==========================================
# TAB 7: AI 深度研究摘要
# ==========================================
with tab7:
    st.subheader("🤖 AI 智慧研究結論報告 (成大四節規範標準)")
    st.caption("基於真實清洗資料與量化回測結果，自動生成符合合規聲明之結構化研究結論")

    # 預先計算領先落後全貌
    lead_lag_all_results = {}
    for fx_s in selected_fx[:2]:
        for sec_s in list(df_sec_prices.columns)[:2]:
            if fx_s in combined_prices.columns and sec_s in combined_prices.columns:
                pair_key = f"{fx_s} vs {sec_s}"
                lead_lag_all_results[pair_key] = compute_lead_lag_correlations(
                    combined_prices[fx_s], combined_prices[sec_s]
                )

    # 預先計算所有事件研究
    all_ev_results = []
    for ev in st.session_state.events_list:
        res = perform_event_study(
            combined_prices,
            event_date_str=ev["date"],
            event_label=ev["label"],
            window=5,
        )
        if res.get("valid"):
            all_ev_results.append(res)

    # 生成 AI 報告
    ai_report_markdown = generate_ai_research_report(
        df_prices=combined_prices,
        df_metrics=summary_metrics,
        corr_matrix=corr_df,
        lead_lag_results=lead_lag_all_results,
        event_study_results=all_ev_results,
        date_start=date_start_str,
        date_end=date_end_str,
        selected_fx_symbols=selected_fx,
        selected_sectors=list(df_sec_prices.columns),
    )

    st.markdown(ai_report_markdown)

    st.markdown("---")

    # 下載與匯出區
    st.subheader("📥 匯出研究報告與清洗後資料集")
    col_dl1, col_dl2, col_dl3, col_dl4 = st.columns(4)

    with col_dl1:
        st.download_button(
            label="📄 下載 AI 研究報告 (.md)",
            data=ai_report_markdown,
            file_name=f"ai_research_report_{date_end_str}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col_dl2:
        csv_aligned = df_prices.to_csv(encoding="utf-8-sig")
        st.download_button(
            label="📊 下載對齊行情 (.csv)",
            data=csv_aligned,
            file_name="fx_stocks_aligned.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col_dl3:
        csv_sectors = df_sec_prices.to_csv(encoding="utf-8-sig")
        st.download_button(
            label="🏭 下載族群指數 (.csv)",
            data=csv_sectors,
            file_name="sector_indices.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col_dl4:
        if all_ev_results:
            ev_export_df = pd.concat([r["summary_table"].assign(事件=r["event_label"]) for r in all_ev_results])
            csv_ev = ev_export_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="📅 下載事件研究 (.csv)",
                data=csv_ev,
                file_name="event_study_summary.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ==========================================
# TAB 8: 資料品質與來源說明
# ==========================================
with tab8:
    st.subheader("ℹ️ 資料源品質、處理方法與系統合規聲明")

    st.markdown(
        """
        ### 1. 資料來源 (Data Sources)
        - **外匯與美元指數**：優先採用 **Yahoo Finance Chart API**。
          - `^NYICDX`：ICE 美元指數（加權籃子）。
          - `TWD=X`：美元兌新台幣匯率（**中價／收盤價**）。
          - `JPY=X`：美元兌日圓匯率（中價）。
          - `CNY=X` / `CNH=X`：美元兌在岸／離岸人民幣匯率（中價）。
        - **台灣出口族群股票**：以公開行情代號（如 `2330.TW`, `2317.TW`）抓取歷史日線收盤價。
        - **原始資料庫存**：每次抓取之原始 JSON/CSV 均自動持久化於本機 `raw/` 目錄。
        - **清洗資料庫存**：交易日對齊與標準化後資料集自動持久化於本機 `data/` 目錄。

        ### 2. 報價方向解讀法則
        - 匯率統一採用 `USD/XXX`（美元對外幣）形式標價。
        - **數值上升** ➔ 美元升值、該國貨幣貶值（如 USD/TWD 自 30.5 上升至 32.0 代表新台幣貶值）。
        - **數值下降** ➔ 美元貶值、該國貨幣升值（如 USD/TWD 自 32.0 下降至 30.5 代表新台幣升值）。

        ### 3. 處理方法與限制
        - **中價特性**：Yahoo 外匯資料為每日收盤中價，無買價（Bid）與賣價（Ask）雙向報價，無法反映市場點差（Spread）擴大時之流動性成本。
        - **跨市場交易日曆對齊**：不同市場開休市日差異採用 `Forward-Fill` 前向填補，確保多資產矩陣在數學計算時之一致性。
        - **快取與備援機制**：若網路斷線或端點連線異常，系統具備自動 3 次重試與自動載入本機 `raw/` 快取檔案之雙重備援機制。

        ---
        """
    )

    st.markdown(
        f"""
        <div class="disclaimer-box">
        <b>⚖️ 合規聲明 (Disclaimer)</b><br>
        {DISCLAIMER_TEXT}<br>
        本工具開發目的為學術教育與金融資料工程實作，所有計算指標、相關係數及 AI 生成摘要均為歷史數據之量化觀察，
        不推薦個股、不預測行情、不產生買賣指令，使用者不應將本報告作為任何投資決策之唯一依據。
        </div>
        """,
        unsafe_allow_html=True,
    )
