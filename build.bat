@echo off
REM Gera o watchdog.exe a partir de main.py + módulos locais.
REM PyInstaller segue os imports automaticamente - todos os .py
REM desta pasta sao embutidos num unico executavel.

pip install -r requirements.txt
pip install pyinstaller

pyinstaller --onefile --console --name watchdog main.py

echo.
echo Executavel gerado em dist\watchdog.exe
pause
