@echo off
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pip
python -m pip install pyinstaller pystray pillow cryptography win11toast

pyinstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name SMSBridge ^
  sms2clipboard_gui.py

echo.
echo 打包完成，EXE 位于 dist\SMSBridge.exe
pause
