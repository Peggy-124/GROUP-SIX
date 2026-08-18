# -*- coding: utf-8 -*-
"""
系統設定檔：匯率代號、出口族群、重大事件與系統參數
"""
from pathlib import Path

# 專案根目錄與資料夾設定
BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = BASE_DIR / "cache"

for d in [RAW_DIR, DATA_DIR, CACHE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 匯率與美元指數定義
# 說明：Yahoo 匯率為中價/收盤價；USD/XXX 數值上升表示美元升值、該貨幣貶值
DEFAULT_FX_SYMBOLS = {
    "^NYICDX": {
        "name": "ICE 美元指數 (DXY)",
        "type": "index",
        "description": "衡量美元對一籃子主要貨幣的匯率加權指數",
        "unit": "點",
        "direction_hint": "數值上升代表美元全面升值",
    },
    "TWD=X": {
        "name": "美元兌新台幣 (USD/TWD)",
        "type": "fx",
        "description": "美元兌新台幣匯率（中價）",
        "unit": "NTD",
        "direction_hint": "數值上升 = 美元升值、台幣貶值；數值下降 = 台幣升值",
    },
    "JPY=X": {
        "name": "美元兌日圓 (USD/JPY)",
        "type": "fx",
        "description": "美元兌日圓匯率（中價）",
        "unit": "JPY",
        "direction_hint": "數值上升 = 美元升值、日圓貶值（日本出口競爭力提升）",
    },
    "CNY=X": {
        "name": "美元兌人民幣 (USD/CNY)",
        "type": "fx",
        "description": "美元兌在岸人民幣匯率（中價）",
        "unit": "CNY",
        "direction_hint": "數值上升 = 美元升值、人民幣貶值",
    },
    "CNH=X": {
        "name": "美元兌離岸人民幣 (USD/CNH)",
        "type": "fx",
        "description": "美元兌離岸人民幣匯率（中價）",
        "unit": "CNH",
        "direction_hint": "數值上升 = 美元升值、離岸人民幣貶值",
    },
}

# 台灣出口族群與預設股票代號
DEFAULT_EXPORT_SECTORS = {
    "半導體": {
        "description": "晶圓代工與 IC 設計，高度美元計價出口，台幣貶值有利毛利與匯兌利益",
        "stocks": {
            "2330.TW": "台積電",
            "2454.TW": "聯發科",
            "2303.TW": "聯電",
        },
    },
    "電子代工": {
        "description": "組裝與伺服器代工，營收規模大、毛利率低，對匯率波動極度敏感",
        "stocks": {
            "2317.TW": "鴻海",
            "2382.TW": "廣達",
            "3231.TW": "緯創",
        },
    },
    "航運": {
        "description": "貨櫃航運三雄，運價以美元計價，營運成本部分為各國港口費",
        "stocks": {
            "2603.TW": "長榮",
            "2609.TW": "陽明",
            "2615.TW": "萬海",
        },
    },
    "自行車": {
        "description": "歐美外銷出口產業，關稅與匯率雙重影響海外終端售價與庫存去化",
        "stocks": {
            "9921.TW": "巨大",
            "9914.TW": "美利達",
        },
    },
}

# 預設重大關稅與匯率政策事件
DEFAULT_EVENTS = [
    {
        "date": "2025-08-22",
        "label": "美國政府入股英特爾 9.9%",
        "category": "半導體政策",
        "note": "88.9 億美元換 9.9% 股權，引發全球晶圓代工供應鏈板塊震盪",
    },
    {
        "date": "2025-10-30",
        "label": "川習會（釜山）",
        "category": "美中貿易",
        "note": "芬太尼關稅減半、稀土管制暫停一年、貿易停火延長",
    },
    {
        "date": "2026-01-15",
        "label": "232條款 25% 半導體關稅生效",
        "category": "關稅生效",
        "note": "聯邦公報 2026-01052，針對最高階 AI 晶片課稅，牽動台美供應鏈定價",
    },
    {
        "date": "2026-02-20",
        "label": "最高法院判對等關稅違憲",
        "category": "法規轉折",
        "note": "6 比 3 裁定《國際緊急經濟權力法》不授權課關稅，美元指數劇烈波動",
    },
    {
        "date": "2026-07-16",
        "label": "台積電加碼投資美國至 2650 億美元",
        "category": "供應鏈設廠",
        "note": "美國商務部新聞稿，先進製程在地化進一步加速",
    },
]

PERIOD_MAP = {
    "1 個月": "1mo",
    "3 個月": "3mo",
    "6 個月": "6mo",
    "1 年": "1y",
    "2 年": "2y",
    "自訂日期": "custom",
}

LEAD_LAG_DAYS = [-10, -5, -3, -1, 0, 1, 3, 5, 10]

DISCLAIMER_TEXT = "⚠️ 本工具僅供教育與研究用途，所有內容皆為資料觀察，不構成投資建議。"
