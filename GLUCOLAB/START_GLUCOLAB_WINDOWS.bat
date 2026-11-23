@echo off
cd /d "%~dp0"
set "PY=python"
rem Prefer the Anaconda Python already active in Anaconda Prompt.
python --version >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if not errorlevel 1 set "PY=py -3"
)
echo Installing/checking GLUCOLAB dependencies...
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
 echo.
 echo Could not install the Python dependencies. Open Anaconda Prompt and run python -m pip install -r requirements.txt instead.
 pause
 exit /b 1
)
echo.
echo GLUCOLAB opens at http://127.0.0.1:8000
 echo Keep this window open while you use the website.
%PY% app.py
if errorlevel 1 (
 echo.
 echo GLUCOLAB could not start. Please read the error above.
 pause
)
