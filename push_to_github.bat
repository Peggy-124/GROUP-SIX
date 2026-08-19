@echo off
chcp 65001 >nul
echo ========================================================
echo  正在推送成果至 GitHub: https://github.com/Peggy-124/GROUP-SIX
echo ========================================================
echo.

:: 檢查 git 是否存在
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [提示] 系統找不到 git 指令，請確認是否已安裝 Git for Windows。
    echo 如果已安裝，請使用「Git Bash」開啟本資料夾執行。
    echo.
    pause
    exit /b 1
)

:: 初始化與設定遠端倉庫
git init
git remote remove origin 2>nul
git remote add origin https://github.com/Peggy-124/GROUP-SIX.git

:: 切換至 main 分支
git branch -M main

:: 加入所有成果檔案
git add .

:: 提交 Commit
git commit -m "feat: 更新第六組匯率與出口股連動量化成果報告與 HTML 呈現"

:: 推送至 GitHub
echo.
echo 正在推送至 GitHub main 分支...
git push -u origin main

echo.
echo ========================================================
echo  推送完成！請至 https://github.com/Peggy-124/GROUP-SIX 查看
echo ========================================================
pause
