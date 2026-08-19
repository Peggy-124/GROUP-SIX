@echo off
chcp 65001 >nul
echo ========================================================
echo  打包「匯率與出口股連動」為單一獨立 HTML 成果報告
echo ========================================================
echo.
py generate_all.py
echo.
echo 打包完成！您可以直接雙擊開啟 index.html 或 GROUP-SIX-Report.html
pause
