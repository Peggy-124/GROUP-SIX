# EvoCode 速查｜在群益交易王 CTA 上寫自訂指標

> 來源：Bob 提供的 TradeApi 知識圖譜（946 個 API 成員、564 個官方範例），
> 2026-08-17 由本課程整理。骨架與 API 名稱**皆出自官方範例原文**，非推測。
> 語言：**C#（.NET）**。用途：**技術分析與指標建構**。
> ⚠️ **本課程只做指標，不做自動下單**——平台雖有下單 API，課堂一律不使用。

## 一、一支指標的完整骨架（照抄就能跑）

```csharp
using Runtime.Script;
using TradeApi.Indicators;

namespace TestEnv
{
    public class MyIndicator : IndicatorBuilder      // ① 一定繼承 IndicatorBuilder
    {
        public MyIndicator() : base()
        {
            Credentials.ProjectName = "MyIndicator";  // ② 專案名稱
            Lines.Set("MyLine");                      // ③ 宣告一條要畫的線
            base.SeparateWindow = false;              // ④ false＝疊在主圖，true＝獨立副圖
        }

        BuiltInIndicator ma;                          // ⑤ 宣告要用的內建指標

        public override void Init()                   // ⑥ 初始化，只跑一次
        {
            ma = IndicatorsManager.BuildIn.MA(HistoryDataSeries, 20, MAMode.EMA);
        }

        public override void Update(TickStatus args)  // ⑦ 每次報價更新都會跑
        {
            if (HistoryDataSeries.Count > 20)         // ⑧ 資料不足時先不要算
            {
                double v = ma.GetValue();
                Lines["MyLine"].SetValue(v);          // ⑨ 把算出來的值畫到線上
            }
        }
    }
}
```

**九個位置就是你要改的全部**：換名稱（②③）、換指標與參數（⑤⑥）、
改計算邏輯（⑦⑨）、決定畫在主圖還是副圖（④）、設定暖身根數（⑧）。

## 二、30 個內建指標（`IndicatorsManager.BuildIn.` 後面接）

| 類型 | 指標 |
|---|---|
| 均線與通道 | `MA`（含 MAMode：SMA／EMA 等）、`Bands`（布林通道）、`Envelopes`、`Ichimoku`、`Alligator`、`Gator` |
| 動能與擺盪 | `RSI`、`MACD`、`Stochastic`、`CCI`、`Momentum`、`WPR`、`DeMarker`、`RVI`、`AO`、`AC`、`OsMA` |
| 趨勢與波動 | `ADX`、`ATR`、`StdDev`、`SAR`、`Fractals` |
| 量能與資金流 | `OBV`、`AD`、`MFI`、`BWMFI`、`Force` |
| 多空力道 | `BullsPower`、`BearsPower` |
| 自訂 | `Custom` |

用法：`indicator = IndicatorsManager.BuildIn.RSI(HistoryDataSeries, 14);`
取值：`indicator.GetValue();`

## 三、常用 API 速查

| 要做的事 | 寫法 |
|---|---|
| 取歷史資料 | `HistoryDataSeries`（`.Count` 可看有幾根） |
| 取當前報價 | `InstrumentsManager.Current.DayInfo.Ask`（買價；Bid 同理） |
| 畫值到線上 | `Lines["線名"].SetValue(值)` 或 `Lines["線名"][0] = 值` |
| 讀線上的值 | `var v = Lines["線名"][0];` |
| 輸出訊息除錯 | `Notification.Print("文字");` |
| 多條線 | 建構子裡多次 `Lines.Set("線A")`、`Lines.Set("線B")` |

## 四、用 AI 幫忙寫的正確方式（本課程的重點）

AI 對 C# 很熟，但**對 TradeApi 這套專有 API 不熟**——它可能編出不存在的函式。
所以正確作法不是叫 AI 憑空生成，而是**給它足夠材料**：

**TASK.md 寫法範例**
```
目標：做一個「收盤價站上 20 日均線就標記」的指標
材料：
  1. 下面這段是平台的官方骨架（把第一節的程式碼整段貼上）
  2. 可用的內建指標清單（把第二節的表格貼上）
  3. 常用 API 速查（把第三節的表格貼上）
驗收：
  1. 能在 CTA 編譯通過、掛得上圖表
  2. 均線值與平台內建 MA 指標對得起來（抽 3 根 K 棒人工核對）
  3. 只用材料裡出現過的 API，沒有自己發明的函式
```

**驗收 AI 產出的三個檢查點**
1. 它用的 API 有沒有出現在速查表裡？沒有的就是它編的。
2. 有沒有保留 `Init()` 與 `Update()` 兩個 override？漏了就跑不起來。
3. 編譯錯誤訊息貼回去給 AI 時，要連同骨架一起貼，不要只貼錯誤。

## 五、坑卡（做之前先看）

1. **暖身根數**：`Update()` 一開始資料還不夠，必須像骨架 ⑧ 那樣先判斷 `Count`，
   否則會取到無效值或直接出錯。
2. **`SeparateWindow` 選錯**：均線類要疊主圖（`false`），RSI／MACD 這類擺盪指標
   要獨立副圖（`true`），選錯會讓圖表比例整個爛掉。
3. **線名要一致**：建構子 `Lines.Set("A")` 與後面 `Lines["A"]` 的字串必須完全相同，
   打錯字不會編譯失敗，但線畫不出來——這是最常見的「明明編譯過卻沒東西」。
4. **AI 幻覺 API**：見上一節，只信速查表裡有的。
5. **CFD 有買賣價差**：`Ask` 與 `Bid` 不同，報告要寫明用的是哪一個。
6. **模擬帳號課前辦好**：申請後要收信取得帳號，現場才登入。

## 六、驗收與交付（接回課程的六件套）

- **驗證**：用平台的**回測面板**跑一次（可選單一或多商品、多時間框架）——
  這就是五關卡「監控化」那一關在 EvoCode 版的作法。
- **交付**：EvoCode 的原始碼可以 Save／Save as 存成檔案 →
  **`.cs` 原始碼推進 GitHub 倉庫**，與 PLAN.md、TASK.md、MEMORY.md 放在一起。
  → 六件套（GitHub、push、定期 commit、PLAN、TASK、MEMORY）一字不改，完全適用。
- **結論報告**：把回測結果與圖表訊號餵給 AI，產出四節結論報告
  （現況數字／與關稅事件日對照／判讀／限制與失效條件），合規框定與 Python 題完全相同。

---
本文件為教學用速查，不構成任何投資建議。指標僅供判讀參考，不產生買賣指令。
