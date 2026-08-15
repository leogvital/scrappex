#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "✗ Rode primeiro: bash setup.sh"
  exit 1
fi

source venv/bin/activate

# Carrega credenciais/config local (veja .env.local.example) — não versionado
if [ -f .env.local ]; then
  set -a
  source .env.local
  set +a
fi

# Instala gunicorn se não tiver
pip show gunicorn      &>/dev/null || pip install gunicorn --quiet
pip show secretstorage &>/dev/null || pip install secretstorage --quiet
pip show requests      &>/dev/null || pip install requests --quiet
pip show selenium      &>/dev/null || pip install selenium --quiet
pip show webdriver-manager &>/dev/null || pip install webdriver-manager --quiet

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    X Video Scraper — Iniciando       ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  Backend: http://localhost:5000"
echo "  Pressione Ctrl+C para parar."
echo ""

exec gunicorn app:app \
  --bind 0.0.0.0:5000 \
  --workers 1 \
  --worker-class gthread \
  --threads 4 \
  --timeout 600 \
  --log-level warning \
  --access-logfile - \
  --no-control-socket
