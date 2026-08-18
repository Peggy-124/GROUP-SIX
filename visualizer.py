# -*- coding: utf-8 -*-
"""
視覺化模組 (Visualizer)
以 Plotly 打造高互動性、繁體中文、支援事件標註、標準化走勢、相關性熱圖、滾動相關與領先落後圖表。
"""
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


COLOR_PALETTE = [
    "#2E86AB",  # 藍
    "#D90429",  # 紅
    "#06D6A0",  # 綠
    "#FFB703",  # 黃
    "#8338EC",  # 紫
    "#FB5607",  # 橘
    "#3A86FF",  # 天藍
    "#118AB2",  # 藍綠
    "#EF476F",  # 粉紅
    "#073B4C",  # 深藍
    "#6D597A",  # 紫褐
    "#355070",  # 灰藍
]


def add_event_lines(
    fig: go.Figure,
    events_list: List[Dict[str, Any]],
    date_min: pd.Timestamp,
    date_max: pd.Timestamp,
    show_labels: bool = True
) -> go.Figure:
    """在 Plotly 圖表上加入重大事件垂直虛線與標記"""
    for event in events_list:
        e_date_str = event.get("date")
        e_label = event.get("label", "重大事件")
        try:
            e_dt = pd.to_datetime(e_date_str)
            if date_min <= e_dt <= date_max:
                fig.add_vline(
                    x=e_dt,
                    line_width=1.5,
                    line_dash="dash",
                    line_color="#E63946",
                    annotation_text=e_label if show_labels else "",
                    annotation_position="top left",
                    annotation_font=dict(size=10, color="#E63946"),
                    annotation_bgcolor="rgba(255, 255, 255, 0.8)",
                )
        except Exception:
            continue
    return fig


def plot_normalized_comparison(
    df_norm: pd.DataFrame,
    events_list: Optional[List[Dict[str, Any]]] = None,
    title: str = "標準化走勢比較圖 (基期 100)",
    highlight_cols: Optional[List[str]] = None
) -> go.Figure:
    """繪製基期 100 標準化走勢比較圖"""
    fig = go.Figure()

    if df_norm.empty:
        fig.update_layout(title="無可用資料")
        return fig

    date_min = df_norm.index.min()
    date_max = df_norm.index.max()

    cols = df_norm.columns
    for idx, col in enumerate(cols):
        is_highlight = highlight_cols is not None and col in highlight_cols
        line_width = 3.0 if is_highlight else 1.8
        opacity = 1.0 if (highlight_cols is None or is_highlight) else 0.4
        color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]

        fig.add_trace(
            go.Scatter(
                x=df_norm.index,
                y=df_norm[col],
                mode="lines",
                name=col,
                line=dict(width=line_width, color=color),
                opacity=opacity,
                hovertemplate="<b>%{x|%Y-%m-%d}</b><br>" + f"{col}: " + "%{y:.2f}<extra></extra>",
            )
        )

    # 基準 100 水平虛線
    fig.add_hline(
        y=100,
        line_dash="dot",
        line_color="#888888",
        line_width=1,
        annotation_text="基期 100",
        annotation_position="bottom right"
    )

    if events_list:
        fig = add_event_lines(fig, events_list, date_min, date_max)

    fig.update_layout(
        title=dict(text=title, font=dict(size=18, color="#1E293B")),
        xaxis=dict(title="交易日期", showgrid=True, gridcolor="#E2E8F0"),
        yaxis=dict(title="標準化點數 (起點 = 100)", showgrid=True, gridcolor="#E2E8F0"),
        hovermode="x unified",
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40),
        height=500,
    )
    return fig


def plot_original_fx_series(
    df_prices: pd.DataFrame,
    fx_cols: List[str],
    events_list: Optional[List[Dict[str, Any]]] = None
) -> go.Figure:
    """繪製原始匯率與美元指數報價走勢"""
    valid_cols = [c for c in fx_cols if c in df_prices.columns]
    if not valid_cols:
        fig = go.Figure()
        fig.update_layout(title="無匯率資料")
        return fig

    fig = make_subplots(
        rows=len(valid_cols),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=[f"{col} 原始行情 (中價/收盤價)" for col in valid_cols]
    )

    date_min = df_prices.index.min()
    date_max = df_prices.index.max()

    for i, col in enumerate(valid_cols, start=1):
        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
        fig.add_trace(
            go.Scatter(
                x=df_prices.index,
                y=df_prices[col],
                mode="lines",
                name=col,
                line=dict(width=2.0, color=color),
                hovertemplate="<b>%{x|%Y-%m-%d}</b><br>價格: %{y:.4f}<extra></extra>",
            ),
            row=i,
            col=1
        )
        fig.update_yaxes(title_text="匯率/點數", row=i, col=1, gridcolor="#F1F5F9")
        fig.update_xaxes(showgrid=True, gridcolor="#F1F5F9", row=i, col=1)

    fig.update_layout(
        title=dict(text="各幣別與美元指數原始行情（數值上升代表美元升值／當地貨幣貶值）", font=dict(size=16)),
        hovermode="x unified",
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        height=180 * len(valid_cols) + 100,
        showlegend=False,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


def plot_correlation_heatmap(
    corr_df: pd.DataFrame,
    title: str = "Pearson 相關係數熱圖 (日報酬)"
) -> go.Figure:
    """繪製相關係數熱圖"""
    if corr_df.empty:
        fig = go.Figure()
        fig.update_layout(title="無相關係數資料")
        return fig

    z_vals = corr_df.values
    x_labels = corr_df.columns.tolist()
    y_labels = corr_df.index.tolist()

    # 文字標籤
    text_vals = [[f"{val:.2f}" for val in row] for row in z_vals]

    fig = go.Figure(
        data=go.Heatmap(
            z=z_vals,
            x=x_labels,
            y=y_labels,
            text=text_vals,
            texttemplate="%{text}",
            textfont=dict(size=11),
            colorscale="RdBu_r",  # 負相關為藍，正相關為紅
            zmin=-1.0,
            zmax=1.0,
            colorbar=dict(title="相關係數 (r)"),
            hovertemplate="<b>%{y}</b> 與 <b>%{x}</b><br>相關係數: %{z:.4f}<extra></extra>",
        )
    )

    fig.update_layout(
        title=dict(text=title, font=dict(size=17, color="#1E293B")),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        xaxis=dict(tickangle=-30, showgrid=False),
        yaxis=dict(autorange="reversed", showgrid=False),
        height=max(450, len(y_labels) * 35 + 150),
        margin=dict(l=60, r=40, t=60, b=80),
    )
    return fig


def plot_rolling_correlation(
    rolling_series_dict: Dict[str, pd.Series],
    events_list: Optional[List[Dict[str, Any]]] = None,
    title: str = "20 日滾動相關係數走勢 (與美元兌新台幣 USD/TWD)"
) -> go.Figure:
    """繪製 20 日滾動相關係數折線圖"""
    fig = go.Figure()

    all_dts = []
    for idx, (label, s) in enumerate(rolling_series_dict.items()):
        if s.empty:
            continue
        all_dts.extend(s.index.tolist())
        color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
        fig.add_trace(
            go.Scatter(
                x=s.index,
                y=s.values,
                mode="lines",
                name=label,
                line=dict(width=2.0, color=color),
                hovertemplate="<b>%{x|%Y-%m-%d}</b><br>" + f"{label}: " + "%{y:.4f}<extra></extra>",
            )
        )

    # 零基準線
    fig.add_hline(
        y=0,
        line_dash="solid",
        line_color="#475569",
        line_width=1.2,
        annotation_text="零相關基準線",
        annotation_position="bottom right",
    )

    # 加上 +0.5 與 -0.5 參考線
    fig.add_hline(y=0.5, line_dash="dot", line_color="#CBD5E1", line_width=1)
    fig.add_hline(y=-0.5, line_dash="dot", line_color="#CBD5E1", line_width=1)

    if events_list and all_dts:
        date_min = min(all_dts)
        date_max = max(all_dts)
        fig = add_event_lines(fig, events_list, date_min, date_max, show_labels=False)

    fig.update_layout(
        title=dict(text=title, font=dict(size=17, color="#1E293B")),
        xaxis=dict(title="交易日期", showgrid=True, gridcolor="#F1F5F9"),
        yaxis=dict(
            title="20日滾動相關係數",
            range=[-1.05, 1.05],
            showgrid=True,
            gridcolor="#F1F5F9"
        ),
        hovermode="x unified",
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40),
        height=450,
    )
    return fig


def plot_lead_lag_bars(
    lead_lag_df: pd.DataFrame,
    title: str = "匯率與標的領先落後交叉相關係數分析"
) -> go.Figure:
    """繪製領先落後交叉相關性長條圖"""
    if lead_lag_df.empty:
        fig = go.Figure()
        fig.update_layout(title="無領先落後資料")
        return fig

    # 根據正負相關給予紅藍配色
    colors = ["#EF476F" if v >= 0 else "#118AB2" for v in lead_lag_df["相關係數 (r)"]]

    fig = go.Figure(
        data=go.Bar(
            x=lead_lag_df["關係說明"],
            y=lead_lag_df["相關係數 (r)"],
            marker_color=colors,
            text=[f"{v:.3f}" for v in lead_lag_df["相關係數 (r)"]],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>相關係數: %{y:.4f}<extra></extra>",
        )
    )

    fig.add_hline(y=0, line_color="#334155", line_width=1.2)

    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color="#1E293B")),
        xaxis=dict(title="平移期數 (Lag / Lead)", showgrid=False),
        yaxis=dict(title="Pearson 相關係數 (r)", range=[-1.0, 1.0], showgrid=True, gridcolor="#F1F5F9"),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        margin=dict(l=40, r=40, t=60, b=50),
        height=400,
    )
    return fig


def plot_event_study_trajectory(
    norm_window_df: pd.DataFrame,
    t0_date: str,
    event_label: str
) -> go.Figure:
    """繪製重大事件日前後 5 日走勢窗口圖 (以 t0-5 = 100)"""
    fig = go.Figure()

    if norm_window_df.empty:
        fig.update_layout(title="無事件窗口資料")
        return fig

    # 將 x 軸轉換為相對於 t0 的交易日序數 (-5, -4, ..., 0, ..., +5)
    dates = norm_window_df.index
    t0_dt = pd.to_datetime(t0_date)
    if t0_dt in dates:
        t0_loc = dates.get_loc(t0_dt)
    else:
        t0_loc = len(dates) // 2

    rel_days = [f"T{i - t0_loc:+d}" if (i - t0_loc) != 0 else "T (事件日)" for i in range(len(dates))]

    for idx, col in enumerate(norm_window_df.columns):
        color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
        is_fx = ("TWD" in col) or ("NYICDX" in col) or ("USD" in col)
        line_dash = "dash" if is_fx else "solid"
        width = 2.8 if is_fx else 1.8

        fig.add_trace(
            go.Scatter(
                x=rel_days,
                y=norm_window_df[col].values,
                mode="lines+markers",
                name=col,
                line=dict(width=width, dash=line_dash, color=color),
                marker=dict(size=5),
                customdata=[str(d)[:10] for d in dates],
                hovertemplate="<b>%{x}</b> (%{customdata})<br>" +
                              f"{col}: %{{y:.2f}}<extra></extra>",
            )
        )

    # 標記 T 點
    fig.add_shape(
        type="line",
        x0="T (事件日)",
        x1="T (事件日)",
        y0=0,
        y1=1,
        xref="x",
        yref="paper",
        line=dict(width=2, dash="dot", color="#E63946"),
    )
    fig.add_annotation(
        x="T (事件日)",
        y=1,
        xref="x",
        yref="paper",
        text="事件生效/發生日",
        showarrow=False,
        xanchor="right",
        yanchor="bottom",
    )
    fig.add_hline(y=100, line_dash="solid", line_color="#94A3B8", line_width=1)

    fig.update_layout(
        title=dict(
            text=f"事件窗口前後 5 個交易日走勢：{event_label} (基準 T-5 = 100)",
            font=dict(size=16, color="#1E293B")
        ),
        xaxis=dict(title="交易日窗口 (T-5 至 T+5)", showgrid=True, gridcolor="#F1F5F9"),
        yaxis=dict(title="標準化累積報酬點數 (T-5=100)", showgrid=True, gridcolor="#F1F5F9"),
        hovermode="x unified",
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40),
        height=480,
    )
    return fig


def plot_sector_returns_bar(
    summary_df: pd.DataFrame,
    title: str = "各族群與標的期間累積報酬比較 (%)"
) -> go.Figure:
    """長條圖比較各標的期間總報酬"""
    if summary_df.empty or "期間累積報酬 (%)" not in summary_df.columns:
        fig = go.Figure()
        fig.update_layout(title="無報酬率資料")
        return fig

    sorted_df = summary_df.sort_values(by="期間累積報酬 (%)", ascending=True)
    colors = ["#EF476F" if v >= 0 else "#118AB2" for v in sorted_df["期間累積報酬 (%)"]]

    fig = go.Figure(
        data=go.Bar(
            x=sorted_df["期間累積報酬 (%)"],
            y=sorted_df["標的名稱"],
            orientation="h",
            marker_color=colors,
            text=[f"{v:+.2f}%" for v in sorted_df["期間累積報酬 (%)"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>期間總報酬: %{x:+.2f}%<extra></extra>",
        )
    )

    fig.add_vline(x=0, line_color="#334155", line_width=1.2)

    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color="#1E293B")),
        xaxis=dict(title="累積報酬率 (%)", showgrid=True, gridcolor="#F1F5F9"),
        yaxis=dict(title="標的", showgrid=False),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        margin=dict(l=100, r=60, t=50, b=40),
        height=max(350, len(sorted_df) * 28 + 100),
    )
    return fig
