@echo off
setlocal

if not exist venv (
  echo X Rode primeiro: setup_windows.bat
  exit /b 1
)

call venv\Scripts\activate.bat

REM Carrega credenciais/config local (veja .env.local.example) — nao versionado
if exist .env.local (
  for /f "usebackq eol=# tokens=1,2 delims==" %%A in (".env.local") do set "%%A=%%B"
)

echo.
echo   X Video Scraper — Iniciando (Windows)
echo.
echo   Backend: http://localhost:5000
echo   Feche esta janela para parar o servidor.
echo.

REM waitress-serve = servidor WSGI puro-Python, equivalente ao gunicorn do
REM Linux (gunicorn nao funciona no Windows, depende de fork()). --threads 4
REM pelo mesmo motivo do gthread no Linux: sem isso, uma busca lenta (Selenium
REM rolando a pagina) bloqueia toda requisicao nova ate terminar, inclusive
REM cliques em "Baixar".
waitress-serve --host=0.0.0.0 --port=5000 --threads=4 app:app
