# SETUP.md 範本

> 用途：環境重建步驟——從一台空白電腦到能跑出你們的程式，一步一步寫下來。
> Day 1 收尾時寫，Day 2 開場照著自己寫的這份重建環境。重建順利，代表寫得夠好；
> 卡住，代表漏了什麼，當場補上再繼續。
>
> 完整安裝步驟見 [`../docs/02-環境設定.md`](../docs/02-環境設定.md)，這裡只記
> **自己這組實際裝了什麼、版本多少**，不用重抄一遍教學文。

---

## 填寫範例

```markdown
## 環境重建步驟（第 3 組）

1. 安裝 Python 3.12（python.org 下載，安裝時勾選 Add to PATH）
   確認：終端機打 `python --version` 看到 `Python 3.12.4`

2. 安裝 Antigravity（antigravity.google 下載，用 Google 帳號登入）
   確認：開啟後左側檔案總管、下方終端機都看得到

3. 安裝 Chrome（Antigravity 登入需要）
   確認：能正常開網頁

4. 終端機安裝套件：
   pip install requests matplotlib
   確認：`pip list` 看得到 requests 2.32.x、matplotlib 3.9.x

5. Clone 倉庫：
   在 Antigravity 用 Source Control 面板 Clone Repository，
   貼上 https://github.com/xxx/tariff-semi-group3
   確認：左側檔案總管看得到 README.md、PLAN.md

6. 跑第一支程式確認：
   python probes/fetch_twse.py
   確認：終端機印出 2330 最新一筆收盤價，沒有紅字錯誤

## 這組的特別設定
- pip 安裝很慢時，改用 `pip install -i https://pypi.org/simple requests matplotlib`
- Windows 中文路徑跑程式偶爾會亂碼，統一在終端機打 `chcp 65001` 先切成 UTF-8
```

---

## 空白版（複製這一段填寫）

```markdown
## 環境重建步驟（第＿組）

1. 安裝 Python（版本：＿）
   確認：

2. 安裝 Antigravity（或 Cursor）
   確認：

3. 安裝 Chrome
   確認：

4. 終端機安裝套件：

   確認：

5. Clone 倉庫：
   網址：
   確認：

6. 跑第一支程式確認：
   指令：
   確認：

## 這組的特別設定
-
```

---

## 提醒

- 每一步都要寫「怎麼確認這步成功了」，不是「裝完就好」——Day 2 卡住的時候，
  就是靠這一行判斷卡在哪一步。
- 套件版本盡量寫具體數字（`pip list` 或 `pip freeze` 可以看到），
  不要只寫「裝了 requests」。
- 如果這組有特別的環境問題（例如某台電腦裝不起來、要換別的下載來源），
  寫進「這組的特別設定」，明天照著避開同一個坑。
