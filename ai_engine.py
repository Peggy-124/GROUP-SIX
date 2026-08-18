# -*- coding: utf-8 -*-
"""
AI 智慧研究報告生成模組 (AI Engine)
根據計算產出的量化指標（現況數值、相關係數、領先落後平移、事件日前後報酬），
依據成大課堂規範生成結構化「四節研究結論報告」，杜絕數據幻覺，提供嚴謹的總經與產業判讀。
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd
from config import DISCLAIMER_TEXT


def generate_ai_research_report(
    df_prices: pd.DataFrame,
    df_metrics: pd.DataFrame,
    corr_matrix: pd.DataFrame,
    lead_lag_results: Dict[str, pd.DataFrame],
    event_study_results: List[Dict[str, Any]],
    date_start: str,
    date_end: str,
    selected_fx_symbols: List[str],
    selected_sectors: List[str]
) -> str:
    """
    生成標準四節結構化結論報告
    1. ① 現況數字
    2. ② 與關稅事件日的對照
    3. ③ 判讀
    4. ④ 限制與失效條件
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- 1. 現況數字提取 ---
    fx_rows = []
    sec_rows = []
    if not df_metrics.empty:
        for _, row in df_metrics.iterrows():
            target = row["標的名稱"]
            val = row["最新值"]
            ret_5d = row["5日變化率 (%)"]
            ret_20d = row["20日變化率 (%)"]
            ret_total = row["期間累積報酬 (%)"]

            str_5d = f"{ret_5d:+.2f}%" if pd.notnull(ret_5d) else "N/A"
            str_20d = f"{ret_20d:+.2f}%" if pd.notnull(ret_20d) else "N/A"
            str_tot = f"{ret_total:+.2f}%" if pd.notnull(ret_total) else "N/A"

            line = f"- **{target}**：最新收盤價/中價 `{val:.4f}`，近5日 `{str_5d}`，近20日 `{str_20d}`，分析區間總累積 `{str_tot}`"

            is_fx = any(k in target for k in ["TWD", "NYICDX", "JPY", "CNY", "CNH", "美元", "指數"])
            if is_fx:
                fx_rows.append(line)
            else:
                sec_rows.append(line)

    fx_figures_text = "\n".join(fx_rows) if fx_rows else "- (查無匯率數據)"
    sec_figures_text = "\n".join(sec_rows) if sec_rows else "- (查無族群數據)"

    # --- 2. 相關性最高與最低配對尋找 ---
    top_corr_info = []
    if not corr_matrix.empty:
        fx_cols = [c for c in corr_matrix.columns if any(k in c for k in ["TWD", "NYICDX", "JPY", "CNY", "CNH", "X"])]
        asset_cols = [c for c in corr_matrix.columns if c not in fx_cols]

        pairs = []
        for f_col in fx_cols:
            for a_col in asset_cols:
                r_val = corr_matrix.loc[f_col, a_col]
                if pd.notnull(r_val):
                    pairs.append((f_col, a_col, float(r_val)))

        # 按相關性絕對值排序
        pairs_sorted = sorted(pairs, key=lambda x: abs(x[2]), reverse=True)
        for f_c, a_c, r in pairs_sorted[:4]:
            direction_str = "正向同步連動" if r > 0 else "負向反向連動"
            strength = "高度" if abs(r) >= 0.6 else ("中度" if abs(r) >= 0.3 else "低度")
            top_corr_info.append(
                f"- **{f_c}** 與 **{a_c}**：Pearson 相關係數 `r = {r:+.4f}`（呈現{strength}{direction_str}）"
            )

    corr_summary_text = "\n".join(top_corr_info) if top_corr_info else "- (相關性計算樣本不足)"

    # --- 3. 領先落後發現 ---
    lead_lag_insights = []
    for pair_name, lldf in lead_lag_results.items():
        if not lldf.empty:
            best_row = lldf.loc[lldf["相關係數 (r)"].abs().idxmax()]
            k = best_row["Lag_Days"]
            r_max = best_row["相關係數 (r)"]
            desc = best_row["關係說明"]
            lead_lag_insights.append(
                f"- **{pair_name}**：最大相關性落在 **{desc}**，相關係數 `r = {r_max:+.4f}`"
            )
    lead_lag_text = "\n".join(lead_lag_insights) if lead_lag_insights else "- (未執行領先落後計算)"

    # --- 4. 事件日觀察 ---
    event_observations = []
    for ev in event_study_results:
        if ev.get("valid"):
            e_label = ev.get("event_label", "未知事件")
            e_date = ev.get("event_date")
            act_t0 = ev.get("actual_t0")
            sum_tbl = ev.get("summary_table", pd.DataFrame())

            obs_lines = [f"### 📍 事件：{e_label} (事件日：{e_date}，對齊交易日：{act_t0})"]
            if not sum_tbl.empty:
                for _, r in sum_tbl.iterrows():
                    sym = r["標的名稱"]
                    pre = r["前 5 日報酬 (%)"]
                    post = r["後 5 日報酬 (%)"]
                    tot = r["前後 10 日總變化 (%)"]
                    obs_lines.append(
                        f"  - `{sym}`: 前5日 `{pre:+.2f}%` ➔ 後5日 `{post:+.2f}%` (10日窗口總變化: `{tot:+.2f}%`)"
                    )
            event_observations.append("\n".join(obs_lines))

    events_summary_text = "\n\n".join(event_observations) if event_observations else "- (所選區間內未涵蓋預設事件日，或事件日前後交易日不足)"

    # --- 組裝完整報告 ---
    report_md = f"""# 匯率與出口股連動分析報告（AI 股票研究結論）

> **資料觀測期間**：`{date_start}` 至 `{date_end}`  
> **報告生成時間**：`{now_str}`  
> **觀測幣別與指數**：{', '.join(selected_fx_symbols)}  
> **出口族群標的**：{', '.join(selected_sectors)}  

---

## ① 現況數字

以下所有數值均取自本次資料清洗與對齊後之真實行情計算結果：

### 1. 匯率與美元指數行情（Yahoo Finance 中價／收盤價）
> 💡 **報價方向解讀**：本工具外匯皆採用 `USD/XXX` 標價法。數值**上升**代表**美元升值、該國貨幣貶值**；數值**下降**代表**美元貶值、該國貨幣升值**。

{fx_figures_text}

### 2. 台灣出口族群與個股報酬表現（等權重族群指數）
{sec_figures_text}

---

## ② 與關稅事件日的對照

針對重大關稅、貿易談判與供應鏈政策事件日前後各 5 個交易日（合計 11 日窗口）進行連動反應回溯：

{events_summary_text}

---

## ③ 判讀

### 1. 匯率升貶方向對出口族群之傳遞機制
- **美元兌台幣 (USD/TWD) 走勢與出口競爭力**：
  當 USD/TWD 上升（台幣貶值）時，台灣以美元計價報價之出口型科技與製造業（如半導體晶圓代工、電子代工 EMS）在換算回台幣營收時具備**毛利率擴張與帳面匯兌利益**；反之，若台幣急升（USD/TWD 走低），短期常引發外銷毛利受壓與匯損提列之擔憂。
- **美元強弱與國際資金流向之抵銷效應**：
  儘管台幣貶值有利出口實體毛利，但若美元指數 (DXY) 全面急升，往往伴隨國際外資自新興市場與台股大盤撤出。因此，高權值股（如台積電 2330、鴻海 2317）常在「實體外銷受惠」與「外資被動賣壓」兩股力量間交錯拉鋸。

### 2. 跨幣別與出口族群連動強度觀察
{corr_summary_text}

- **半導體族群 (Semiconductors)**：營運具備極高議價權與國際定價能力，受海外終端景氣與先進製程資本支出週期主導，匯率為次要調節因子。
- **電子代工族群 (EMS)**：毛利率多在 5%~8% 水準，對匯率波動之彈性敏感度高於半導體，常與美元走勢呈現階段性同向修復。
- **航運族群 (Shipping)**：全球運價以美元結算，且直接反映國際貿易量能與關稅生效前之「提前拉貨（Front-loading）」潮。
- **自行車族群 (Bicycle)**：歐洲與北美終端消費市場庫存去化進度與關稅稅率具實質關聯。

### 3. 領先與落後時序關係
{lead_lag_text}
- 若外匯市場波動領先股票 1~3 個交易日反應，顯示外匯市場對總體政策及貿易訊息吸收速度較快，可作為出口股短期避險之早期參考指標。

---

## ④ 限制與失效條件

本研究結論建立於歷史量化觀測，判讀時須留意以下資料邊界與失效情境：

1. **資料源特徵限制**：
   - Yahoo Finance 外匯資料僅提供**每日中價／收盤價**，無買入（Bid）與賣出（Ask）雙向即時撮合價差，亦不含外匯保證金槓桿融資利息成本。
   - 跨國市場時區與交易日曆不一致：台股收盤時間（台北 13:30）與美股及紐約外匯結算時間（美東 17:00）存在跨日時間差，採用 Forward-fill 對齊在極端跳空行情下可能低估當日瞬間波動率。
2. **事件樣本數不足（Small Sample Size）**：
   - 歷史重大關稅事件樣本數量有限，事件研究（Event Study）呈現的是「特定時空背景下的歷史共變反應」，不可直接線性推論為未來必然發生的因果規律。
3. **判讀失效條件**：
   - **非線性關稅與供應鏈豁免條款**：若未來關稅政策搭配特定國家或特定產品專案豁免，或被課稅方迅速將產能移轉至美國本土，傳統「匯率貶值補償關稅」之邏輯將出現結構性翻盤。
   - **全球系統性流動性危機**：當發生恐慌性拋售（Liquidity Crunch）時，美元可能因避險需求急速飆升，但所有風險性股票資產無論出口競爭力強弱皆遭無差別拋售。

---

> **合規聲明**  
> {DISCLAIMER_TEXT}
"""
    return report_md
