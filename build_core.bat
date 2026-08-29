@echo off
rem ============================================
rem  Aku Desktop Pet - build logic (pure ASCII,
rem  works on any Windows locale / codepage).
rem ============================================
cd /d %~dp0

rem --- clear possibly-broken proxy env vars (delete these 4 lines if you use a working proxy) ---
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set NO_PROXY=

echo.
echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 goto :nopython

echo [2/4] Installing dependencies (Tsinghua mirror, first time may take a while)...
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 30
python -m pip install -r requirements.txt pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 30
if errorlevel 1 goto :nopip

echo [2.5/4] Checking Qt platform plugin (qwindows.dll)...
python -c "import os,PyQt5,sys;p=os.path.join(os.path.dirname(PyQt5.__file__),'Qt5','plugins','platforms','qwindows.dll');ok=os.path.isfile(p);print('  qwindows.dll:', 'OK' if ok else 'MISSING');sys.exit(0 if ok else 1)"
if errorlevel 1 goto :repairqt
goto :qtok

:repairqt
echo.
echo   [!] qwindows.dll missing. This is almost always the antivirus
echo       deleting Qt files right after they are installed.
echo       Try: add these folders to your antivirus whitelist:
echo         - this project folder
echo         - C:\Users\<you>\AppData\Local\Programs\Python
echo       Then rerun. Retrying once with a clean reinstall...
python -m pip uninstall -y PyQt5 PyQt5-Qt5 PyQt5-sip
python -m pip install PyQt5 PyQt5-Qt5 PyQt5-sip -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60
if errorlevel 1 goto :nopip
python -c "import os,PyQt5,sys;p=os.path.join(os.path.dirname(PyQt5.__file__),'Qt5','plugins','platforms','qwindows.dll');ok=os.path.isfile(p);print('  qwindows.dll:', 'OK' if ok else 'MISSING');sys.exit(0 if ok else 1)"
if errorlevel 1 goto :qtbroken
echo   Qt runtime repaired OK.
goto :qtok

:qtbroken
echo.
echo   [ERROR] qwindows.dll is STILL missing after reinstall.
echo   Your antivirus is actively deleting Qt plugin files.
echo   Two ways forward:
echo     1) Whitelist the project folder and the Python folder in your
echo        antivirus, then rerun this script.
echo     2) Use GitHub Actions cloud build (README 4-B) - it builds in
echo        a clean environment, no antivirus, no local Python needed.
goto :end

:qtok
echo [3/4] Checking icon...
if exist assets\icon.ico goto :iconok
python make_icon.py
if errorlevel 1 goto :fail
:iconok

echo [4/4] Building exe (may take 1-3 minutes)...
pyinstaller --noconfirm --clean --onefile --windowed --name "Aku" --icon assets\icon.ico --hidden-import keyboard --collect-submodules petpet main.py
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo   SUCCESS!
echo   exe:  dist\Aku.exe
echo   First launch creates config.json (scale/note/hotkeys).
echo   (You may rename Aku.exe to whatever you like.)
echo ============================================================
goto :end

:nopython
echo.
echo   [ERROR] Python not found.
echo   Install Python 3.9+ from python.org and check "Add to PATH".
goto :end

:nopip
echo.
echo   [ERROR] Failed to install dependencies.
echo   Check network, or use GitHub Actions cloud build (README 4-B).
goto :end

:fail
echo.
echo   [ERROR] A build step failed. Read the messages above.
goto :end

:end
exit /b 0
