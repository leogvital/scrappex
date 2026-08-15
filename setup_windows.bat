@echo off
setlocal

echo   X Video Scraper — Setup (Windows)
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo X Python nao encontrado no PATH. Instale em https://python.org/downloads/
  echo   Marque "Add python.exe to PATH" durante a instalacao.
  exit /b 1
)
python --version

if not exist venv (
  echo -> Criando ambiente virtual...
  python -m venv venv
  if errorlevel 1 (
    echo X Falha ao criar o venv.
    exit /b 1
  )
)

call venv\Scripts\activate.bat
echo Ambiente virtual ativo

echo -> Instalando dependencias...
python -m pip install --upgrade pip --quiet
REM waitress no lugar do gunicorn (gunicorn usa fork(), nao existe no Windows).
REM secretstorage fica de fora — e so para o keyring do Linux (D-Bus); no Windows
REM o yt-dlp usa a API DPAPI nativa para decifrar cookies do Chrome/Edge.
pip install flask flask-cors yt-dlp waitress requests selenium webdriver-manager "curl_cffi>=0.10,<0.15" psutil --quiet
echo OK: flask, flask-cors, yt-dlp, waitress, requests, selenium, webdriver-manager, curl_cffi, psutil instalados

echo.
echo Setup concluido! Inicie com: start_windows.bat
