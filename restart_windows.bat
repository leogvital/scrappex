@echo off
setlocal

set PORT=5000
set LOG=%TEMP%\scrapperx.log

if not exist venv (
  echo X Rode primeiro: setup_windows.bat
  exit /b 1
)

call venv\Scripts\activate.bat

REM Carrega credenciais/config local (veja .env.local.example) — nao versionado
if exist .env.local (
  for /f "usebackq eol=# tokens=1,2 delims==" %%A in (".env.local") do set "%%A=%%B"
)

REM Mata quem estiver ouvindo na porta 5000 (equivalente ao "kill $(lsof -ti:$PORT)" do restart.sh)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
  echo   Parando servidor atual (PID %%P)...
  taskkill /F /PID %%P >nul 2>nul
)

echo.
echo   X Video Scraper — Reiniciando (Windows)
echo.

REM Roda em segundo plano (janela oculta), assim como o "nohup ... &" do Linux —
REM continua rodando mesmo fechando este terminal.
start "scrapperx" /B cmd /C "waitress-serve --host=0.0.0.0 --port=%PORT% --threads=4 app:app > "%LOG%" 2>&1"

timeout /t 2 /nobreak >nul

curl -s -o nul -w "%%{http_code}" http://localhost:%PORT%/api/session > "%TEMP%\scrapperx_check.txt" 2>nul
set /p CODE=<"%TEMP%\scrapperx_check.txt"
if "%CODE%"=="200" (
  echo   OK: Servidor rodando em http://localhost:%PORT%
  echo   Logs: %LOG%
) else (
  echo   X Falha ao iniciar — confira: %LOG%
  exit /b 1
)
